# Spec: textured faces for `actor preview` (`--faces wire|flat|textured`)

**Status:** ⛔ **PARKED AGAIN — re-entry round returned a STRUCTURAL finding.** The masking spike is
complete and its blocker cleared, but a second cold round (2026-07-26, 3 fresh Opus reviewers) found
that this spec is designed against a `TextureResolver` API that a **reviewed, on-deck `p1` item is
about to delete**. Per `CLAUDE.md` "Review gates" a structural finding replaces the remaining round,
does **not** pass the gate, and parks the work for an owner ruling. **Do not plan or build from this
document.** The blocker is §12; the detail defects the same round found are §13 and must be fixed in
the same revision — deliberately NOT fixed yet, because the §12 ruling may change what `resolve_mips`
should even be.
**Requested by:** the owner, 2026-07-26, session `uedcli:preview-textured`.
**Ephemeral:** scratch, per `CLAUDE.md`. On build, fold the outcome into
[`architecture.md`](../architecture.md) "Preview internals", [`docs/usage.md`](../../../docs/usage.md)
and [`docs/leveldesign/general/textures-and-surfaces.md`](../../../docs/leveldesign/general/textures-and-surfaces.md),
record the agent-side choices in [`rationale/preview.md`](../rationale/preview.md), and delete this file.

---

## 0. What this is, and what it is not

`actor preview` renders an **orthographic schematic** of a set of actors — model-side, host-only, no
editor and no container. Today it draws **wireframe only**. This spec adds two solid-face modes, one
of which samples each face's **real texture** through the face's own authored UV frame.

**It is explicitly NOT:**

- **Not a port of `actor preview` to Rust.** Deferred (§2.9). The renderer stays pure-Python and
  stdlib-only, and the native extension stays **optional** — `bin/_venv.sh` warns and skips the
  native build when `cargo` is absent, and the native tests `importorskip`. Nothing here may make
  `actor preview` fail on a machine without `cargo`.
- **Not a replacement for `level preview --native`.** That stays the *perspective, whole-level,
  post-CSG* tier; this is the *orthographic, per-actor, pre-CSG* tier.
- **Not lighting.** No lightmaps, no `Engine.Light` contribution — only the fixed key-light term
  in §4.1.

**Why it is worth building.** Every texture-frame defect in
[`spikes/levelbuild-friction/agent-reports.md`](../spikes/levelbuild-friction/agent-reports.md) —
mirrored lettering, the half-shifted sheet, the wrapped door trim, the cut-out texture on a solid
face — was **invisible in `actor preview`** and cost a full materialize + render cycle to see. Those
faults are properties of the *authored* UV frame, which this tier reads directly.

## 1. The governing constraint: `preview.py` stays resolver-free and stdlib-only

