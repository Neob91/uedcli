# Spec: textured faces for `actor preview` (`--faces wire|flat|textured`)

**Status:** specced, **not yet review-gated**. Next step is the spec review round (`CLAUDE.md`
"Review gates").
**Requested by:** the owner, 2026-07-26, session `uedcli:preview-textured`.
**Ephemeral:** scratch, per `CLAUDE.md`. On build, fold the outcome into
[`architecture.md`](../architecture.md) "Preview internals", [`docs/usage.md`](../../../docs/usage.md)
and [`docs/leveldesign/general/textures-and-surfaces.md`](../../../docs/leveldesign/general/textures-and-surfaces.md),
record the agent-side choices in [`rationale/preview.md`](../rationale/preview.md), and delete this file.

---

## 0. What this is, and what it is not

`actor preview` renders an **orthographic schematic** of a set of actors — model-side, host-only,
no editor and no container. Today it draws **wireframe only**. This spec adds two solid-face modes
to it, one of which samples each face's **real texture** through the face's own authored UV frame.

**It is explicitly NOT:**

- **Not a port of `actor preview` to Rust.** The owner deferred that (§2.6). The renderer stays
  pure-Python and stdlib-only, and the native extension stays **optional** — `bin/_venv.sh` warns
  and skips the native build when `cargo` is absent, and the native tests `importorskip`. Nothing
  in this spec may make `actor preview` fail on a machine without `cargo`.
- **Not a replacement for `level preview --native`.** That stays the *perspective, whole-level,
  post-CSG* tier. This is the *orthographic, per-actor, pre-CSG* tier. They answer different
  questions and both remain.
- **Not lighting.** No lightmaps, no `Engine.Light` contribution. The only shading is the fixed
  key-light term below, exactly as `--native` does it.

**Why it is worth building.** Every texture-frame defect in
[`spikes/levelbuild-friction/agent-reports.md`](../spikes/levelbuild-friction/agent-reports.md) —
mirrored lettering, the half-shifted sheet, the wrapped door trim, the cut-out texture on a solid
face — was **invisible in `actor preview`** and cost a full materialize + render cycle to see. Those
faults are all properties of the *authored* UV frame, which this tier reads directly.

## 1. The governing constraint: `preview.py` stays resolver-free and stdlib-only

Two existing invariants shape the whole design, and neither is negotiable here
([`architecture.md`](../architecture.md) "Preview internals"):

1. **`preview.py` is stdlib-only** — no PIL, no numpy.
2. **`preview.py` is resolver-free** — it never touches `config`, packages, or the search path.
   `dispatch.py` resolves and decodes; `preview.py` receives already-decoded pixels and draws them.

**This seam already exists and already carries texture pixels.** Point-actor sprites go through it
today: `dispatch._preview_render_data()` resolves via `utexture.TextureResolver` and hands
`preview.py` a `PointRender` whose `sprite` field is a decoded `(w, h, rgb, mask)` tuple, which
`preview._blit` draws. **Textured brush faces extend that same `render_data` channel** — they do not
open a new one.

## 2. Decisions (the owner's, 2026-07-26)

1. **The flag is an enum: `--faces {wire,flat,textured}`, default `wire`.** *Rejected: a boolean
   `--textured`* — it leaves no room for the `flat` tier without a second flag later, and
   `CLAUDE.md` "No back-compat cruft" means reshaping it would be a hard break rather than an
   addition. The enum also matches the existing `--brush-colors {csg,legend}` style.
2. **A textured face is shaded exactly as `level preview --native` shades it** (§4.1) — same
   key-light term, same nearest-neighbour texel fetch, same Euclidean wrap, same
   `DEFAULT_GREY` for an untextured face. *Rejected: unlit/full-bright sampling* — truer for reading
   a texture's own colour, but faces at different orientations stop being distinguishable and the
   two renderers would disagree about the same brush.
