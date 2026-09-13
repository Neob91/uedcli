# Spec — port UE1 mesh geometry decode to Rust

## Goal

Replace `umesh.py`'s pure-Python per-export mesh body decode (`parse_mesh`, `lazy_array`, and the
element decoders it drives — vertex/triangle/wedge/face/material tables) with one Rust decoder,
exposed via PyO3, following the exact pattern `package_read.rs`/`read_property_tags_raw` already
established for the sibling package-primitive port (`unify-ue1-package-read-primitives-into-one-rust`,
done). No CLI-observable change: byte-identical `Mesh` objects, same public Python API
(`umesh.Mesh`, `umesh.parse_mesh`, `umesh.mesh_exports`).

### Evidence

Same profiling pass as the package-primitive item: `level photo --native` on original Unreal
`IsvKran32.unr` (1705 brushes, 1439 mesh-actor instances, 108 distinct meshes), cProfile-scoped to
`build_scene`, 2026-09-11.

| Function | Calls | Cumulative | Own time |
|---|---|---|---|
| `meshrender.resolve_skins` | 108 | 18.85s | 0.004s |
| `meshfacts.decode_mesh` | 108 | 15.76s | 0.007s |
| `umesh.parse_mesh` (line 235) | 108 | 7.12s | 0.50s |
| `umesh.lazy_array` (line 77) | 432 | 6.40s | 1.88s |

Only 108 distinct meshes decode for 1439 actor instances — this is per-distinct-asset parsing, not
redundant re-decoding. `lazy_array`'s own time (the tight per-element loop over Verts/Tris/Connects/
VertLinks) is the single biggest self-time contributor after raw file I/O. Property-tag reading
(the first thing `parse_mesh` does) is **already native** (`upackage.read_property_tags` →
`uedcli_native.read_property_tags_raw`) — the profiled cost is entirely in what runs *after* it.

**Scope: read path only**, one export class pair (`Mesh`/`LodMesh`). The mesh *write* path does not
exist in this codebase (uedcli never authors meshes) and is out of scope.

## Design

### Rust core — `uedcli-native/src/mesh_read.rs`

Pure functions, no PyO3 inside (matches `package_read.rs`'s own style — `cargo test`-able with no
Python). Reuses `package_read::read_compact_index` rather than re-implementing it (`umesh.py`'s
`tarray`/`lazy_array`/`m.textures` all bottom out in compact-index reads today).

One entry point, decoding the **whole per-export body after the property-tag prefix** — not just
the hot arrays — in a single pass, owner-confirmed (2026-09-12) over the narrower
"arrays-only" alternative: it keeps the "consumed exactly to export end" self-check
(`umesh.py`'s `strict_end` assertion) inside one function instead of split across a language
boundary, and every remaining field (box/sphere/scale/origin/frame_verts/anim_frames/texture_lod,
the LodMesh tail, the `RemapAnimVerts` rebuild) is still pure struct-level decode or array
indexing — the same category of work as the arrays already targeted, just smaller individually:

```rust
pub fn parse_mesh_body(buf: &[u8], pos: usize, end: usize, version: i32, is_lod: bool,
                        vert8_hint: Option<bool>) -> Result<RawMesh, BuildError>
```

`RawMesh` is a plain struct mirroring `umesh.Mesh`'s fields one-for-one (box, sphere, verts, tris,
anim_seqs, connects, vert_links, textures, frame_verts, anim_frames, scale, origin, rot_origin,
texture_lod, vert_stride, and the `LodMesh`-only fields), including:

- **Vertex-stride self-detection** (`detect_vert_stride`'s logic — read the `Verts` `TLazyArray`
  header's skip-offset vs. element count without decoding, to pick the 8-byte Deus Ex `FMeshVert`
  vs. the 4-byte stock-Unreal packed form) — an internal decision inside this function, not a
  separately exposed primitive.
