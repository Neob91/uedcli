# Native offline preview — `level preview --native` (design spec)

**Status:** draft (spec gate pending). Ephemeral per-feature scratch — once built, fold the durable
parts into `architecture.md` (+ any engine facts into `unrealed/*.md`) and keep the decisions in
`decisions.md`.

**Decisions captured (Andrzej, 2026-07-16):** see `decisions.md` entry
`2026-07-16 12:13 UTC — level preview becomes two-backend`. The choices + rejected alternatives live
there (durable), not here. Companion spec: board item `level-preview-game` (the `--game`
faithful tier — this spec shares its SHOT grammar and retires the same editor backend).

---

## 1. Problem / motivation

Every existing way to *see* a level costs a container:

- The shipped `level preview` boots an ephemeral **UnrealEd** per render mode, can only auto-frame
  a named brush from one canonical angle (free rotation never reaches the pixels — spike
  `2026-07-12-preview-pose-calibration`), and its lighting is unfaithful to the game.
- The planned `--game` tier (spec in board item `level-preview-game`) fixes fidelity and posing,
  but each preview still costs: materialize (editor boot, minutes when stale) + a game-container
  boot + travel. Right for hero shots and lighting judgment; too slow for the inner edit loop.

Meanwhile the native (editor-free) materialize line has produced, as by-products, every piece an
**offline software renderer** needs:

- **Carved geometry with no editor:** the Rust CSG/BSP core builds a level's real post-CSG surface
  set from the trunk in-process (`uedcli-native/src/{csg,build}.rs`, `lib.rs::build_geometry` —
  architecture.md "Native (editor-free) materialize"; differential-validated against editor goldens).
- **Pixel-exact texture decode:** the pure-Python `.utx`/UTexture decoder is byte-identical to
  `UCC batchexport` across the whole Deus Ex corpus (spike
  `2026-06-27-decontainerize-uedcli/01-native-texture-decode.md`, ✅ RESOLVED).
- **A working textured rasterizer harness:** the same spike series already renders a built `.dx`'s
  BSP surfs with real decoded textures to PNG
  (`spikes/2026-06-27-decontainerize-uedcli/harness/native_render.py` — top-down ortho only, but the
  surf→UV→texel path is proven).

**The fix:** promote those pieces into a first-class **draft preview backend** — `level preview`
(default `--native`) reads the trunk, carves it with the Rust CSG build, decodes the referenced
textures, and software-rasterizes freely-posed perspective stills in-process. **Zero docker, zero
editor, zero game** — seconds per batch. It complements (never replaces) `--game`: native answers
"did my edit look right" instantly; the game remains the faithful lit/sky/mesh ground truth.

---

## 2. Decisions (this spec implements)

All from `decisions.md 2026-07-16 12:13 UTC` (Andrzej):

| # | Decision |
|---|---|
| D1 | Native is a **draft tier complementing** the in-game preview (partially revises the 2026-07-13 rejection of an offline rasterizer: rejected as THE preview, accepted as draft). |
| D2 | **One verb, backend flags:** `level preview {--native\|--game}`; **`--native` is the default**; the editor-screenshot backend (`preview_render.py` + `TARGET[:MODE][=NAME]`) is **retired/deleted** when `--native` lands. `--game` = clean exit-2 "not built yet" until the in-game tier ships. |
| D3 | **Geometry = the Rust CSG build on the trunk, in-process.** The preview shows the CARVED world (BSP surfs), not raw brushes. N-2 residuals (un-merged coplanar fragments; missing zone splits) accepted — both invisible to a textured render. No `--from-dx` in v1 (rejected, can be added later). |
| D4 | **Pose grammar = the in-game spec's SHOT tokens, shared verbatim** (`at:…;rot:…` / `look:` / `orbit:`; 2026-07-13 spec §3). Same tokens work on both backends. |
| D5 | **Lighting: flat-textured v1; `--lit` is a scoped fast-follow** consuming the N-4 bake (§8). |
| D6 | **Rasterizer in Rust** (`uedcli-native`), Python orchestration, Pillow PNG encode. |
| D7 | **Promote the texture decoder** to a shipped `uedcli/utexture.py`. |
| — | `brush preview` texturing was considered and **DROPPED** (not deferred) — wireframe stays the brush-inspection look. |

