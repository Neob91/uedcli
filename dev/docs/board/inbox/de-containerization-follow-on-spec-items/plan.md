# `level photo --native` — implementation plan

**Spec:** [`spec.md`](spec.md)
(two-cold-reviewer gated, findings folded). **Decisions:** `decisions.md` 2026-07-16 12:13 UTC.
**Status:** draft (plan gate pending). Ephemeral — delete once built; durable knowledge folds into
`architecture.md`.

---

## 0. Concurrency contract — coexistence with the native-materialize agent

Another agent is actively working the native-materialize line (`uedcli/native/*.py`,
`uedcli-native/src/{build,csg,fpoly,model_write,light,lib}.rs`, `apply.py`). This build is
deliberately architected to stay out of its way (the spec §5 "plan refinement"):

**NOT touched (read-only consumption or no contact at all):**
- `uedcli-native/src/{build,csg,fpoly,model,model_write,light,linecheck,passes,zones,paths}.rs` —
  `build_geometry` + `serialize_model` are called through the EXISTING FFI, unchanged. The
  `BrushTuple` shape is not modified (preview computes UV frames Python-side; the boarded
  texture-axes FFI extension is the materialize agent's fidelity fix, not ours).
- `uedcli/native/{materialize,assemble,umodel,actor_write,level_write,pkg_write,pkgref,codec}.py` —
  `umodel.parse_model_body` is imported read-only; `materialize._build_brush_input` is NOT called
  (preview has its own brush-input builder with different rotation/scale policy).
- `apply.py`, `packages.py`, `verify.py`, `writes.py`, `editor.py`, `stub*.py` — untouched.

**Touched, with expected-zero conflict:**
- `uedcli-native/src/lib.rs` — ADDITIVE only: register the new `render_frame` pyfunction + `mod
  render;`. Two new-line insertions; if the other agent edits `lib.rs` concurrently, the merge is
  trivial. Coordinate by appending at the end of the registration block.
- `uedcli-native/src/render.rs`, `Cargo.toml` (only if a dep were needed — none is planned) — new
  file.
- `preview_shots.py` — S3 adds the SHOT parser/pose math, S6 prunes the old grammar. Photo-only.
- `cli.py` / `dispatch.py` — the `level photo` verb region only. NB the photo and materialize
  parser blocks are textually ADJACENT in `cli.py`, so concurrent edits may textually conflict —
  expect plain merges there, not "clean by construction".
- Deleted at cutover: `preview_render.py`, `MODE_INI`, `preview_shots.parse_frame` + their tests —
  preview-only symbols; verified no materialize-side import.

**Two known couplings to watch (reviewer findings):**
- **`_brush_inputs` (S5) makes preview a SECOND constructor of the `BrushTuple` FFI**, and the
  boarded materialize fidelity fix is precisely a `BrushTuple` texture-axes extension. If that
  lands mid-build it is a signature break, not a merge nit. **Coordination rule:** the axes
  extension must be backward-compatible (optional trailing field) OR whoever lands it updates BOTH
  constructors in the same commit — recorded on the inbox item itself so the materialize agent
  sees it.
- **Until S6, the SHIPPED preview imports `apply._materialize`/`_materialized_order`**
  (`preview_render.py`) — a one-way dependency: a materialize-agent refactor of `apply.py` can
  break the still-live editor preview mid-build. The merge-and-retest rule covers detection; don't
  be surprised by it.

**Standing rule for every slice:** rebase-free (repo rule), commit+push per slice, re-run
`bin/test` before each push; if `lib.rs`/`dispatch.py`/`apply.py` changed underneath, plain-merge
and re-test — never assume sole ownership. Concurrent `bin/test` runs share the `.venv` and the
maturin source-hash marker, so a parallel native rebuild can race — on a weird build failure,
re-run once before digging.

---

## 1. Slices (each: build → offline tests green → commit+push)

### S1 — `uedcli/utexture.py` (texture decode, promoted)
- Copy `spikes/2026-06-27-decontainerize-uedcli/harness/utexture_decode.py` →
  `uedcli/utexture.py`; keep the spike file as evidence. API unchanged
  (`load_package`/`decode_texture`/`decode_palette`/`mip0_to_rgb`); drop the stdlib PNG writer
  (Pillow owns encode in uedcli) or keep it private — implementer's call.
- Add a ref-resolution helper: `Package[.Group].Name` → decoded RGB, searching
  `config.composed_search_files` (project shadows base), per-invocation cache, bare-ref → miss.
- **Tests:** decode a committed tiny fixture package pixel-exact (build the fixture once with the
  spike's `tex_compare.py` methodology, freeze bytes); v61-vs-v68 `WidthOffset` variant if a small
  fixture is obtainable, else document the gap; ref-resolution hit/miss/bare/group-qualified.
- New files only — zero conflict surface.

### S2 — Live anchor capture (BEFORE the editor preview is deleted)
The §9 anchor gate needs a real-engine reference render, and the easiest source — the CURRENT
editor-screenshot `level photo` — is deleted in S6. Capture the reference NOW:
- Author a throwaway one-room trunk carrying an asymmetric REAL texture on known faces, one face
  with authored non-zero `Pan`, one brush rotated 45°.
- Render it with today's `level photo` (shaded mode) and/or the game via uplayctl; store images +
  the face/texture/pan manifest in `dev/docs/spikes/2026-07-16-native-preview-anchor/` (committed —
  spikes are durable evidence; the trunk fixture too).
- No verdict yet — the comparison happens in S5 when the native render exists. This slice only
  banks the reference while it's cheap.
- ⚠️ Editor-driving: ephemeral container, tracked background job + long fallback timer per the
  background-work rules.

### S3 — SHOT grammar + pose math (`preview_shots.py`)
- Implement the in-game spec §3 token parser (`at:…;rot:…` / `look:` / `orbit:` / `name:`) —
  ALONGSIDE the old `parse_frame` (old stays until S6 cutover so the shipped verb keeps working
  between slices).
- Pure `pose_from_lookat(eye, target) -> (pitch, yaw)` and `pose_from_orbit(target, radius,
  azimuth, elev) -> (eye, pitch, yaw)` in degrees, eye-space (in-game spec §7 owns the same
  functions later — write them backend-agnostic).
- `@actor` resolution: brush → world-AABB centre (`writes.actor_bounds` path), point actor →
  `Location`; case-insensitive resolver; all-or-nothing validation.
- **A NEW `shot_filename` stem helper** (default `shot-01`-style zero-padded index stems, `name:`
  override, the `taken`/`-<k>` dedup + `_SLUG_SAFE` rules carried over). The old `frame_filename`
  is NOT touched — it is typed to the old `Frame` and still called by the live `preview_render.py`
  until S6, where both die together.
- **Tests:** every grammar form + malformed/old-grammar migration hint → exit-2 naming the token;
  look-at/orbit trig on known vectors incl. straight-down/up; `shot_filename` stem/dedup rules.

### S4 — `render.rs` + the `render_frame` FFI
- **FFI shape (flat buffers, mirroring `BrushTuple`'s style):**
  `render_frame(polys, textures, camera, size) -> bytes(RGB)` where `polys` is a flat list of
  world-space textured polygons — `(verts_flat, uv_base, uv_axis_u, uv_axis_v, pan, tex_index)` —
  covering BOTH world surfs and mover `extra_polys` (one shape, spec §5 plan-refinement 2). Python
  does all joins/frames; Rust only rasterizes. This keeps `render.rs` fully independent of the
  Model format and the build modules (concurrency contract §0).
- **Camera crosses the FFI as a BASIS, not angles** (spec §5 plan-refinement 3): Python computes
  forward/right/up via the GMath-verified `rotation.euler_to_matrix_uu` and passes
  `(location, basis, fov)`; Rust never converts angles, so the FRotator convention is
  single-sourced and no cross-implementation camera test is needed. Rust: perspective from
  `--fov`; near-plane polygon clip (~4 uu); z-buffer; perspective-correct UV (`u/w, v/w, 1/w`);
  nearest sampling, mip0, wrap; per-face Lambert-vs-headlight shading factor; `PF_Invisible`
  skipped Python-side before marshaling (no flags in the tuple).
- **Pin the `--fov` default** (spec §3's ⚠️ task lands HERE): read the substrate source for the
  first-person default (`PlayerPawn`/`DeusExPlayer` `DesiredFOV`), record the value + source cite
  in the code. Never from memory.
- **Tests (cargo):** projection round-trip; UV texel probe on a known quad; near-plane clip;
  z-buffer ordering. **Test (pytest, pixel-probe):** marker quad at a known world point renders at
  the oracle-projected pixel (guards the projection now that the basis is single-sourced).
- `maturin develop` + `bin/_venv.sh`'s existing source-hash rebuild covers the new file; verify.

### S5 — `preview_native.py` (orchestration) + golden + anchor verdict
- Trunk → brush inputs: own `_brush_inputs()` (NOT materialize's) — rotation passed through as
  GMath rot3x3; `MainScale`/`PostScale`/`SheerRate` non-identity → named exit-2; movers and point
  actors excluded from CSG input.
- `build_geometry` → `serialize_model` → `parse_model_body`; node-poly extraction (vert pool →
  points); §4.4 join (texture / pan / per-face flags, out-of-range → default grey); **Python UV
  frames** (`base_w = Location + R·(Origin − PrePivot)`, `axes_w = R·axes`, fallbacks per §5);
  texture decode via S1; checkerboard + one warning per distinct unresolvable ref; movers →
  world-transformed `extra_polys` at base pose via `rotation.actor_matrix`.
- Per shot: camera from S3 pose → `render_frame` → Pillow PNG into `--out-dir`.
- **Tests:** the §9 Python set — join guards, UV-frame unit tests (authored axes + rotated +
  PrePivot vs hand-derived; fallback paths), rotated-brush cross-check (Rust-transformed verts via
  a tiny probe build == `rotation.world_vertices`), mover-transform cross-check, checkerboard/warn,
  scale/sheer rejections, zero-brush trunk, `BuildError` surfacing, unwritable `--out-dir`
  (spec §7 requires a regression test PER named error path — cover them all, not a subset).
- **Anchor verdict (build gate):** render S2's fixture natively; compare against the banked
  reference; record U-direction / V-row-order / Pan-sign verdicts in the anchor spike doc; fix
  until they match. ONLY THEN bless the **golden image** (csg-golden **case c**
  `add_in_subtract` — subtract room + added pillar; NOT case a, a lone subtract with degenerate
  provenance — through `build_geometry`, synthetic asymmetric texture, exact-trig poses, 320×240,
  byte-exact on Linux/x86_64).

### S6 — CLI cutover + deletion + docs
- `cli.py`/`dispatch.py`: `--native` (default) / `--game` (reserved → exit-2 pointing at the
  2026-07-13 spec) / `--size` / `--fov`; backend-flag combination rejections (§3/§7); route
  `_level_preview`'s back half to `preview_native.render_shots`.
- DELETE/REWORK the full cutover surface (reviewer-enumerated — bigger than the three modules):
  `preview_render.py` + `MODE_INI`; in `preview_shots.py` — `parse_frame`, the old `Frame`
  dataclass, `OVERVIEW`/`_RESERVED`, `frame_filename`; in `cli.py` — the `--mode` flag + the
  `TARGET[:MODE][=NAME]` metavar/help block; in `dispatch.py` — the `overview_brush` wiring and the
  point-actor REJECTION (which the new grammar partially legalizes: `look:@pointactor` is valid);
  the ~8 preview tests in `test_dispatch.py` that monkeypatch `preview_render.render_shots` /
  assert old-grammar behavior get REWRITTEN against the native backend, not just deleted; the
  `preview_render` docstring mention in `normalize.py` (grep for the NAME, not just imports).
- Docs reconciliation (same commit): `architecture.md` `level photo` section (two backends,
  native pipeline, deletion note) + "Preview internals"; `docs/usage.md` preview section IF its
  rewrite hasn't landed (it carries a stale-warning banner — at minimum update the preview lines);
  `unrealed/rendering.md` gets a pointer that the editor-screenshot recipe is retired for `level
  photo` (recipe text stays — it documents editor behavior, still true for other drivers).
  (`direction.md` needs nothing — already reconciled to the 2026-07-16 decision and committed;
  verify it still matches at cutover.)
- Board: strike the built entry from `board/to-plan/`; `board/done/` tail note; new TODOs for anything
  deferred mid-build.

### S7 — Acceptance + perf
- Castle trunk (~90 brushes): batch of 8 shots (interior, exterior bird's-eye — the shot the old
  backend could never take, top-down, orbit ring) — eyeball pass, note anything off as inbox items.
  ⚠️ The castle trunk lives ONLY in wipeable scratch (`_scratch/castle/uedcli/maps/foobar`; the
  committed project trunk is 1 actor) — regenerate via the native-materialize spike harness
  (`spikes/2026-07-15-native-materialize/harness/build_native_castle.py`) if wiped, or use any
  comparable multi-brush trunk; don't let a scratch wipe stall acceptance.
- Measure wall-clock vs the ≤10 s soft target; record in the anchor spike doc. If missed, profile
  before optimizing (rayon rows is the known lever, spec §5).

---

## 2. Risks / watch-list

- **Pan sign/frame** — no repo ground truth until S5's anchor verdict; budgeted as a fix-loop, not
  an unknown (the reference is banked in S2 precisely so the loop is fast).
- **`f32` trig in the golden** — pinned to exact-trig poses + single-platform assertion (spec §9);
  if CI ever runs elsewhere, switch to a tolerance comparator.
- **Concurrent `lib.rs`/`dispatch.py` churn** — additive edits + plain merges (§0); re-run
  `bin/test` after any merge.
- **`orbit`/`look` gimbal cases** (straight up/down) — covered by S3 unit tests; the in-game spec
  §9 lists the same cases, keep the tests backend-agnostic so that tier inherits them.
- **Semisolid trunks** — the semisolid brush set flows through `build_geometry` (case-e parity is
  green), so the castle WITH ornament should photo even though materialize's MAP SAVE bug blocked
  the editor path; if a semisolid-specific render artifact shows up in S7, board it — don't chase
  it mid-build.

## 3. Done when

Every slice's tests are in the default offline suite and green (`bin/test`); **every spec §7 named
error path has a regression test** (not a subset); the anchor verdict is recorded; the golden is
blessed post-anchor; the editor preview path is deleted with no stray importers OR name references;
docs + board reconciled per S6; S7 acceptance shots recorded. The `--game` flag exists as a clean
reserved error; nothing in `uedcli/native/` or the Rust build/CSG modules has changed.