3. **Masked (index-0 cut-out) texels are HONOURED — they are not drawn, and whatever is behind
   shows through** (§4.3). *Rejected: rendering masked opaque like `--native`.* **This is a
   deliberate, single-axis divergence from decision 2, not an oversight**, and it has a real cost:
   `--native`'s documented "lie" about masking is what makes it a free cut-out detector (a masked
   texture shows its index-0 key as raw magenta), and `actor preview` will not inherit that. The
   detector remains available via `level preview --native`. Recorded so a later reader does not
   "fix" the divergence.
4. **All layouts accept `--faces`, with no size guard and no cost ceiling** (§7). *Rejected:
   restricting `textured` to `--layout single`; rejected: a soft `--size` ceiling.* The accepted
   risk is stated in §7 and is the owner's call.
5. **`flat` fills with the brush's CSG hue**, so it stays a *diagram* — see §4.4.
6. **Converting `actor preview` to Rust, and making the native extension non-optional, are
   DEFERRED** — out of scope here, and §10 records what would change if that is revisited.

## 3. CLI surface

One new option on `actor preview`, and on `stash preview` / `prefab preview` (they share
`dispatch._preview_opts`, so it lands on all three at once — deliberate: a stash/prefab is the same
kind of actor set).

```
--faces {wire,flat,textured}
```

**`help=` string** (per `CLAUDE.md`, it must say what it does, not restate the name):

> how brush faces are drawn (default `wire`). `wire` = outlines only, the schematic. `flat` = each
> face filled solid in its brush's CSG hue — a readable diagram of what occludes what. `textured` =
> each face filled by sampling its OWN texture through its authored UV frame (`Origin`/`TextureU`/
> `TextureV`/`Pan`), so texture alignment, panning, mirroring and tiling are visible offline — no
> editor, no container, no lighting. Point actors are unaffected.

**Not added:** no `--lit`, no `--no-wireframe`, no `--mip`. Each would be a flag that restates
something already decided (`CLAUDE.md` "Verbs compose"). Mip choice is automatic (§4.5).

## 4. The shape of a textured face — exact

### 4.1 Per-face shade

Computed **once per face**, in world space, matching `uedcli-native/src/render.rs`:

| Quantity  | Definition
|-----------|---
| `N`       | Newell normal over the face's **world** vertices (`preview_native._newell`) — NOT the stored `Normal`, per `t3d.md` "Winding defines the face, not `Normal`"
| `L`       | the fixed key light, `(-0.408, -0.577, 0.707)`, used **as authored and un-normalized** (its length is 0.9995, not 1 — matching byte-for-byte matters more than tidiness)
| `shade`   | `0.55 + 0.45 * abs(dot(N, L)) / length(N)`
| degenerate | `length(N) <= 1e-12` → the face is skipped entirely (zero area)

The `abs()` is load-bearing and is inherited deliberately: it makes the term robust to winding, so a
reversed face does not go flat.

### 4.2 Per-vertex UV

The authored frame, transformed to world space by **`preview_native._world_uv_frame(actor, poly)`**,
which is pure math over an `Actor` + `Polygon` and needs no CSG. **It moves to a shared module**
(§6) so `actor preview` and `level preview --native` cannot drift apart.

It returns `(base_w, tu_w, tv_w, pan)` where:

```
base_w = Location + R·(Origin − PrePivot)
tu_w   = R·TextureU          tv_w = R·TextureV
```

and per vertex `P`, per `t3d.md` "The UV convention" (✅, pinned by
`test_polyalign.test_engine_fact_uv_formula_is_base_relative_plus_pan`):

```
u = dot(P − base_w, tu_w) + pan[0]
v = dot(P − base_w, tv_w) + pan[1]
```

**The texel scale lives in the MAGNITUDE of `TextureU`/`TextureV`** — a unit `TextureU` is 1 texel
per world unit. There is no separate scale field. A missing or zero axis falls back to
`_tex_basis_default(N)`, exactly as `_world_uv_frame` already does.

**Interpolation is AFFINE, not perspective-correct.** This is the one genuine simplification an
orthographic camera buys: `render.rs` must carry `(1/d, u/d, v/d)` and divide per pixel, whereas
here `u`, `v` and depth are all linear in screen space, so plain barycentric interpolation is
**exact**, not an approximation. Any conformance test between the two renderers must compare an
ortho-equivalent pose, not an arbitrary one.