- **The `RemapAnimVerts` rebuild** (`umesh.py:315-330`) — done in Rust too, operating on the
  already-decoded `verts`/`remap_anim_verts` arrays before they cross back to Python, so a large
  animated mesh's vertex table is rebuilt once, in Rust, not shipped twice across the FFI boundary.
- **Both documented version traps**, faithfully reproduced: `mesh_anim_seq`'s `Group` is a single
  FName (not a `TArray<FName>`) and its field order is Name/Group/Start/NumFrames/**Notifys**/**Rate**
  (Notifys before Rate, not declaration order); `ver == 65` reads one trailing float where `ver >= 66`
  reads a `texture_lod` array instead.

### PyO3 binding

One `#[pyfunction] fn parse_mesh_raw(py: Python<'_>, buf: &[u8], pos: usize, end: usize,
version: i32, is_lod: bool, vert8_hint: Option<bool>) -> PyResult<RawMeshOut>` in `lib.rs`,
following `read_property_tags_raw`'s exact shape:

- `buf: &[u8]` — a **borrowed** slice, not an owned `Vec<u8>`. `read_property_tags_raw`'s own
  history is the reason this is non-negotiable: an owned buffer measured ~15-20ms/call regardless
  of the tiny span actually decoded, dominated by copying the whole package on every call; borrowed,
  microseconds. A mesh body decode reads the same full package buffer this many times per photo.
- Heavy work under `py.allow_threads(...)` (interruptible, GIL released).
- **Return shape: plain tuples/lists**, matching `RawPropertyTagOut`'s convention — owner-confirmed
  over a leaner packed/byte-span representation, for consistency with the one PyO3 pattern this
  codebase already uses everywhere else. `RawMeshOut` is a typed tuple alias assembling the
  `RawMesh` fields in the same order `umesh.Mesh`'s dataclass declares them. **Considered and
  rejected:** dropping `vert_stride` from the tuple and deriving it Python-side from a single
  `vert8: bool` the Rust side already computes internally (`vert_stride = 8 if vert8 else 4` is pure
  duplication) — kept as its own field anyway, for the same reason as the rest of this shape: one
  tuple position per `Mesh` field, no reader has to know a derivation rule to reconstruct the
  dataclass.
- Errors: reuse the existing `PackageError` (mesh bodies live inside `.u`/`.utx` packages; a
  malformed mesh is a package-decode failure in the same sense a malformed property tag is) via the
  same `map_pkg_err` conversion `read_property_tags_raw` uses — never a panic/traceback.

### Python shell — `umesh.py`

`parse_mesh`'s public signature and the `Mesh` dataclass are **frozen** — `meshfacts.decode_mesh`
(the sole call site of `parse_mesh` itself) is untouched, as is everything reading a decoded `Mesh`
downstream: `meshrender.py`, `preview_native.py`, and `meshworld.py` (`mesh_scale`/
`mesh_vertex_to_world` read `.scale`/`.origin`/`.rot_origin` directly off the dataclass).
The function body becomes a thin wrapper, exactly mirroring how `upackage.read_property_tags` wraps
`read_property_tags_raw` today:

1. Read the property-tag prefix (already native, unchanged).
2. Call `uedcli_native.parse_mesh_raw(pkg.buf, p, end, pkg.version, is_lod, vert8)`.
3. Unpack the returned tuple into a `Mesh(...)` instance.

`lazy_array`, `tarray`, `mesh_vert_dx`, `mesh_vert_packed`, `mesh_tri`, `mesh_anim_notify`,
`mesh_anim_seq`, `mesh_vert_connect`, `mesh_face`, `mesh_wedge`, `mesh_material`,
`detect_vert_stride`, and the low-level primitives (`u8`/`i16`/`u16`/`i32`/`u32`/`f32`/`fvec`/
`frotator`/`fbox`/`fsphere`) become dead code once the Rust path is proven (see "Removal gate"
below) and are deleted outright — no dual-path, no old-way branch, matching this project's own
no-back-compat-cruft convention.