---

## 3. CLI surface

```
uedcli level preview SHOT [SHOT ...] --out-dir DIR
                     [--native | --game]   # backend; --native is the default
                     [--size WxH]          # output resolution (default 1280x960, 4:3 — matches --game)
                     [--fov DEG]           # horizontal FOV (default: the game's first-person default)
```

- **SHOT tokens** are the in-game spec's §3 grammar, byte-for-byte (shared parser):
  `at:X,Y,Z;rot:PITCH,YAW[;name:STEM]`, `at:…;look:X,Y,Z|@ActorName`,
  `orbit:@ActorName;radius:R;azimuth:A[;elev:B]`. Angles in degrees; `rot` is `pitch,yaw` (no roll —
  the game tier forces a level horizon, D10 there; native matches so outputs stay comparable).
  All tokens validated up front, all-or-nothing, exit 2 naming the offending token. A token in the
  OLD `TARGET[:MODE][=NAME]` grammar → exit 2 with the migration hint (same rule as the in-game
  spec). `look:@x`/`orbit:@x` aim at a brush actor's **world-AABB centre** (its `Location` is the
  pivot, the wrong target), a point actor's `Location`; name resolution is the standard
  case-insensitive resolver.
- **`at:` is the camera position, verbatim.** Native has no pawn, so no eye-height arithmetic at
  all. (The `--game` tier's `Screenshot` verb owns the single `BaseEyeHeight` subtraction so its
  eye also lands exactly at `at:` — the two backends agree by construction.)
- **Pitch is NOT artificially clamped on native** (the engine's ≈±98.9° clamp is a game-tier
  reality, documented in `--help`; native renders true straight-down/up). Full ±90° covers all
  real use.
- **`--fov`**: horizontal field of view, **native-only in v1**. Default = the game's first-person
  default so `--native` and `--game` compose comparably. ⚠️ *Build-time task:* pin the substrate's
  actual default from the game source (`PlayerPawn`/`DeusExPlayer` `DesiredFOV`) — do NOT trust a
  remembered value; record it in the code with the source cite. `--fov` combined with `--game` is
  rejected exit-2 (the 2026-07-13 spec defines no FOV mechanism; lift when/if that tier grows one).
- **`--game`-tier-only flags** (`--map`, `--rebuild`, `--keep-alive` from the 2026-07-13 spec) are
  rejected with a clean exit-2 ("--map requires --game") when combined with `--native`; they land
  with that tier's build.
- Output naming: reuse `preview_shots.frame_filename`'s stem/dedup RULES via a **new SHOT-token
  stem helper** (the old function is typed to the retired `Frame` and produces target/mode stems —
  it goes with the editor path at cutover; only its dedup semantics survive) (default stem =
  `shot-01`, `shot-02`, …; `name:STEM` overrides; never silently overwrites) — same as the in-game
  spec.

**Verbs unaffected:** `brush`/`stash`/`prefab preview` (the offline PPM/P6 wireframe) stay exactly
as-is; `level doctor` remains the lint surface. The render-mode taxonomy stays dropped (decision
2026-07-13 20:38) — native has one draft look (v1 flat-textured; later `+ --lit`).

---

## 4. Pipeline (the `--native` backend)

```
trunk ──► brush transform ──► Rust CSG build ──► surf→texture join ──► decode textures ──► rasterize N shots ──► PNGs
(read)    (world-space)       (build_geometry)    (Python)             (utexture.py)        (render.rs)          (Pillow)
```

1. **Read + validate.** Resolve project + selected level, `TrunkLevelSource.load()`. Parse all SHOT
   tokens up front (shared parser + the pure `pose_from_lookat`/`pose_from_orbit` trig from the
   in-game spec §7 — model-side, unit-tested, shared by both backends).