### 4.3 Per-pixel texel fetch

```
tx = floor(u) % tex_w          # Python % on ints == Rust i64::rem_euclid — verified identical
ty = floor(v) % tex_h          #   for positive divisors, which tex_w/tex_h always are
texel = rgb[(ty * tex_w + tx) * 3 : ... + 3]
```

Nearest-neighbour. No bilinear filtering — matches `render.rs` and keeps the pure-Python inner loop
to integer indexing.

Then, per decision 2.3, **masked texels are skipped**:

| Case                                    | Result
|-----------------------------------------|---
| `mask[ty * tex_w + tx] == 0` (index 0)  | **pixel not written at all** — the z-buffer is NOT updated either, so a face behind shows through the hole
| poly has no `Texture` (`texture is None`) | `DEFAULT_GREY = (128, 128, 128)`, then `× shade` — matches `render.rs`'s `tex_index < 0` path
| ref present but unresolvable            | the `render.rs` checkerboard, `× shade`, plus **one** stderr warning per distinct ref (§8)

Not updating the z-buffer on a masked texel is the whole point of honouring the mask — writing depth
for a hole would punch a same-shaped hole in everything behind it.

### 4.4 `flat` mode

Fill is `_CSG_PALETTE[classify_brush(actor)]`, which is a `(front, back)` RGB pair:

- face is front-facing for this view (`_is_front`) → the **front** colour
- otherwise → the **back** colour

**No key-light shade is applied.** `flat` is a schematic tier — a readable map of what occludes
what — and multiplying the CSG hue by a per-face factor would break the "this exact blue means
additive" cue that the palette exists to carry. *(Agent-side choice; goes to
`rationale/preview.md`.)*

Under `--brush-colors legend`, `flat` fills use the per-actor tint (`assign_tints`) instead of the
CSG pair, consistent with what that flag already means for the wireframe.

### 4.5 Mip selection

Sampling mip 0 of a 256×256 texture across a 12-pixel face is both slow and aliased. The mip is
chosen **per face, automatically**:

```
uu_per_px       = 1.0 / scale                       # `scale` is the framing px-per-world-unit
texels_per_px   = max(|tu_w|, |tv_w|) * uu_per_px
level           = clamp(floor(log2(max(texels_per_px, 1.0))), 0, len(mips) - 1)
```

`decode_texture` already decodes **all** mips into `TextureObj.mips`, and `mip0_to_rgb(mip, palette)`
is generic over any `Mip` despite its name — so this needs only a mip-selecting resolver method
(§6), not new decode work.

### 4.6 Visibility: a real z-buffer, no back-face culling

Brush volumes **interpenetrate by design** — a subtract sits inside the add it carves. A per-face
painter's sort is therefore wrong wherever two faces cross, so:

- one `float` depth buffer per pane, sized `size × size`, initialised to `+inf`
- `depth(P) = dot(P, _view_depth(iso_angle, view))` — the existing into-screen direction, where
  **smaller = nearer**; it interpolates affinely under ortho
- a pixel is written iff `depth < zbuf[i]`, and then `zbuf[i] = depth`
- **no back-face culling** in `flat`/`textured`: the z-buffer resolves visibility, and culling would
  wrongly hide the far interior wall of a subtract, which is exactly what a designer wants to see

`_is_front` keeps its current role — choosing the wireframe's shade pair and `flat`'s fill — and
gains no new one.

### 4.7 Draw order within a pane

Fills go **under** everything that exists today, so no current output element is obscured:

1. background (`BG = 224`, light grey)
2. point-actor underlays (`_draw_point_underlay`) — unchanged
3. **face fills + z-buffer (new)** — `flat` or `textured`
4. brush wireframe edges — unchanged, drawn **over** the fill
5. point markers/sprites, on-face poly decals, leader labels, `--show` overlays, legend — unchanged

