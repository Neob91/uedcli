# Port UE1 mesh geometry decode to Rust — Implementation Plan

**Spec:** `dev/docs/board/to-plan/port-ue1-mesh-geometry-decode-to-rust/spec.md` — read it first; this
plan implements it and does not re-derive the wire format or the design decisions it already settled
(whole-body port, plain-tuple return shape, deletion gated on visual sign-off).

**Goal:** Add `uedcli-native/src/mesh_read.rs` + a `parse_mesh_raw` PyO3 binding that decodes a
`Mesh`/`LodMesh` export body exactly as `umesh.py`'s `parse_mesh` does today, and rewire
`umesh.py`'s `parse_mesh` to call it. Byte-identical `Mesh` objects; frozen public API
(`umesh.Mesh`, `umesh.parse_mesh`, `umesh.mesh_exports`).

**Explicitly NOT this plan's job — deletion is a separate, later step.** The spec's "Removal gate"
requires the owner's visual sign-off (`level photo` + `class preview` renders, both substrates)
*before* `lazy_array`/`tarray`/the element decoders/the low-level primitives get deleted from
`umesh.py`. This plan switches `parse_mesh` over to the Rust path and leaves those functions in the
file, unused — do not delete them here, no matter how confidently green the tests are. A comment at
the top of the now-dead block should say so (`# unused since <this change> — kept pending visual
sign-off, see the item's "Removal gate"`).

## Global constraints

- No CLI-observable change: byte-identical decode results, same public Python API.
- No new crate dependency — hand-roll, matching `package_read.rs`/`model_read.rs`'s existing style.
- Reuse `package_read::read_compact_index` rather than re-implementing it.
- Every parse error surfaces as the existing `PackageError` in Python — never a bare panic/traceback.
- Run tests via `bin/test`, never bare `pytest` (`dev/docs/rules/tests.md`); on this host use `-s`
  and a worktree-relative `TMPDIR` (`mkdir -p _scratch/pt && TMPDIR=$PWD/_scratch/pt bin/test
  -p no:cacheprovider -o cache_dir=_scratch/pt/pc -s <args>` — bare `pytest` capture crashes on the
  shared `/tmp` across concurrent sessions). Scope each task's runs to what it touches; run the full
  non-integration suite once before the final commit.
- `cargo test` (fast, via the build image) must stay green throughout.

---

## Task 1 — Rust decoder: `uedcli-native/src/mesh_read.rs`

**Files:** create `uedcli-native/src/mesh_read.rs`; modify `uedcli-native/src/lib.rs` (add
`mod mesh_read;` alongside the other `mod` declarations, alphabetically between `linecheck` and
`model`).

Port `uedcli/umesh.py`'s primitives and `parse_mesh` faithfully — read the real file, don't work
from memory of it. In order:

1. The element decoders `parse_mesh` drives: `fvec`/`frotator`/`fbox`/`fsphere`,
   `mesh_vert_dx`/`mesh_vert_packed`, `mesh_tri`, `mesh_anim_notify`/`mesh_anim_seq` (**both traps
   preserved**: `Group` is a single FName not `TArray<FName>`; serialized field order is
   Name/Group/Start/NumFrames/**Notifys**/**Rate**, Notifys before Rate), `mesh_vert_connect`,
   `mesh_face`, `mesh_wedge`, `mesh_material`.