2. **Brush transform.** Each CSG brush actor → the **existing, unmodified** `BrushTuple`
   flat-buffer form `build_geometry` takes. (Authored texture axes deliberately do NOT ride this
   tuple — the UV frame is computed Python-side from the source polys instead; §5 plan refinement.)
   Two deliberate divergences from `materialize._build_brush_input`:
   - **Rotation IS passed through** (the GMath rot3x3 from `rotation.euler_to_matrix_uu` into
     `FPoly::Transform`'s rot parameter). Materialize gates on identity rotation (`BuildError`,
     `materialize.py::_build_brush_input`) because its output must be editor-parity; a DRAFT
     preview of a rotated brush beats an error. The transform is validated offline against the
     GMath-verified Python path (§9), not editor goldens.
   - **Scale/sheer are checked HERE, explicitly:** non-identity `MainScale` **or `PostScale` or
     `SheerRate`** → named exit-2 (actor + field). NB materialize today checks only `MainScale`
     and silently ignores `PostScale`/`SheerRate` (reviewer finding — boarded as its own inbox
     item); preview must not inherit that hole. The scale-support spec lifts this later for both.
3. **CSG build.** `uedcli_native.build_geometry(brushes)` carves the world (N-1 core;
   architecture.md). `BuildError` → clean exit 2. Then `serialize_model` → `umodel.parse_model_body`
   → the `Model` (nodes/surfs/verts/points/vectors) — the same bytes-across-FFI shape materialize
   uses (no new FFI geometry types).
4. **Surf→texture join (Python).** A freshly built surf carries `i_actor` = source-brush index and
   `i_brush_poly` = source-poly index (this is exactly what `assemble._patch_surf_refs` consumes at
   materialize), so the texture NAME for each surf is `brushes[i_actor].polys[i_brush_poly].texture`
   — plus that poly's `PanU/PanV` (Pan lives on the source FPoly and is DROPPED from the built surf
   — see §5 UV note) and that poly's authored per-face `Flags` (which also don't survive into the
   built surf: `BrushTuple` carries one brush-level `poly_flags`, so per-face skip/render decisions
   in §5 read the SOURCE poly's flags via this join, never the built surf's). **Guard the join like
   `_patch_surf_refs` does:** an out-of-range/`-1` `i_actor`/`i_brush_poly` (the build emits such
   surfs) → the flat default grey, never an `IndexError`. No package assembly, no import tables.
5. **Texture decode** (`uedcli/utexture.py`, promoted from the proven spike decoder). Resolve each
   referenced `Package[.Group].Name` against the **composed config search path**
   (`config.composed_search_files` — project overlay shadows game base, same as materialize), decode
   mip0 + palette → RGB. Decoded per-package results cached in-memory for the invocation.
   A **bare (unqualified) `Texture=name`** is treated as unresolvable (checkerboard + a warning
   suggesting qualification) — consistent with `assemble._patch_surf_refs`, which also resolves
   dotted refs only; a cross-package stem scan would be ambiguous.
   **Unresolvable/undecodable ref → that face renders as a magenta/black checkerboard + ONE stderr
   warning per distinct ref naming it** *(AI-proposed default — Andrzej expressed no preference; a
   draft preview should always produce an image, and the placeholder makes the miss visible in the
   render itself; revisit if wrong)*. A face with **no texture set** renders in the flat default
   grey.
6. **Rasterize** (`uedcli-native/src/render.rs`, §5): per shot, Rust renders an RGB framebuffer;
   Python encodes PNG via Pillow (the existing sole third-party dep) into `--out-dir`.

**No cache, no freshness key:** the build is in-process and takes seconds; every invocation renders
the trunk as it is right now. (The `--game` tier's `.dx` freshness cache is that tier's concern.)

---

## 5. The rasterizer (`render.rs`)

A deliberately boring software renderer — draft tier, correctness of *placement/texture*, not
engine-look parity:

- **Input (FFI) — *plan refinement 2 (2026-07-16, planning pass):* flat world-space textured
  polygons, not Model bytes.** Python (which already parses the Model via
  `umodel.parse_model_body`) extracts each node's polygon from its vert pool
  (`verts[i_vert_pool + k].i_vertex → points[]`) and marshals ONE flat list covering world surfs
  AND mover `extra_polys` alike: `(verts_flat, uv_base, uv_axis_u, uv_axis_v, pan, tex_index)` —
  plus a texture table (`[(w, h, rgb_bytes)]`), camera (below), and `(width, height)`.
  **Output:** `width×height×3` RGB bytes. This supersedes the earlier "serialized Model bytes /
  `Built` handle" phrasing: Rust only rasterizes and stays fully independent of the Model format
  and the build modules — the concurrency win the plan's §0 contract needs. (`PF_Invisible` faces
  are dropped Python-side before marshaling.)
- **Authored texture axes MUST drive the UV frame (reviewer finding).** The current `BrushTuple`
  carries no per-poly `TextureU/TextureV`, so `build.rs::alloc_surf` always synthesizes
  `default_texture_axes` — which, worse, differ from `builders._tex_basis`'s authored default by a
  90° in-plane rotation. Rendering from the built surf's texture vectors would therefore be wrong
  for every authored alignment. **Plan refinement (2026-07-16, planning pass):** the preview does
  NOT read the built surf's texture vectors at all — the §4.4 join already reaches the SOURCE poly,
  which carries the full authored frame (`Origin`, `TextureU/V`, `Pan` — `model.Polygon`), so
  **Python computes each surf's world UV frame** (`base_w = Location + R·(Origin − PrePivot)`,
  `axes_w = R·axes`; missing `Origin` → local zero; missing/zero axes → a Python default matching
  `builders._tex_basis`) and passes it per-surf to the rasterizer. This is MORE correct than the
  built-surf route (Pan never survives the build anyway), unifies world surfs with the mover
  `extra_polys` path, and — deliberately — **avoids editing `lib.rs`'s `BrushTuple` /
  `build.rs` / `fpoly.rs`, which a concurrent agent is actively working in.** *(The `BrushTuple`
  axes FFI extension remains boarded as the NATIVE-MATERIALIZE fidelity fix — the materialized
  `.dx` loses authored alignment — in that work's lane, not this build's.)*
- **Camera:** right-handed UE world (Z up). **The angle convention is NOT ours to choose — it must
  match the engine FRotator semantics** the SHOT tokens are defined in (yaw about Z via `Rz`,
  pitch/roll sin-flipped, order `Rz·Ry·Rx` — spike `2026-06-19-frotator-convention.md`).
  *Plan refinement 3 (2026-07-16, planning pass):* rather than re-deriving that convention in Rust
  and policing it with a cross-implementation test, **Python computes the camera basis** (via the
  GMath-verified `rotation.euler_to_matrix_uu`) **and passes `(location, forward/right/up, fov)`
  across the FFI** — Rust never turns angles into a matrix, so a convention mismatch between the
  tiers is impossible by construction (single-sourced), and no camera-probe FFI is needed. Rust
  does perspective projection from `--fov` and a near-plane clip (e.g. 4 uu) so geometry
  behind/straddling the camera is clipped, not wrapped; a pixel-probe sanity test (§9) guards the
  projection itself.
- **Visibility: z-buffer, no BSP walk.** Rasterize every marshaled polygon (fan-triangulated
  Rust-side; the vert-pool extraction happens Python-side per the input bullet) with a per-pixel
  depth test. The BSP
  *could* give exact front-to-back order, but a z-buffer is simpler, order-independent, and immune
  to the N-2 residuals. No backface cull (BSP node polys are effectively single-sided per node;
  culling risks holes on the draft tier for no visual gain).