## Tests

**Existing suite is the primary acceptance bar — no new test infrastructure needed.**
`uedcli/tests/test_mesh_decode.py` already exercises exactly the traps this port must reproduce, and
must pass **unchanged, byte-for-byte identical** against the Rust path:

- `test_v69_packages_parse_to_exact_end` / `test_v68_deusex_packages_parse_to_exact_end` — the
  consume-exactly-to-export-end self-check, per real package.
- `test_v68_vertex_stride_is_detected_as_eight_byte` / `test_v69_vertex_stride_is_detected_as_packed`
  — the self-describing stride detection.
- `test_anim_seq_group_is_a_single_fname_not_an_array` — the single-FName trap.
- `test_special_verts_precede_the_model_verts_in_each_frame`, `test_v68_old_frame_verts_mirrors_frame_verts`
  — LodMesh tail field ordering.
- `test_unrealgold_lodmesh_parses_with_populated_remap_anim_verts` /
  `test_unrealgold_lodmesh_verts_are_rebuilt_through_the_remap` — the RemapAnimVerts reconstruction,
  the one place this port does more than mechanical struct decode.
- `test_v68_keypad3_matches_umodel_ground_truth` — an independent-oracle cross-check.
- `test_lodmesh_tail_is_not_deusex_specific` — confirms the ULodMesh tail fields are real, not a DX
  quirk, so they must decode correctly on stock Unreal content too.

Additions for this item specifically:
- `cargo test` unit tests for `mesh_read.rs` against known-good byte fixtures per substrate (DX v68,
  stock Unreal v69) — the independent oracle, mirroring `package_read.rs`'s own test convention.
- A before/after parity check over the real corpus (every `Mesh`/`LodMesh` export in every `.u`
  fixture the repo already has): old Python decoder vs. new Rust one, byte-for-byte on every `Mesh`
  field. Run once during the build, delete after — a migration guard, not a durable test, exactly as
  the package-primitive port's own parity check was handled.

## Removal gate (owner requirement, 2026-09-12)

Passing `test_mesh_decode.py` is necessary but **not sufficient** to delete the old Python decoders.
Before deletion, produce and get the owner's visual sign-off on:

1. **`level photo`** renders of varied meshes **in both substrates** — a handful of real Unreal Gold
   (`.unr`) levels and a handful of real Deus Ex (`.dx`) levels, chosen for mesh variety (static
   props, animated/skeletal meshes if any are in scope, LOD meshes).
2. **`class preview`** standalone renders of individual mesh classes (one mesh, not embedded in a
   level) — isolates a per-mesh regression from any level-compositing issue.

Both already exist as CLI capabilities (`level photo`, `class preview`) — this is a verification
step using existing tooling, not new tooling to build. Only after (a) the full existing test suite
is green against the Rust path, (b) the corpus parity check passes, and (c) the owner has visually
confirmed the renders, do the superseded Python decode functions get deleted.

## Non-goals

- `read_property_tags`/`read_property_tags_raw` — already native, untouched.
- The package write path, and `native/pkg_write.py` — untouched.
- `meshrender.py`/`meshfacts.py`/`meshworld.py`'s own logic (skin resolution, triangle-frame
  extraction, world-space transforms) — untouched beyond continuing to consume the same frozen
  `Mesh` shape.
- Non-P8/non-DeusEx mesh format variants beyond what `umesh.py` already handles (stock Unreal packed
  verts are already in scope today; nothing new is added or dropped by this port).

## Refs

`dev/docs/board/done/unify-ue1-package-read-primitives-into-one-rust/` (the sibling port this
mirrors) · `dev/docs/board/stale/port-ue1-package-primitive-decode-to-rust-61m/` (same profiling
methodology) · `uedcli/umesh.py` · `uedcli/meshfacts.py` · `uedcli-native/src/package_read.rs` ·
`uedcli-native/src/lib.rs`