Two existing invariants, neither negotiable ([`architecture.md`](../architecture.md) "Preview
internals"):

1. **`preview.py` is stdlib-only** — no PIL, no numpy.
2. **`preview.py` is resolver-free** — `dispatch.py` resolves and decodes; `preview.py` receives
   already-decoded pixels and draws them.

The seam already exists and already carries texture pixels: point-actor sprites resolve in
`dispatch._preview_render_data()` and reach `preview._blit` as a decoded `(w, h, rgb, mask)` tuple.
Textured faces extend that same `render_data` channel (§6).

## 2. Decisions (the owner's, 2026-07-26)

1. **`--faces {wire,flat,textured}`, default `wire`.** *Rejected: a boolean `--textured`* — no room
   for the `flat` tier without a second flag later, and "No back-compat cruft" makes reshaping a hard
   break. Matches the existing `--brush-colors {csg,legend}` style.
2. **A textured face is shaded as `level preview --native` shades it** (§4.1) — same key-light term,
   nearest-neighbour fetch, Euclidean wrap, `DEFAULT_GREY` for an untextured face. *Rejected:
   unlit/full-bright sampling.* Every divergence from `--native` is deliberate and enumerated in
   §4.9 — nothing diverges by accident.
3. **Cut-outs are honoured, but ONLY on a genuinely masked face** (§4.3). A face masks iff its poly
   carries `PF_Masked` (`0x2`) **OR** its texture was imported masked — per `unrealed/quirks.md`
   (🔬 2026-07-26): *"`Masked` is a property of the TEXTURE, set at import — and a texture's flags are
   OR'ed into every surface it is applied to."* *Rejected: masking every index-0 texel unconditionally*
   (spec review round 1 measured `LUM_InfoPortraits.ArthurCallaway` using index 0 as **real black at
   2.2 % of texels** — that face would have rendered shot through with holes); *rejected: rendering
   masked opaque like `--native`* (the owner wants the true cut-out). **The texture-side half is
   BUILD-BLOCKED on a spike — §11.**
4. **All layouts accept `--faces`, no size guard, no cost ceiling** — **re-affirmed 2026-07-26 against
   the corrected figures** in §7 (the first ruling was taken against numbers that were wrong by 4×,
   and omitted `--layout breakdown` entirely). *Rejected: rejecting `textured` under `breakdown`;
   rejected: a stderr cost warning past a pixel budget.*
5. **`textured` draws NO wireframe; `flat` KEEPS its wireframe** (§4.6). *Rejected: a wireframe under
   textured; rejected: dropping it from both.* Accepted consequence: under `textured` two abutting
   brushes sharing a texture are indistinguishable, and the CSG-op colour cue is absent.
6. **`--faces textured` with no usable texture resolver is a clean exit 2 naming the actual cause**
   (§8). *Rejected: checkerboarding every face; rejected: silently falling back to `flat`.*
7. **`--brush-colors` combined with `--faces textured` is a clean exit 2** — **re-affirmed
   2026-07-26 after its original rationale was refuted.** The first ruling said the flag "would do
   nothing"; that is **false** — `preview._scene_geometry` derives `vivid`, the `--highlight` outline
   colour, from it. The ruling stands on the corrected ground that the flag's *documented job* is
   colouring the wireframe, and silently repurposing it to mean "highlight hue" under one mode would
   give one flag two jobs. *Rejected: accepting it as the highlight-hue selector.*
8. **`level preview` is NOT changed** — it keeps `--native`/`--game` (which *backend*); `--faces` is
   *how faces are drawn*. *Rejected: unifying the spelling.*
9. **The Rust port and a non-optional native extension are DEFERRED** (§10).
10. **A subtract brush's faces render ONLY from inside the subtracted volume** (§4.7) — *"the
    subtract's polys looked at from OUTSIDE do not render in UnrealEd or in game, and they should not
    render here"* (owner, 2026-07-26). Under an orthographic camera, which is always outside, this
    means **cull a subtract's camera-facing polys and draw its far ones**. This is what makes an
    additive brush inside a subtracted room visible, and it dissolves review round 1's structural
    finding S2 rather than patching it.

Also decided and folded in: `--focus` keeps every brush filled with non-focused ones dimmed (§4.8);
`--highlight` is the only *deliberate* line art under `textured` (§5); on-face decals are left as they
are (§5); `flat` fills are unshaded (§4.5); all three preview verbs get the flag (§3).

## 3. CLI surface

One option, on `actor preview`, `stash preview` and `prefab preview` — they share
**`cli._preview_opts`**, and a stash or prefab is the same kind of actor set.

```
--faces {wire,flat,textured}
```

**`help=`:**

> how brush faces are drawn (default `wire`). `wire` = outlines only, the schematic. `flat` = each
> face filled solid in its brush's CSG hue, wireframe kept — a diagram of what occludes what.
> `textured` = each face filled by sampling its OWN texture through its authored UV frame
> (`Origin`/`TextureU`/`TextureV`/`Pan`), with NO wireframe, so alignment, panning, mirroring and
> tiling are visible offline — no editor, no container, no lighting. Under `flat`/`textured` a
> subtract brush shows only its far (interior) faces, so geometry inside a subtracted room stays
> visible. Point actors are unaffected. `textured` rejects `--brush-colors` and scaled brushes, and
> needs resolvable textures.

**Two existing `help=` strings must be corrected in the same change** (`CLAUDE.md` requires help to
say what a flag actually does):

- `--brush-colors` — currently "how to colour **the wireframe**"; it also drives `flat` fills and is
  a hard error under `textured`.
- `--focus` — currently "every OTHER brush recedes to a faint (dimmed) **wireframe**"; under
  `flat`/`textured` they recede as dimmed *fills*.

**Not added:** no `--lit`, no `--no-wireframe`, no `--mip`.

## 4. The shape of a face — exact

### 4.1 Per-face shade (`textured` only)

| Quantity   | Definition
|------------|---
| `N`        | Newell normal over the face's **world** vertices — NOT the stored `Normal`, per `t3d.md` "Winding defines the face, not `Normal`"
| `L`        | the key light `(-0.408, -0.577, 0.707)`, used **as authored and un-normalized** (`|L|` = **0.99962**)
| `shade`    | `0.55 + 0.45 * abs(dot(N, L)) / length(N)`
| degenerate | `length(N) <= 1e-12` → face skipped (zero area)

The `abs()` is inherited deliberately: it makes the term robust to winding.

**Precision is pinned:** compute in Python `float` (f64) and convert with **truncation**,
`min(int(c * shade), 255)`, matching `render.rs`'s `(c * shade).min(255.0) as u8`. `render.rs` is f32
throughout, so byte-identity with `--native` is **not** claimed (§4.9); truncation is specified so
two implementers agree with each other.

### 4.2 Per-vertex UV

From **`texframe.world_uv_frame(actor, poly)`** (§6), returning `(base_w, tu_w, tv_w, pan)`:

```
base_w = Location + R·(Origin − PrePivot)          tu_w = R·TextureU     tv_w = R·TextureV
u = dot(P − base_w, tu_w) + pan[0]                 v    = dot(P − base_w, tv_w) + pan[1]
```

per `t3d.md` "The UV convention" (✅, pinned by
`test_polyalign.test_engine_fact_uv_formula_is_base_relative_plus_pan`). **The texel scale lives in
the MAGNITUDE of `TextureU`/`TextureV`** — a unit axis is 1 texel per world unit; there is no separate
scale field.

**Zero/missing axis fallback.** `_tex_basis_default` is fed `poly.normal` when present and the Newell
normal otherwise — i.e. the *existing* `_world_uv_frame` behaviour, which is preserved verbatim so the
two renderers cannot drift. This is a deliberate exception to §4.1's Newell rule and is scoped to the
fallback basis only; it does not affect `shade`, which always uses Newell.

**Interpolation is AFFINE and exactly so.** Under ortho, `u`, `v` and depth are linear in screen
space, so barycentric interpolation is exact, not an approximation — `render.rs`'s per-pixel
perspective divide is simply not needed.

**Scaled brushes are REJECTED under `flat`/`textured`** — clean exit 2 naming the offending actor.
`preview._scene_geometry` builds vertices with `rotation.actor_linear` (`PostScale·R·MainScale`) while
the UV frame uses `rotation.actor_matrix` (**rotation only**), so a scaled brush would render scaled
geometry against an unscaled texture frame — silently mis-aligned, the exact defect class this tier
exists to expose. `level preview --native` already rejects the same case (`preview_native._reject_scaled`).
*Rejected: transforming UV axes by the inverse-transpose* — mathematically the right shape, but UE1's
actual treatment of a scaled brush's texture frame is unverified, and guessing it would put a wrong
answer in the one tool meant to be authoritative about UV. Supporting scaled brushes is a follow-up
(§10). `--faces wire` keeps rendering them exactly as today.

### 4.3 Per-pixel texel fetch (`textured`)

```
tx = floor(u / 2**level) % mip_w        # u is in MIP-0 texel units — the /2**level is required
ty = floor(v / 2**level) % mip_h        # Python % on ints == Rust rem_euclid for positive divisors
texel = rgb[(ty * mip_w + tx) * 3 : ... + 3]
```

**The `/ 2**level` is load-bearing** and was the single most-reported defect of review round 1: `u`
comes out of §4.2 in mip-0 texel units, so taking it modulo a *level-L* width tiles the texture `2^L`
times instead of scaling it down. Nearest-neighbour, no bilinear.

Non-finite `u`/`v` (a degenerate frame) must not reach `math.floor`, which raises `ValueError` —
guard and treat the face as untextured (`CLAUDE.md`: no Python exception reaches the user).

**Cut-out handling, per decision 2.3:**

| Case                                                    | Result
|----------------------------------------------------------|---
| face is masked (§4.3a) **and** `mask[…] == 0` at this texel | **pixel not written, and depth NOT written** — a face behind shows through the hole
| face is NOT masked                                       | index 0 is an ordinary palette colour and draws normally
| poly has no `Texture`                                    | `DEFAULT_GREY = (128,128,128) × shade` — matches `render.rs`'s `tex_index < 0` path. A genuinely untextured poly is normal, not an error
| ref present but unresolvable / non-P8 / imported palette | **clean exit 2 naming the offending ref**, before anything is rendered (§8). No checkerboard, no partial render

Not writing depth on a masked texel is the point: writing it would punch a same-shaped hole in
everything behind.

#### 4.3a Is this face masked?

```
masked = bool(poly.flags & 0x2) or texture_is_imported_masked(ref)
```

`PF_Masked = 0x2` is readable today (`query.PF_NAMES`). **The texture-side half is now resolved:**
the stored property is **`bMasked`**, a UE1 bool written PRESENCE-ONLY, so
`texture_is_imported_masked(ref)` is `"bMasked" in <the export's property block>` — no new decoding
(spike `2026-07-26-texture-masked-property/findings.md`; `quirks.md` "Surfaces / polys").

### 4.4 Mip selection (`textured`)

```
uu_per_px     = 1.0 / scale_world          # see the note below — NOT _framing's raw scale under iso
texels_per_px = max(|tu_w|, |tv_w|) * uu_per_px
level         = clamp(floor(log2(max(texels_per_px, 1.0))), 0, len(mips) - 1)
```

`decode_texture` already decodes **all** mips and `mip0_to_rgb(mip, palette)` is generic over any
`Mip`, so this needs only the resolver method in §6.

**`_framing`'s `scale` is px per *projected* unit, and under `iso` — the default `--view` — the iso
projection is a shear, so that is not px per world unit.** `scale_world` must therefore be derived
per view: for `top`/`front`/`side` it is `scale`; for `iso` it is `scale` divided by the projection's
worst-case axis gain. Getting this wrong only mis-picks a mip (a sharpness/cost effect, never a wrong
UV), but it must be specified so two implementations agree.

### 4.5 `flat` mode

Fill is the `(front, back)` pair the wireframe already uses:

- `--brush-colors csg` (default) → `_CSG_PALETTE[classify_brush(actor)]`
- `--brush-colors legend` → `(tint, _fade(tint))` from `assign_tints`, matching `_scene_geometry`
- front-facing for this view (`_is_front`) → the **front** colour; otherwise the **back** colour

**No key-light shade** (*rejected: shading `flat`*) — multiplying the hue would break the "this exact
blue means additive" cue the legend is matched against.

**On the legacy `color_by_csg=False` path** (`render_brushes_pgm`'s default, used by unit tests),
`_CSG_PALETTE` is not consulted at all; `flat` there fills with the same black/grey pair that path
already uses for edges.

### 4.6 Wireframe presence

| Mode       | Wireframe
|------------|---
| `wire`     | yes — the whole render (unchanged)
| `flat`     | **yes**, over the fills — face boundaries and the CSG cue
| `textured` | **no**. The only *deliberate* line art is `--highlight` (§5). Note §5's decal/legend caveat — a default textured render is not literally line-free

### 4.7 Visibility: CSG-aware culling, then a depth buffer

**Culling rule (decision 2.10), applied in `flat` and `textured`:**

| Brush op (`classify_brush`)              | Which faces render
|-------------------------------------------|---
| `subtract`                                | **only faces NOT facing the camera** — the far/interior surfaces. Camera-facing polys are culled outright
| `add`, `semisolid`, `nonsolid`, `mover`   | **all** faces; the depth buffer resolves visibility

Vertices are stored CCW-from-outside (`t3d.md` "Polygon sub-fields"), so a subtract's near face is
`_is_front` — exactly the set to cull. This makes an additive brush inside a subtracted room visible
from outside, matches what the editor and the game draw, and is why `flat`/`textured` do not simply
show the outside of the outermost box.

Non-subtract brushes are **not** back-face culled: a `nonsolid` sheet is one face and must be visible
from both sides.

**Depth**, after culling:

- `depth(P) = dot(P, _view_depth(iso_angle, view))` — the existing into-screen direction, **smaller =
  nearer**; affine under ortho
- write iff `depth < zbuf[i]`, then `zbuf[i] = depth`
- **coplanar tie-break:** strictly `<`, so the **first** face drawn wins a tie and iteration order is
  the tie-break. Iteration is scene order (stable, as `assign_tints` already relies on), making the
  result deterministic and golden-testable. No epsilon bias — a flush add/subtract pair is common
  pre-CSG and any bias would merely move the arbitrariness

### 4.8 `--focus`

Every brush stays filled; non-focused brushes are dimmed. Two passes with **separate** depth buffers:

| Pass | Contents                | Depth buffer  | Colour
|------|-------------------------|---------------|---
| A    | all NON-focused brushes | `zbuf_ctx`    | resolved **opaquely** into a scratch buffer, then composited **once** over the canvas at `_DIM_ALPHA` (0.15)
| B    | the focused brush       | `zbuf_focus`  | opaque, full shade — drawn after A, never occluded by context

**Resolve-then-composite-once is required, not stylistic.** Per-face alpha blending against a
nearest-wins depth buffer blends a pixel once per face that passes the test, so the result would
depend on iteration order. Pass A therefore renders opaque into its own buffer and is composited a
single time.

**The dim is a single `_DIM_ALPHA` composite, matching the existing wireframe dimming.** Review round
1 computed that the originally-specified `_fade(rgb, 0.75)` *then* alpha 0.25 leaves `0.0625 × texel`
over the background — final pixels in 210–226 against `BG` 224, i.e. invisible, defeating the owner's
intent that every brush stays visible. `preview.py` already dims non-focused wireframes with one
`_DIM_ALPHA = 0.15` composite; `flat`/`textured` use the same constant so the two agree.

Two buffers, not one, is the mechanism that keeps a focused brush visible even when sealed inside
another. With no `--focus`: one pass, one buffer, all opaque.

### 4.9 Declared divergences from `level preview --native`

Decision 2.2 says "as `--native` shades it". These are the exceptions, **all deliberate**:

| # | Divergence
|---|---
| 1 | **Masking** — `--native` renders masked faces opaque (which is what makes it a free cut-out detector, `quirks.md`); this tier honours the cut-out on genuinely masked faces (2.3)
| 2 | **Mip selection** — `render.rs` is **mip-0 only**; this tier picks a mip per face (§4.4). Any cross-renderer test must therefore force level 0
| 3 | **Precision** — `render.rs` is f32; this is f64. Byte-identity is not claimed (§4.1)
| 4 | **`PF_Invisible`** — `preview_native.build_scene` drops those polys. This tier **also drops them** under `flat`/`textured` (an invisible face must not become an opaque occluder). Under `wire` they keep drawing, unchanged
| 5 | **Projection** — ortho vs perspective, hence affine UV (§4.2)
| 6 | **Unresolvable refs** — `--native` checkerboards the face and warns once; this tier **exits 2** (§8). `conventions.md` rejects warn-and-continue, so this tier conforms and `--native` does not; that is logged against `--native`, not softened here
| 7 | **Scaled brushes** — both reject them; `--native` via `_reject_scaled`, this tier via §4.2. Listed for completeness, as it is a divergence in *message*, not behaviour

### 4.10 Draw order within a pane

1. background (`BG = 224`)
2. **face fills + depth (new)** — `flat`/`textured`; under `--focus`, pass A then pass B
3. point-actor underlays (`_draw_point_underlay`) — selection brackets, **sprites**, and the
   `--show` collision/light/sound overlays
4. brush wireframe edges — **`wire` and `flat` only**
5. `--highlight` outlines
6. point markers, on-face poly decals, leader labels, legend

**Fills moved to step 2, ahead of the point underlays.** Round 1 found the original ordering (fills
after underlays) would paint over every sprite and every `--show` overlay, contradicting this spec's
own claim that point actors are unaffected. Fills are brush geometry and belong under the point
layer.

## 5. Interaction with every existing option

| Option              | Behaviour under `flat` / `textured`
|---------------------|---
| `--layout`          | all three accept it (decision 2.4). See §7 for what `breakdown` costs
| `--view`            | unchanged. The UV math is view-independent; the *mip pick* is not (§4.4)
| `--iso-angle`       | unchanged; feeds `_view_depth` and the iso `scale_world` correction
| `--brush-colors`    | `flat`: as today, governing fills and wireframe. **`textured`: passing it explicitly is a clean exit 2** (decision 2.7)
| `--annotate`        | unchanged and **left exactly as-is** (owner-decided; *rejected: auto-contrast; rejected: a backing plate*). **Two accepted consequences, both recorded:** (a) a tinted decal can be unreadable on a busy texture; (b) `_decal_opacity` still paints an *occluded* face's index at a 0.12 floor, so over an opaque fill that number sits on the wall in front of it — a wrong-face label, not merely a faint one. Anyone reading indices off a `textured` render should pass `--annotate none` or use `flat`
| `--highlight`       | under `textured` its vivid outline is the only *deliberate* line art. Its hue comes from `vivid`, which is `csg`-derived since `--brush-colors` is rejected in this mode
| `--focus`           | §4.8
| `--show`            | unchanged, and now genuinely unaffected — the overlays draw at step 3, above the fills (§4.10)
| `--frame`/`--frame-tightness` | unchanged; they set `scale`, which feeds the mip pick
| `--size`            | unchanged, **uncapped** (decision 2.4)
| `--from-t3d`        | works inside a project. A snippet's refs resolve on the composed search path
| `--prefab-dir`      | `prefab preview --prefab-dir X` deliberately runs with **no project**, so `--faces textured` there always exits 2 per decision 2.6. `wire`/`flat` work normally
| `--out`             | unchanged (always PNG)

**Point actors are unaffected** by `--faces` — it is a brush-face option.

**How `--brush-colors` explicitness is detected.** Its argparse `default` is `"csg"`, so a defaulted
value is today indistinguishable from an explicit `--brush-colors csg`, and decision 2.7 rejects only
the *explicit* combination. The parser sets `default=None` and `dispatch` treats `None` as `"csg"` at
its four consumers. Only a non-`None` value alongside `--faces textured` triggers exit 2.

## 6. Code shape

| Change                                                                     | Where
|----------------------------------------------------------------------------|---
| `world_uv_frame`, `tex_basis_default`, `newell` move to a shared module, imported by BOTH `preview_native.py` and the fill path. `preview._face_normal` is **deleted** and re-imported from here — it is already byte-identical to `_newell`, and §6 exists to stop exactly that duplication | new `uedcli/texframe.py` (stdlib-only, no `uedcli_native` import)
| `TextureResolver.resolve_mips(ref)` → `list[tuple[int,int,bytes,bytes]] \| None` (all mips, masked; `None` on any miss, matching `resolve`). Must reject a truncated mip chain rather than let `mip0_to_rgb` raise `IndexError` | `uedcli/utexture.py`
| a `texture_is_imported_masked(ref)` predicate (**blocked, §11**)             | `uedcli/utexture.py`
| resolve + decode each distinct face ref; collect unresolvable ones and raise the exit 2; the four exit-2 validations | `uedcli/dispatch.py`
| `--faces` parsing; `--brush-colors default=None`; the corrected `help=` strings | `uedcli/cli.py`
| the scanline fill, CSG-aware cull, depth buffers, focus two-pass, mip pick, texel loop | `uedcli/preview.py`
| `--faces` threaded through `render_brushes_pgm` / `render_quad_pgm` / `_render_breakdown_grid` | `uedcli/preview.py`, `uedcli/dispatch.py`

**The `render_data` seam, precisely.** `render_data` is today `dict[actor_name → PointRender]` and is
indexed by name in `_scene_geometry`, `_world_aabb` and `_point_pane_region`. It becomes a small
dataclass:

```
PreviewData(points: dict[str, PointRender], faces: FaceTextures | None)
FaceTextures:  by_ref:   dict[str, list[tuple[int,int,bytes,bytes]]]   # ref → mip pyramid (rgb, mask)
               masked:   dict[tuple[str,int], bool]                    # (actor, poly_idx) → §4.3a
```

A face's texture is looked up by its `poly.texture` ref. Every ref present in the set is guaranteed
to be in `by_ref` — an unresolvable one exits 2 before rendering (§8), so there is no fallback slot
and no missing-key path. `poly.texture is None` means `DEFAULT_GREY`. Existing call sites move from `render_data[name]` to
`render_data.points[name]` — a mechanical change with no behaviour effect, and the reason the shape is
specified here rather than left to the plan.

**`_preview_render_data` must be restructured.** It currently early-returns `{}` when the actor set
has no point actors — the *common* case for a brush-only textured preview — so neither face
resolution nor decision 2.6's exit 2 can be reached from it as written. Its docstring's stated
contract ("a pure-brush preview works with no game install") remains true for `wire` and `flat` and
is now false for `textured` by design; update it.

## 7. Cost, and the accepted risk

Measured on this box, LUM `basement` (28 actors), 2026-07-26:

| Render                                                                 | Time
|------------------------------------------------------------------------|---
| `actor preview` quad @1024, wireframe, pure Python                      | 4.6 s
| `level preview --native` @512², full CSG carve + textured raster, Rust  | 0.68 s

**These two are not directly comparable and no ratio is claimed from them.** The first is a
*wireframe* render at ~1.05 M px whose cost is dominated by label placement and decal planning; the
second is a *fill* at ~0.26 M px. Round 1 correctly refuted the earlier "~7× slower" inference. What
stands is the qualitative point: a pure-Python per-pixel fill is far slower than the Rust one, and
fills are O(area) where wireframe is O(perimeter).

**Corrected pane arithmetic** (round 1; the original figures were wrong by 4× in both directions):

| Layout        | Panes            | Pixels at `--size 1024`
|---------------|------------------|---
| `single`      | 1 at `size`      | ~1.05 M
| `quad`        | 4 at `size // 2` | ~1.05 M total — **~1× a single pane, not 4×**
| `breakdown`   | **N+1 at full `size`**, each `--focus`ed | ~(N+1) × 1.05 M — on this 28-actor level, **~29 two-pass full-scene fills**

**`--layout breakdown` is the worst case, not `--focus`.** A reviewer measured a representative
pure-Python textured inner loop at ~4.6 s per 1 M px, putting a breakdown textured render in the
**many-minutes** range.

**The owner re-affirmed "no guard, no ceiling" against these corrected figures** (*rejected: exit 2
for `textured` under `breakdown`; rejected: a stderr cost warning past a pixel budget*). The accepted
consequence, recorded plainly: `--faces textured --layout breakdown` can run for minutes with no
progress output. Mip selection (§4.4) is the only cost control.

## 8. Failure and degradation

| Situation                                             | Behaviour
|--------------------------------------------------------|---
| bad `--faces` value                                    | argparse choice error, exit 2
| `--faces textured` + explicit `--brush-colors`         | exit 2 naming both flags and the conflict
| `--faces flat\|textured` + a **scaled** brush          | exit 2 naming the offending actor and its scale (§4.2)
| **no usable texture resolver** + `textured`            | exit 2 naming **which** cause applies — `_texture_resolver` returns `None` for three distinct reasons (no user games config; a `ConfigError`; an empty composed file list), all reachable *with* a valid project, so a generic "no project" message would violate "naming the offending value". `wire`/`flat` are unaffected
| a face's `Texture` ref does not resolve                | **exit 2 naming that ref**, listing every unresolvable ref in the set (not just the first) so one run fixes them all
| non-P8 / imported palette / truncated mip chain        | same — exit 2 naming the ref and which of those applies, never an exception and never a partial render
| a face has no `Texture` at all                         | `DEFAULT_GREY × shade`, silently — a genuinely untextured poly is normal

**Every failure here refuses; none degrades.** `direction/conventions.md` lists warn-and-continue
under **Rejected** ("a half-answer that looks like a full one is worse than a refusal; the note
scrolls away"), and a textured render whose faces are secretly checkerboards is exactly that — the
picture looks like an answer. Validation runs in `dispatch` **before** any pixel is drawn, so the
failure is a refusal rather than a half-finished image.

This makes `--faces textured` **stricter than `level preview --native`**, which today checkerboards
an unresolvable ref and warns once (`preview_native._TextureTable`). That inconsistency is real and
now runs the other way; it is `level preview --native`'s behaviour that does not match
`conventions.md`, and changing an existing verb is out of scope here. Logged on `board/inbox.md` as
its own item — **not** as a reason to weaken this spec.

## 9. Tests

| Test                                                                                | Guards
|--------------------------------------------------------------------------------------|---
| `--faces wire` output **byte-identical** to today for a fixed scene                   | the change is additive — the primary regression guard
| `u = (V − Origin)·TextureU + Pan` on a rotated, pre-pivoted brush                     | the UV convention
| **mip level L samples the same world point as level 0** (the `/2**level` rescale)      | §4.3's top defect; a test on level *selection* alone passes the buggy version
| forced level 0: ortho Python vs `render.rs` agree on texel **index** (not bytes)       | cross-renderer drift, scoped past the f32/f64 and mip divergences (§4.9)
| a **masked** face's index-0 texels leave `BG` and skip depth; an **unmasked** face's index-0 texels draw normally | decision 2.3, both directions — the round-1 defect
| a **scaled** brush exits 2 under `flat`/`textured` and still renders under `wire`      | §4.2
| **subtract**: camera-facing faces culled, far faces drawn, and an add brush inside a subtract is visible | decision 2.10 — the structural fix
| a `nonsolid` sheet renders from both sides                                             | that culling is subtract-only
| two overlapping brushes: nearer face wins; coplanar tie goes to scene order            | §4.7
| point **sprites** and each `--show` overlay survive an opaque fill                      | §4.10's reordering
| `--focus`: focused brush visible when fully enclosed; context composited **once** (order-independent) and at `_DIM_ALPHA` | §4.8, both the two-buffer mechanism and the blend-once fix
| `PF_Invisible` faces do not fill and do not write depth                                 | §4.9 #4
| `flat` fill RGB == the front/back pair for `csg` **and** `legend`, unshaded; and on the legacy `color_by_csg=False` path | §4.5, all three paths
| bare `--faces textured` succeeds; `--faces textured --brush-colors csg` exits 2          | the `default=None` mechanism
| each of `_texture_resolver`'s three `None` causes produces a message naming that cause   | §8
| `stash preview` / `prefab preview` accept `--faces`; `--prefab-dir` + `textured` exits 2 | §3, §5
| `--layout quad` and `--layout breakdown` both render under `flat` and `textured`         | untested layouts in round 1
| an unresolvable ref exits 2 naming it, lists ALL unresolvable refs, and writes no image        | §8 — refuse, never degrade
| a non-P8 / imported-palette / truncated-mip texture exits 2 naming which applies                | §8, the same refusal path
| non-finite UV and a truncated mip chain produce a clean result, never a traceback         | `CLAUDE.md`'s no-exception rule
| a golden PNG of a textured cube, blessed like `native_preview_golden.png`                 | end-to-end pixel stability
| `uedcli/texframe.py` imports nothing outside stdlib + uedcli                               | §0's no-cargo constraint, tested where it can actually regress

Dropped from the round-1 list as vacuous: "Python `%` vs Rust `rem_euclid`" (true by definition for
positive divisors) and "runs with the native extension absent" (`preview.py` never imports it — the
`texframe.py` import test above is the real guard).

## 10. Deferred (explicitly out of scope)

- **The Rust port / a non-optional native extension.** If revisited: an ortho camera mode in
  `render.rs` plus a scene builder taking raw brush polys instead of carved BSP nodes.
- **Scaled brushes under `flat`/`textured`** — rejected with exit 2 in v1 (§4.2). Supporting them
  needs UE1's actual scaled-brush texture-frame behaviour verified first.
- **Bilinear filtering, real lighting, mesh rendering for point actors, the `Translucent` polyflag.**
- **A `texture list --cutout` filter** over the catalog's dominant-colour signal — a separate ask.

## 11. The masking spike — DONE, blocker cleared

`spikes/2026-07-26-texture-masked-property/findings.md` (2026-07-26) answered it: the stored property
is **`bMasked`**, a UE1 bool on the `Texture` export written **presence-only** (present ⇒ masked,
absent ⇒ not), decoded by the existing `utexture._read_props`. §4.3a is implementable as written.

Two measurements from that spike belong here because they size what decision 2.3 avoided:

- **464 of 2,669** corpus textures use palette index 0 while NOT masked — **17.4 %**. The original
  unconditional-masking draft would have punched false holes in all of them, and flat colour swatches
  (`LUM_CoreTex.White` and eleven more) are **100 %** index 0, so those faces would have rendered as
  nothing at all.
- **Reserved magenta at palette[0] is not a masking signal** — three unmasked textures park it and
  never use it, while the one texture that most needs protecting (`ArthurCallaway`, 2.2 % index-0
  usage) has real black there. `bMasked` is the only reliable gate.

Pinned by two `test_engine_facts` regressions against committed fixtures.


---

## 12. BLOCKING (re-entry round, 2026-07-26) — a sequencing conflict

**`dev/docs/board/to-build.md` carries a REVIEWED, on-deck `p1`: "Native texture decode for any UE1
package"** (spec `specs/2026-07-25-native-texture-formats.md` + its plan). That work:

- **deletes `TextureResolver.resolve_masked`** outright — its spec line 159: *"§4's return-type change
  **deletes** `TextureResolver.resolve_masked` rather than keeping it beside…"*, citing no-back-compat;
- **replaces `resolve`'s `None`-on-miss contract** with a typed error object naming the case;
- adds **`CompMips`** — a second, compressed mip array — changing what "the mip pyramid" is;
- records **30 textures in the project's own `LUM/Textures/LUM_CoreTex.utx` that do not decode today.**

This spec's §6 specifies `resolve_mips(ref) -> list[…] | None`, *"`None` on any miss, matching
`resolve`"* — designed against the exact contract being replaced, beside a method being deleted. §0,
§10 and §11 name no such dependency because this spec never knew about it.

Two further consequences: §8's "non-P8 → exit 2" becomes wrong the day that item lands; and because
`--faces textured` **refuses** rather than degrades, any LUM level using one of those 30 undecodable
textures would fail to render at all — where `level preview --native` shows a checkerboard today.

**The owner's ruling is needed on sequencing**, and the options are genuinely different builds:
land textured-faces first against today's API and rework it after; wait for the texture-decode item
and design `resolve_mips` against the new typed-error contract; or fold the mip-pyramid accessor into
that item's scope so there is one texture API change, not two.

## 13. Detail defects from the re-entry round (fix in the same revision as §12)

Converged across the three reviewers unless noted. **Not yet applied** — see the status header.

| # | Defect
|---|---
| 1 | **The masking gate ignores the brush ACTOR's `PolyFlags`** (all 3). `preview_native.build_scene` ORs `_poly_flags_int(actor.props)` into every poly (`preview_native.py:382`), and `preview.classify_brush` already reads actor-level flags. §4.3a reads `poly.flags` only, so a brush authored `PolyFlags=2` masks in the engine and in `--native` but renders opaque here — re-hiding "cut-out texture on a solid face", one of §0's four motivating defects. §4.9 #4's `PF_Invisible` drop has the identical hole
| 2 | **`--prefab-dir` does NOT imply "no project"** (all 3). It overrides only the prefab library root (`dispatch._prefab_root`); `_preview_render_data` independently calls `_resolve_project(args)`. §5's row is false and §9's test would pass or fail by cwd
| 3 | **§4.4 declares `scale_world` "must be specified" and never specifies it** (all 3), and the recipe given is wrong: `scale` is px per *projected* unit so the correction multiplies, not divides; and the iso map is an orthogonal anisotropic scale, not a shear. `preview._draw_sphere` already carries the constant (`max(√2·cos r, √(2 sin²r + 1))` = 1.2247 at 30°). Three readings ⇒ three mip picks, and §9 has no iso mip test
| 4 | **`resolve_mips -> … \| None` cannot produce §8's "naming which cause applies"** (2 of 3). `_decode_ref` collapses six distinct misses to `None`; `_texture_resolver` likewise, and §6 does not list it as changing. Either it returns a reason or §8/§9 drop the requirement
| 5 | **`preview._face_normal` is imported by `query.py:13` and `polyalign.py:26`** (all 3). §6 says "deleted"; deleting it breaks `actor show` / `brush poly *` at import, and a re-export alias is the shim `conventions.md` forbids. Neither file is listed as touched. A third `_newell` also lives at `builders.py:82`
| 6 | **The `render_data` reshape is not mechanical and the call-site list is short** (all 3). `preview.render_quad_pgm:1868-1870` is unlisted; `render_brushes_pgm:1622` and `render_quad_pgm:1868` both do `render_data or {}`, which yields a plain dict with no `.points` ⇒ `AttributeError` to the user; `_scene_geometry`'s `.get(name)` + `is None` guard becomes a `KeyError` under `[name]`
| 7 | **`math.floor(±inf)` raises `OverflowError`, not `ValueError`** (2 of 3). §4.3 names only `ValueError`, so an implementer following it literally still leaks a traceback — in the one place the spec cites the no-exception rule
| 8 | **The rasterizer is underspecified** (1 of 3, but load-bearing). §6 says "scanline fill", §4.2 says "barycentric" — different rasterizers, and no pixel-coverage/fill rule is given. `architecture.md` records that **0.1–0.6 % of faces in real exported maps are concave** (spike `concave-faces/`, live 2026-07-23), which is why `preview.py` already carries `_poly_is_convex_2d`. A fan triangulation fills outside a concave face; even-odd scanline does not. §9's golden PNG would bless whichever was built
| 9 | **No offline test can exercise the `bMasked = True` arm** (1 of 3). Neither committed fixture carries `bMasked` (I verified), and the game corpus is gitignored — so the half the spike calls load-bearing ships untested. §6 budgets no synthesized masked fixture
| 10 | **§9's cross-renderer test is unimplementable** (2 of 3). `render.rs` is reachable only as `render_frame` → RGB bytes; texel indices are never exposed, the projections differ, and the Rust half is `importorskip`-gated so it would silently skip on the no-cargo machine §0 protects
| 11 | **`--brush-colors` has THREE consumers, not four**, and `getattr(args, "brush_colors", "csg")` does **not** fire for an existing-but-`None` attribute — each site needs an explicit `or "csg"` (all 3)
| 12 | **§7 over-counts breakdown**: `_render_breakdown_grid` passes `focus=None` for pane 0 and every point-actor pane, so only brush panes are two-pass. Reviewers put the real figure at ~2.2–4.5 min, not "many minutes" (all 3)
| 13 | **The swatch count contradicts the spike it cites** — "and eleven more" (12) vs findings.md's 13 (all 3)
| 14 | **§4.9 #7 mislabels the scaled-brush divergence** as message-only; it is behavioural (this tier rejects only under `flat`/`textured`). And `_reject_scaled` also rejects **`SheerRate`**, which `actor_linear` folds into geometry — a pure-sheer brush is the same silent hazard and §8's "naming its scale" mis-describes it (all 3)
| 15 | **§6's truncated-mip reasoning is inverted**: a SHORT mip silently zero-fills (the dangerous case); only an over-long one raises `IndexError`. §6 directs guarding the wrong one (all 3)
| 16 | **§4.5's legacy-path claim is wrong about the mechanism** — `_CSG_PALETTE` *is* evaluated unconditionally at `preview.py:1464-1467` and then discarded. Colours right, mechanism wrong
| 17 | **§4.10 step 6's internal order is wrong** — the code draws markers → leader labels → decals → keyline → legend
| 18 | **Unspecified**: pass-A scratch buffer initialisation; `by_ref` key casefolding (`_TextureTable` uses `ref.casefold()`, §6 does not say); whether the §4.7 cull also suppresses `--highlight`/`flat` line art on culled faces; `textured` on the legacy `color_by_csg=False` path; faces with <3 vertices (`render.rs` skips them explicitly)
| 19 | **A bare (unqualified) `Texture=` ref is the most common miss and §8 never names it.** `_decode_ref` rejects it before any lookup; `_TextureTable` already emits the right hint ("qualify the ref as `Package.Name`"). Exiting 2 without saying that is the biggest practical usability risk
| 20 | **§8 vs §4.3 collide when nothing needs a texture** — `brush build cube \| actor preview --from-t3d - --faces textured` has every poly `texture=None`, yet exits 2 outside a project. Follows from decision 2.6 but is nowhere recorded as a consequence
| 21 | **§4.7's "matches what the editor and the game draw" is an undated, uncited engine claim.** The support is the owner's dated ruling (2.10); attribute it plainly or cite evidence, since this text folds into a durable doc
| 22 | **`_DIM_ALPHA = 0.15` may not restore the intent** (all 3, as a concern). One composite gives `0.15·c + 190.4` → 190–229; a mid-grey texel lands ~210 against `BG` 224. `_DIM_ALPHA` was tuned for thin *lines*, not area fills. Wants one test render before building

**Refuted, with the check recorded** (`CLAUDE.md` requires the disproving check, not just the claim):
one reviewer reported that procedural textures (`FireTexture`/`WetTexture`/…) pass `_decode_ref`'s
`not t.mips` gate with an empty mip and render **all-black at exit 0**. I scanned the **full 2,669
`Texture`-classed export corpus**: **zero** have `fmt == 0` with an empty mip-0. The code path exists
but no corpus texture reaches it, and a poly naming a procedural texture misses the name lookup and
exits 2 correctly. Not a defect here.

**Three reviewers independently confirmed there is no OTHER structural problem** — the pre-CSG ortho
tier, the `--faces` shape, the masking gate's structure and the subtract-culling rule all hold up
against the docs and the code. §12 is a sequencing conflict, not a design error in this spec.