- **UV per vertex:** `U = (P − points[p_base]) · vectors[v_texture_u] + PanU`,
  `V = (P − base) · vectors[v_texture_v] + PanV` — texel units, wrap by texture size. Evidence
  honesty: the **pan-free part** of this frame is what `native_render.py` proved renders correctly
  (t3d.md "Polygon" grammar documents `TextureU/V` world axes + `Pan U= V=` as authored fields);
  the **Pan term's SIGN and frame have NO ground truth in this repo yet** — the harness omits Pan
  entirely, and nothing else pins it. **Build gate: pin Pan (sign + which frame it offsets in)
  against a live reference** — one asymmetric texture, one authored `Pan`, compared against an
  editor/game render — recorded in the build's spike dir BEFORE the golden is blessed (§9). A
  wrong sign would pass every self-referential test.
- **Sampling:** nearest, mip0 only, **perspective-correct** interpolation (interpolate `u/w, v/w,
  1/w` per pixel — affine warps visibly on the large wall polys a level is made of).
- **Shading (v1 "flat"):** texel × a per-face brightness factor from the face normal vs a fixed
  headlight/key direction (e.g. `0.55 + 0.45·max(0, N·L)`) so adjacent same-texture faces read as
  distinct 3-D shapes. No lightmaps in v1 (D5).
- **PolyFlags** (read from the SOURCE poly via the §4.4 join — per-face flags never reach the
  built surf): skip `PF_Invisible` faces only. **Textured `PF_Portal` sheets RENDER like any other
  face** (opaque, v1) — a blanket portal-skip was reviewed and rejected: a water surface is a
  translucent textured portal sheet and IS visible in-game (the repo's own moat water:
  `board/inbox/` "Zone-portal / water authoring", 2026-07-12), so skipping portals would blank every
  water surface. Translucent/masked/modulated render **opaque** in v1 (draft-tier simplification,
  noted in `--help`). *(AI-proposed defaults — flag for review.)*
- **Movers** are out of world CSG (architecture.md "Mover support"), so they have no BSP surfs.
  v1 renders each mover **directly** via the `extra_polys` FFI input: **Python** transforms the
  mover's brush polys to world space at the BASE pose using the verified model-side path
  (`rotation.actor_matrix` — `Location + R·(v − PrePivot)`, the same math every measurement verb
  uses), rotates the authored texture axes with the same matrix, and passes flat world-space
  textured polys `(verts, texture_u, texture_v, pan, tex_index, flags)`; Rust rasterizes them
  z-buffered against the world with the same UV/shading rules. A draft preview without doors would
  be actively misleading. Scaled movers hit the same §4.2 scale rejection as any brush.
  *(AI-proposed — flag for review.)*
- **Not rendered in v1:** point actors (no native mesh decoder yet — the tracked p3 spike;
  lights/PlayerStart simply don't appear), sky boxes (a `PF_FakeBackdrop` surf renders its texture
  like any other face; no sky-zone projection), dynamic anything.
- **Background** (pixels no surf covers — possible when the camera exits the carved space): a flat
  dark grey, visibly distinct from black (black reads as "render broke" — the historical black-
  viewport trap).
- **Determinism:** pure function of inputs; no threading in v1 (a single frame at 1280×960 is
  small; rayon can shade rows later if profiling asks).

**Perf target (soft):** castle-scale trunk (the dogfood castle is ~90 brushes / 161 actors): build
+ 8 shots at 1280×960 in **≤ 10 s** end-to-end host-native. (The CSG core was ported to Rust
precisely because CPython missed such targets; rasterizing ~1.2 MP × 8 is trivial by comparison.)

---

## 6. Module layout / what changes