**The wireframe still draws in `textured` mode.** It carries the CSG cue and the poly boundaries,
both of which a texture actively hides. *(Agent-side choice; `rationale/preview.md`.)*

## 5. Interaction with every existing option

| Option              | Behaviour under `--faces flat` / `textured`
|---------------------|---
| `--layout`          | all three (`quad`, `single`, `breakdown`) accept it — decision 2.4. `quad` renders fills in all four panes and so pays ~4× a single pane
| `--view`            | unchanged; the UV math is view-independent, only the projection and depth axis change
| `--iso-angle`       | unchanged; feeds `_view_depth` for the depth axis as it already does
| `--brush-colors`    | `csg` (default) → `flat` fills from `_CSG_PALETTE`; `legend` → `flat` fills from the per-actor tint. Under `textured` it affects only the overlaid wireframe, since fills come from the texture
| `--annotate`        | unchanged, drawn over the fill. **Legibility risk:** an on-face poly-index decal over a busy texture is harder to read than over flat grey. Not mitigated in v1 — noted in §9
| `--highlight`       | unchanged — highlighted polys keep their vivid, bolder outline, drawn over the fill
| `--focus BRUSH`     | **only the focused brush is filled**; every other brush recedes to the existing faint wireframe and is NOT filled. Filling the receded brushes would defeat the flag. *(Agent-side choice; `rationale/preview.md`)*
| `--show`            | unchanged, drawn after fills. These overlays are faint **solid** colours (the renderer has no alpha buffer), so over a textured fill they read as flat patches — same as they already do over the wireframe
| `--frame`/`--frame-tightness` | unchanged. Note framing sets `scale`, which feeds mip selection (§4.5), so a tighter frame legitimately selects a finer mip
| `--size`            | unchanged, and **uncapped** per decision 2.4
| `--from-t3d`        | works. Refs in the snippet resolve against the project's composed search path exactly as level actors do
| `--out`             | unchanged (always PNG)

**Point actors are entirely unaffected** by `--faces` — it is a brush-face option. Their sprites and
markers keep drawing as they do now.

## 6. Code shape

| Change                                                                     | Where
|----------------------------------------------------------------------------|---
| `_world_uv_frame`, `_tex_basis_default`, `_newell` move to a shared module (`texframe.py`) and are imported by BOTH `preview_native.py` and the new fill path | new `uedcli/texframe.py`
| `TextureResolver.resolve_mips(ref)` → `list[(w, h, rgb, mask)]` (all mips, masked), cached per resolver like `resolve`/`resolve_masked` | `uedcli/utexture.py`
| resolve each distinct face `Texture` ref, decode, build a face-render table; warn once per unresolvable ref | `uedcli/dispatch.py` (`_preview_render_data`)
| a `FaceTextures` payload alongside `PointRender` on the existing `render_data` channel | `uedcli/dispatch.py` → `uedcli/preview.py`
| `--faces` parsing + clean exit 2 on a bad value                              | `uedcli/cli.py`, validated in `dispatch`
| the scanline fill, z-buffer, mip pick and texel loop                         | `uedcli/preview.py`
| `--faces` threaded through `render_brushes_pgm` / `render_quad_pgm` / `_render_breakdown_grid` | `uedcli/preview.py`, `uedcli/dispatch.py`

**`preview.py` gains no import of `config`, `utexture` or `packages`** — the resolver-free invariant
(§1) holds. It receives decoded mip pyramids and draws them.

## 7. Cost, and the accepted risk

Measured on this box, LUM `basement` (28 actors), 2026-07-26:

| Render                                                             | Time
|--------------------------------------------------------------------|---
| `actor preview` quad @1024, wireframe, pure Python                  | **4.6 s**
| `level preview --native` @512², full CSG carve + textured raster, Rust | **0.68 s**

The pure-Python renderer is **already ~7× slower than the Rust one doing strictly more work**.
Wireframe cost is O(perimeter); a fill is O(area). At quad @1024 that is ~1M px per pane × 4 panes.