2. `tarray`/`lazy_array` as generic helpers over those element decoders (`lazy_array` reads the
   version-gated `SkipOffset` and self-checks it against the position after decoding — keep that
   invariant, it's what catches a wrong element width at the array that has it).
3. `detect_vert_stride`'s skip-offset-vs-count math (an internal decision, no public wrapper).
4. One function assembling everything into a `RawMesh` struct, matching `parse_mesh`'s own order:
   box/sphere → vertex-stride detection (using `vert8_hint` only when the `Verts` array is empty and
   stride can't be self-detected — the same fallback `parse_mesh`'s own `vert8=None` keyword
   argument provides today; error if stride is undetectable AND no hint was given) → verts/tris/
   anim_seqs/connects → the inline box/sphere re-read → vert_links/textures/bboxes/bspheres/
   frame_verts/anim_frames/**two separate discarded `u32` flag reads (`_and_flags` then
   `_or_flags`)**/scale/origin/rot_origin/cur_poly/cur_vertex → the `ver==65` vs `ver>=66` branch →
   (if `is_lod`) the ULodMesh tail through `old_frame_verts` → the `RemapAnimVerts` rebuild when
   non-empty. Assert `pos == end` at the finish (the "consumed exactly to export end" self-check) and
   return an error naming the delta, not a panic, on mismatch. When `is_lod` is false, `RawMesh`'s
   LodMesh-only fields take the same defaults `umesh.Mesh`'s dataclass does (empty vecs, `0`/`0.0`) —
   Rust's natural zero-value defaults already match; no special-casing needed, just don't populate
   them.

```rust
pub fn parse_mesh_body(buf: &[u8], pos: usize, end: usize, version: i32, is_lod: bool,
                        vert8_hint: Option<bool>) -> Result<RawMesh, crate::model::BuildError>
```

`crate::model::BuildError` — the same internal error type `package_read.rs` itself uses
(`package_read.rs:11`), NOT the Python-exposed `uedcli_native.BuildError` exception (`lib.rs:39`).
Mesh decode errors route through the existing `PackageError`/`map_pkg_err` conversion instead (Task
2) — the same one `read_property_tags_raw` uses, since a malformed mesh body is a package-decode
failure in the same sense a malformed property tag is.

- [ ] **Step 1:** Module skeleton + the element decoders + their `cargo test` unit tests against
  hand-built byte fixtures (a handful of synthetic vertex/tri/anim-seq byte sequences with known
  expected output — the same kind of test `package_read.rs`'s own `read_compact_index` tests use).
- [ ] **Step 2:** `tarray`/`lazy_array` + `detect_vert_stride`, with a test proving a wrong element
  width trips the skip-offset self-check (the property that makes this format self-verifying).
- [ ] **Step 3:** `parse_mesh_body` assembling the full body, plain `Mesh` (not LOD) path first, with
  a unit test decoding one real mesh export's byte span pulled from a committed test fixture package.
- [ ] **Step 4:** The `is_lod` branch (ULodMesh tail) + `RemapAnimVerts` rebuild, with a unit test
  against a real LodMesh export that has non-empty `RemapAnimVerts` (per `umesh.py`'s own comment,
  this only shows up in original Unreal Gold content, not DX/UT retail — use whatever fixture
  `test_unrealgold_lodmesh_verts_are_rebuilt_through_the_remap` already uses).

**Acceptance:** `cargo test` green, including the new module's tests.

## Task 2 — PyO3 binding

**Files:** modify `uedcli-native/src/lib.rs`.

```rust
#[pyfunction]
fn parse_mesh_raw(py: Python<'_>, buf: &[u8], pos: usize, end: usize, version: i32, is_lod: bool,
                   vert8_hint: Option<bool>) -> PyResult<RawMeshOut>
```

- Borrow `buf: &[u8]`, never `Vec<u8>` — `read_property_tags_raw`'s own history is why (an owned
  copy measured ~15-20ms/call regardless of the tiny span decoded; borrowed, microseconds).
- Heavy work under `py.allow_threads(...)`.
- `RawMeshOut` a typed tuple alias, one position per `RawMesh`/`Mesh` field, in `Mesh`'s own
  declaration order (see spec.md's field list). Nested arrays (verts, tris, anim_seqs, …) become
  `Vec<tuple>`, matching how `read_property_tags_raw` returns `Vec<RawPropertyTagOut>` today.
- Errors: reuse `PackageError` via the same `map_pkg_err` conversion `read_property_tags_raw` uses.
- Register with `m.add_function(wrap_pyfunction!(parse_mesh_raw, m)?)?;` beside the other
  `package_read`-family registrations.

**Acceptance:** `cargo test` still green (binding compiles); no Python wiring yet (Task 3).

## Task 3 — Python shell: rewire `umesh.py`

**Files:** modify `uedcli/umesh.py`.

`parse_mesh` becomes a thin wrapper, mirroring `upackage.read_property_tags`'s own shape exactly:

1. Read the property-tag prefix (unchanged — already native).
2. Compute `is_lod` the same way as today (`cls = pkg.object_class_name(j + 1)`) — this already
   happens in Python before any body byte is read, so nothing about the call flow changes.
3. Call `uedcli_native.parse_mesh_raw(pkg.buf, p, end, pkg.version, is_lod, vert8)` — `vert8` is
   `parse_mesh`'s existing keyword-only parameter (`vert8=None`), passed through unchanged as the
   Rust function's stride-detection fallback. Reach the extension via the existing
   `native_ext.import_native()` dispatch (the same pattern `read_property_tags` already uses — do
   not invent a second way to reach the native extension).
4. Unpack the returned tuple into a `Mesh(...)` instance; keep the `strict_end`/`(m, p)` return-shape
   contract `parse_mesh`'s callers rely on today unchanged.

Do **not** delete `lazy_array`, `tarray`, the element decoders, or the low-level primitives — see
this plan's header. Add the one-line comment marking them unused-pending-sign-off.

**Acceptance:** `uedcli/tests/test_mesh_decode.py` passes unchanged, byte-for-byte, against the new
path — every test in that file (stride detection both substrates, the anim-seq trap, the LodMesh
tail ordering, both RemapAnimVerts tests, the Keypad3 ground-truth cross-check, the
not-DX-specific-tail test).

## Task 4 — Corpus parity + full verification

- A one-off migration-guard test (or script, run once and reported in the commit message — not kept
  as a durable test): every `Mesh`/`LodMesh` export in every `.u`/`.utx` fixture already in the repo,
  decoded by BOTH the old Python path (call the pre-rewire functions directly, not through
  `parse_mesh`) and the new Rust-backed `parse_mesh`, compared field-for-field. Report N
  meshes/N packages checked, 0 mismatches expected.
- Full scoped run: `test_mesh_decode.py`, `test_mesh_world_transform.py`, `test_meshrender.py`,
  `test_meshworld.py`, `test_preview_native.py`, `test_class_preview.py`, `test_class_facts.py`
  (every test file importing `umesh`, directly or via `meshfacts`/`meshrender`/`meshworld`/
  `preview_native` — verified by grep, not assumed).
- One full non-integration suite pass before the final commit (`dev/docs/rules/tests.md`).
- `cargo test` green.

**Acceptance:** all of the above green; the parity check's N/mismatch counts recorded in the final
commit message (not as a kept test file).

## Refs

`dev/docs/board/to-plan/port-ue1-mesh-geometry-decode-to-rust/spec.md` ·
`dev/docs/board/done/unify-ue1-package-read-primitives-into-one-rust/` (the sibling port + its own
plan.md, for task-shape precedent) · `uedcli/umesh.py` · `uedcli-native/src/package_read.rs` ·
`uedcli-native/src/lib.rs`