- **New:** `uedcli/utexture.py` (promoted decoder — same API as the spike harness:
  `load_package`/`decode_texture`/`decode_palette`/`mip0_to_rgb`; the spike file stays put as
  evidence), `uedcli/preview_native.py` (orchestration §4), `uedcli-native/src/render.rs` + a
  `render_frame(...)` FFI entry beside `build_geometry`/`serialize_model`/`bake_lighting` (an
  **additive** `lib.rs` registration — the `BrushTuple` shape and the build/CSG modules are NOT
  touched; see the §5 plan refinement and the plan's concurrency contract).
- **Changed:** `cli.py` (`level preview` grows `--native`/`--game`/`--size`/`--fov`, SHOT
  positionals), `dispatch._level_preview` (front half: parse/validate/resolve poses — shared with
  the future `--game`; back half: route by backend), `preview_shots.py` (SHOT-token parser +
  `pose_from_lookat`/`pose_from_orbit` replace `parse_frame`; a new SHOT-token stem helper
  carries `frame_filename`'s dedup rules, the old function is deleted with the editor path).
- **Deleted (D2):** `preview_render.py`, `MODE_INI`, the `TARGET[:MODE][=NAME]` grammar, and their
  editor-boot plumbing. (The in-game spec §7 lists the same deletions — whichever tier lands first
  performs them; this one is landing first.)
- **Docs on land:** `architecture.md` `level preview` section rewritten (two backends);
  `direction.md` preview paragraph reconciled (draft tier + faithful tier); board entries moved.

---

## 7. Errors (no traceback, ever)

Named exit-2 paths, each with a regression test: no project / no selected level (existing); bad
SHOT token (names the token); unknown `@actor` (names it); scaled/sheared brush — `MainScale`,
`PostScale`, **or** `SheerRate` non-identity (names the actor + field + the scale-support
deferral); `BuildError` from the CSG core (surfaces Rust's message); zero-brush trunk ("nothing to
render"); unwritable `--out-dir`; `--game` ("in-game tier not built yet — see
board item `level-preview-game`"); `--map`/`--rebuild`/`--keep-alive`/`--fov` without
their backend. **A ROTATED brush is NOT an error** (deliberate divergence from materialize's
identity-rot gate — §4.2); missing texture is a WARNING + checkerboard, not an error (§4.5).

---

## 8. `--lit` fast-follow (scoped now, built after v1)

Consume the N-4 bake in-process: `bake_lighting(built, lights)` fills per-surf `FLightMapIndex`
(Pan/UScale/VScale/USize/VSize) + 1-bit-per-lumel visibility masks + per-surf light lists (spike
section `20-lighting-bake.md` §3/§4, PROVEN byte-format-correct). **The lumel grid lives in the
RAW dot-product frame, NOT §5's panned texel frame** (reviewer finding): the bake defines
`LMPan.X = Umin − 0.125` with `Umin = min over verts of vertex·TextureU` — no `p_base`
subtraction, no poly-Pan term (spike §4). So the per-pixel lookup is
`lm_u = (P·TextureU − LMPan.X) / UScale` (raw world-point dot, pan-free); feeding §5's texel `U`
in would double-offset by `(base·Tu − PanU)` and shift every lightmap. Then: sample each
participating light's visibility bit (bilinear over the 1-bit mask for softness), accumulate
`Σ visible_i × brightness_i × hue_i` with distance falloff, and multiply into the texel. This is an
*approximation* of the engine's light application (the software renderer's saturation/palette
behavior is not reproduced) — the faithful reference stays `--game`. Light participation/radius
comes from `materialize._participating_lights` (the tracked CDO-default heuristic caveat applies).
Nothing in v1's FFI shape blocks this: `render_frame` grows optional lightmap arrays.

**The former in-game lit-render blocker is RESOLVED anyway** (board, 2026-07-16: root cause was the
`FBspSurf` `iLightMap`/`iActor` on-disk field-order swap, fixed in the serializers) — and it never
gated this path regardless: `--lit` consumes the bake's arrays directly in our own renderer and
never round-trips through the map file.

---

## 9. Tests (fully offline — that's the point)

- **Unit (Python):** SHOT grammar (all forms; malformed/old-grammar → exit 2 naming the token —
  shared with the future `--game`); `pose_from_lookat`/`orbit` trig (known vectors → known angles,
  straight-down/up); surf→texture join on a seeded two-brush trunk (i_actor/i_brush_poly mapping,
  Pan + per-face Flags carried, **out-of-range owner → grey not IndexError**); bare-ref →
  checkerboard; `utexture.py` decode vs a committed tiny fixture package (pixel-exact assertion —
  port the spike's comparator once, freeze the PNG bytes); checkerboard + single-warning path;
  every §7 error path (incl. PostScale/SheerRate rejection); flag-combination rejections.
- **Cross-implementation oracles (the anti-self-reference tests — both reviewers' core point):**
  - *Camera convention:* single-sourced by construction (plan refinement 3 — Python passes the
    `euler_to_matrix_uu`-derived basis across the FFI; Rust never converts angles). The residual
    risk is the projection, guarded by a **pixel-probe test**: place a marker quad at a known
    world point, render, assert the oracle-projected pixel is the one hit.
  - *Rotated-brush transform:* Rust-transformed world verts (rot3x3 through `FPoly::Transform`)
    == Python `rotation.world_vertices` on a rotated + PrePivot'd fixture brush. This is the
    validation that lets preview pass rotation through where materialize still gates (§4.2).
  - *Mover transform:* the Python `extra_polys` world transform for a base-rotated mover ==
    `rotation.world_vertices` on the same actor.
- **Unit (Rust, `cargo test`):** projection round-trip (a known world point → expected pixel);
  perspective-correct UV on a known quad (assert exact texel indices at probe pixels); near-plane
  clip (camera inside geometry doesn't wrap); z-buffer (near face wins).
- **Unit (Python, UV frames):** authored axes honored — for a brush with non-default
  `TextureU/V`+`Origin`, rotated + PrePivot'd, the computed world UV frame matches hand-derived
  values; missing `Origin`/axes fall back as §5 defines (zero origin / `_tex_basis`-matching
  default).
- **Golden image:** a small REAL brush-list fixture pushed through `build_geometry` (e.g. the
  csg-golden **case c** `add_in_subtract` — a subtract room + an added pillar; case a is a LONE
  subtract, useless for multi-brush provenance — NOT `build_carved_box_package`, which is the
  direct-Model M0 path with no brushes and no `i_actor`/`i_brush_poly` provenance, so it cannot
  exercise this pipeline), synthetic asymmetric 4-texel texture, two fixed poses **at exact-trig
  angles (0°/90°)** to dodge cross-platform `f32` trig drift; assert the PNG **pixel buffer**
  byte-exact on the dev platform (Linux/x86_64 — the only supported platform per spike 40), with
  the bless script printing a diff count on mismatch. Small resolution (e.g. 320×240).
- **One-time LIVE anchor (required build gate, before the golden is blessed):** render one simple
  room carrying an asymmetric REAL texture with an authored non-zero `Pan`, natively AND via a real
  engine render (the still-present editor `level preview` before its deletion, or the game via
  uplayctl), and record the comparison (images + verdict on U direction, V row order, Pan
  sign/frame) in `dev/docs/spikes/2026-07-16-native-preview-anchor/`. This pins exactly the three
  things no self-referential test can (Pan sign — §5 gate; V-flip; axis direction). Without it a
  systematically flipped render passes the whole suite.
- **No recurring integration tests** — no container anywhere in the backend. (Human eyeballing on
  the castle trunk is the acceptance pass; `--game`, when built, is the ongoing fidelity
  comparator.)

---

## 10. Out of scope / deferred

- **`--lit`** (§8 — scoped fast-follow, not v1).
- **Meshes/decorations/point-actor markers** (needs the native mesh decoder — tracked p3 spike).
- **Sky-zone projection, translucency blending, masked textures** (render opaque; draft tier).
- **`--from-dx`** (rejected for v1 — decisions.md; revisit for materialize debugging / retail-map
  study alongside `level import`).
- **`brush preview` texturing** — DROPPED (Andrzej, decisions.md 2026-07-16).
- **Scaled brushes** — rejected with a named error until the scale-support spec lands (then both
  materialize and preview lift together).
- **The `--game` tier itself** — its own spec (board item `level-preview-game`); this build
  must leave the shared front half (grammar, pose math, filename rules) in the shape that spec's §7
  expects.