**The owner decided against any guard or ceiling (decision 2.4).** The accepted consequence,
recorded plainly: a large `--faces textured --layout quad --size 2048` render may take **tens of
seconds with no warning and no progress output**. That is the same silent-cost shape the friction
log complains about elsewhere, and it is a known, deliberate trade here. Mip selection (§4.5) is the
only cost control in v1, and it is a real one — it bounds texel fetches per pixel to ~1 regardless
of texture size.

## 8. Failure and degradation

| Situation                                       | Behaviour
|-------------------------------------------------|---
| bad `--faces` value                             | argparse choice error, exit 2
| a face's `Texture` ref does not resolve         | checkerboard fill + **one** stderr warning per distinct ref, naming the ref and suggesting `project show` — mirrors `preview_native._TextureTable`
| a face has no `Texture` at all                  | `DEFAULT_GREY × shade`, silently (a genuinely untextured poly is normal, not an error)
| texture resolves but is non-P8 / imported palette | `resolve_mips` returns `None` → treated as unresolvable (checkerboard + warning)
| **no project/config at all, so no resolver**    | see the open question in §11 — this is the one case where the fallback conflicts with a direction-level rule

## 9. Tests

| Test                                                                             | Guards
|-----------------------------------------------------------------------------------|---
| `--faces wire` output is **byte-identical** to today's render for a fixed scene    | the whole change is additive; this is the primary regression guard
| `u = (V − Origin)·TextureU + Pan` on a rotated, pre-pivoted brush                  | the UV convention, independently of `polyalign`'s own pin
| ortho Python vs `render.rs` on an ortho-equivalent pose: same texel index per pixel | the two renderers cannot drift (§4.2)
| Python `%` vs Rust `rem_euclid` over negative `u`/`v`                              | wrap conformance at the one place the languages could differ
| a face whose texture has index-0 texels leaves `BG` visible, and does NOT write depth | decision 2.3, including the z-buffer half that is easy to get wrong
| two overlapping brushes: the nearer face wins per-pixel                            | the z-buffer, and that painter's-sort was correctly rejected
| a subtract's far interior wall is drawn                                            | no back-face culling (§4.6)
| `flat` fill RGB == `_CSG_PALETTE[op][0/1]`, unshaded                               | decision 2.5
| unresolvable ref → checkerboard + exactly ONE warning for N faces sharing that ref  | the warn-once contract
| mip pick: a face at 8 texels/px selects level 3                                    | §4.5
| a golden PNG of a textured cube, blessed like `native_preview_golden.png`           | end-to-end pixel stability
| `--faces textured` runs with the native extension absent                            | §0 — the no-cargo machine must not break

## 10. Deferred (explicitly out of scope)

- **Porting `actor preview` to Rust / making the native ext non-optional.** If revisited, the
  natural shape is an ortho camera mode in `render.rs` plus a scene builder that takes raw brush
  polys instead of carved BSP nodes — §4.2's affine simplification would be given back, and
  `bin/_venv.sh`'s optional-native contract would have to change.
- **Bilinear filtering, real lighting, mesh rendering for point actors, translucency.**
- **A `texture list --cutout` filter** over the catalog's dominant-colour signal — a separate ask
  from the friction log, noted here only so it is not conflated with this work.

## 11. Open questions for the owner

1. **`--faces textured` with no project/config, so no `TextureResolver` at all.**
   `direction/conventions.md` "No silent half-answers" says a command that cannot fully satisfy a
   request should **exit 2 naming the offending value**, not emit a partial result with a stderr
   warning. Strictly applied, that means `--faces textured` outside a project is exit 2. But §8's
   per-ref fallback (checkerboard + warn) is itself a partial result, and it is what
   `level preview --native` already does. **Proposed:** exit 2 when there is no resolver at all
   (the request cannot be satisfied in any part), and keep checkerboard + warn-once for an
   individual miss (the render is still overwhelmingly the answer asked for). Needs a ruling
   because it interprets a direction-level rule.
2. **Should `--faces` also reach `level preview --native`** as the spelling for its render mode, so
   one flag name means one thing across both preview verbs? Not proposed here — it would change an
   existing verb's surface — but the naming collision is worth ruling on now rather than later.
