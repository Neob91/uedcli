# Spec: textured faces for `actor preview` (`--faces wire|flat|textured`)

**Status:** round 1 of the re-entry gate PASSED WITH FINDINGS (2026-07-26, 3 cold Opus; **no
structural finding — all three confirmed the design holds**). §13 lists what they found; resolving it
changes the artifact, so **round 2 (2 Opus) is owed**. Two items need an owner ruling first — §14.
**DEPENDS ON** the on-deck texture-decoder work — see §12. Build order is fixed: that item first
(with the §12 accessor folded into its scope), then all of this.
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

**Not** a Rust port (§10); **not** a replacement for `level preview --native` (that stays the
perspective, whole-level, post-CSG tier); **not** lighting. The native extension stays optional —
nothing here may make `actor preview` fail on a machine without `cargo`.

**Why it is worth building.** Every texture-frame defect in
[`spikes/levelbuild-friction/agent-reports.md`](../spikes/levelbuild-friction/agent-reports.md) —
mirrored lettering, the half-shifted sheet, the wrapped door trim, the cut-out texture on a solid
face — was **invisible in `actor preview`** and cost a full materialize + render cycle to see. Those
faults are properties of the *authored* UV frame, which this tier reads directly.

## 1. The governing constraint

`preview.py` is **stdlib-only** (no PIL/numpy) and **resolver-free** — `dispatch.py` resolves and
decodes, `preview.py` receives decoded pixels and draws ([`architecture.md`](../architecture.md)
"Preview internals"). The seam already carries texture pixels: point sprites resolve in
`dispatch._preview_render_data()` and reach `preview._blit` as `(w, h, rgb, mask)`. Textured faces
extend that same channel (§6).

## 2. Decisions (the owner's, 2026-07-26)

1. **`--faces {wire,flat,textured}`, default `wire`.** *Rejected: a boolean `--textured`* — no room
   for `flat` without a second flag later, and "No back-compat cruft" makes reshaping a hard break.
2. **A textured face is shaded as `level preview --native` shades it** (§4.1). *Rejected:
   unlit/full-bright.* Every divergence is enumerated in §4.9 — nothing diverges by accident.
3. **Cut-outs are honoured, but ONLY on a genuinely masked face** (§4.3a). *Rejected: masking every
   index-0 texel unconditionally* — the spike measured **464 of 2,669** corpus textures using index 0
   while unmasked, including flat swatches at 100 % that would have rendered as nothing at all;
   *rejected: rendering masked opaque like `--native`.*
4. **All layouts accept `--faces`, no size guard, no cost ceiling** — re-affirmed against the
   corrected figures in §7. *Rejected: rejecting `textured` under `breakdown`; rejected: a stderr cost
   warning.*
5. **`textured` draws NO wireframe; `flat` KEEPS its wireframe** (§4.6). Accepted consequence: under
   `textured` two abutting brushes sharing a texture are indistinguishable and the CSG cue is absent.
6. **Any texture the render needs and cannot get is a clean exit 2 naming the cause** (§8).
   *Rejected: checkerboarding; rejected: silently falling back to `flat`.*
7. **`--brush-colors` with `--faces textured` is a clean exit 2** — re-affirmed after its original
   rationale ("it would do nothing") was **refuted**: `preview._scene_geometry` derives `vivid`, the
   `--highlight` colour, from it. It stands on the corrected ground that the flag's documented job is
   the wireframe, and repurposing it under one mode would give one flag two jobs.
8. **`level preview` is NOT changed** — it keeps `--native`/`--game` (which *backend*).
9. **The Rust port and a non-optional native extension are DEFERRED** (§10).
10. **A subtract brush's faces render ONLY from inside the subtracted volume** (§4.7) — *"the
    subtract's polys looked at from OUTSIDE do not render in UnrealEd or in game, and they should not
    render here"* (owner). Under an always-outside ortho camera: **cull a subtract's camera-facing
    polys, draw its far ones.**
11. **Build order: the texture-decoder item FIRST, with this spec's mip accessor folded into its
    scope; then all of this** (§12). *Rejected: shipping `wire`/`flat` first and `textured` later;
    rejected: waiting for that item without folding the accessor in; rejected: building now against
    today's decoder and reworking.*
12. **`--focus` context dimming is strengthened and VERIFIED BY RENDER, not by arithmetic** (§4.8).

## 3. CLI surface

One option, on `actor preview`, `stash preview` and `prefab preview` — they share
**`cli._preview_opts`** (`cli.py:685, 1474, 1511`).

```
--faces {wire,flat,textured}
```

**`help=`:**

> how brush faces are drawn (default `wire`). `wire` = outlines only, the schematic. `flat` = each
> face filled solid in its brush's CSG hue, wireframe kept — a diagram of what occludes what.
> `textured` = each face filled by sampling its OWN texture through its authored UV frame
> (`Origin`/`TextureU`/`TextureV`/`Pan`), with NO wireframe, so alignment, panning, mirroring and
> tiling are visible offline — no editor, no container, no lighting. Under BOTH `flat` and
> `textured` a subtract brush shows only its far (interior) faces, so geometry inside a subtracted
> room stays visible, and a scaled or sheared brush is rejected. `textured` additionally rejects
> `--brush-colors`, and needs every referenced texture to be readable.

**Three existing `help=` strings are corrected in the same change** (`CLAUDE.md`: help must say what
a flag actually does):

- `--brush-colors` (`cli.py:156`) — says "how to colour **the wireframe**"; it also drives `flat`
  fills and is a hard error under `textured`.
- `--focus` (`cli.py:192`) — says other brushes "recede to a faint (dimmed) **wireframe**"; under
  `flat`/`textured` they recede as dimmed *fills*.
- `--show` — its overlays are unaffected, but the ordering guarantee is now explicit (§4.10).

## 4. The shape of a face — exact

### 4.1 Per-face shade (`textured` only)

| Quantity   | Definition
|------------|---
| `N`        | Newell normal over the face's **world** vertices — NOT the stored `Normal`, per `t3d.md` "Winding defines the face, not `Normal`"
| `L`        | key light `(-0.408, -0.577, 0.707)`, **un-normalized** (`|L|` = 0.99962)
| `shade`    | `0.55 + 0.45 * abs(dot(N, L)) / length(N)`
| skipped    | a face with **fewer than 3 vertices** (matching `render.rs:141-143`), or `length(N) <= 1e-12`

Compute in Python `float` (f64); convert with **truncation**, `min(int(c * shade), 255)`, matching
`render.rs`'s `(c * shade).min(255.0) as u8`. `render.rs` is f32, so byte-identity with `--native` is
**not** claimed (§4.9 #3).

### 4.2 Per-vertex UV

From **`texframe.world_uv_frame(actor, poly)`** (§6): `base_w = Location + R·(Origin − PrePivot)`,
`tu_w = R·TextureU`, `tv_w = R·TextureV`, and per vertex `P`:

```
u = dot(P − base_w, tu_w) + pan[0]        v = dot(P − base_w, tv_w) + pan[1]
```

per `t3d.md` "The UV convention" (✅, pinned by
`test_polyalign.test_engine_fact_uv_formula_is_base_relative_plus_pan`). **Texel scale lives in the
MAGNITUDE of `TextureU`/`TextureV`** — a unit axis is 1 texel per world unit.

**Zero/missing axis fallback:** `_tex_basis_default` is fed `poly.normal` when present, Newell
otherwise — the *existing* `_world_uv_frame` behaviour, preserved verbatim so the two renderers
cannot drift. A deliberate exception to §4.1's Newell rule, scoped to the fallback basis only; it
never affects `shade`.

**Interpolation is AFFINE and exactly so** under ortho — `render.rs`'s per-pixel perspective divide
is not needed.

**Scaled OR SHEARED brushes are REJECTED under `flat` and `textured`** — clean exit 2 naming the
actor and which of `MainScale` / `PostScale` / `SheerRate` is non-identity. `preview._scene_geometry`
builds vertices with `rotation.actor_linear` (`PostScale·R·MainScale`, and `transform.fscale_matrix`
folds sheer in) while the UV frame uses `rotation.actor_matrix` (**rotation only**) — so such a brush
would render transformed geometry against an untransformed texture frame.
`preview_native._reject_scaled` rejects the same three fields. *Rejected: transforming UV axes by the
inverse-transpose* — UE1's actual treatment is unverified and guessing it would put a wrong answer in
the one tool meant to be authoritative about UV. Supporting them is a follow-up (§10). **`--faces
wire` still renders them exactly as today** — a behavioural difference from `--native`, which rejects
in every mode (§4.9 #7).

### 4.3 Per-pixel texel fetch (`textured`)

```
tx = floor(u / 2**level) % mip_w        # u is in MIP-0 texel units — the /2**level is REQUIRED
ty = floor(v / 2**level) % mip_h        # Python % on ints == Rust rem_euclid for positive divisors
texel = rgb[(ty * mip_w + tx) * 3 : ... + 3]
```

The `/ 2**level` is load-bearing: `u` is in mip-0 units, so taking it modulo a level-`L` width tiles
the texture `2^L` times instead of scaling it down.

Nearest-neighbour, no bilinear. **Non-finite `u`/`v` must not reach `math.floor`** — `floor(nan)`
raises `ValueError` and `floor(±inf)` raises **`OverflowError`**; guard on `math.isfinite` and treat
the face as untextured (`CLAUDE.md`: no Python exception reaches the user).

| Case                                     | Result
|------------------------------------------|---
| face is masked (§4.3a) and `mask[…] == 0` | **pixel not written, and depth NOT written** — a face behind shows through
| face is NOT masked                       | index 0 is an ordinary colour and draws normally
| poly has no `Texture`                    | `DEFAULT_GREY = (128,128,128) × shade` — matches `render.rs`'s `tex_index < 0` path. Normal, not an error
| the texture cannot be read               | **exit 2 before rendering** (§8) — no checkerboard, no partial image

#### 4.3a Is this face masked?

```
flags  = (poly.flags or 0) | actor_polyflags(actor)      # the engine ORs the ACTOR's PolyFlags in
masked = bool(flags & 0x2) or texture_has_bMasked(ref)
```

**The actor-level `PolyFlags` OR is required**, not optional: `preview_native.build_scene` does
exactly this (`flags = (poly.flags or 0) | _poly_flags_int(dict(actor.props))`,
`preview_native.py:382`) and `preview.classify_brush` already reads actor-level flags for
semisolid/nonsolid. Omitting it would leave a brush authored `PolyFlags=2` masking in the engine and
in `--native` but opaque here — re-hiding "cut-out texture on a solid face", one of the four defects
§0 exists to expose.

`PF_Masked = 0x2` (`query.PF_NAMES`). `texture_has_bMasked` is `"bMasked" in <the export's property
block>` — a UE1 bool written **presence-only**, so present ⇒ masked (spike
[`2026-07-26-texture-masked-property/findings.md`](../spikes/2026-07-26-texture-masked-property/findings.md);
`quirks.md` "Surfaces / polys"). Delivered by §12's accessor.

### 4.4 Mip selection (`textured`)

```
gain          = 1.0                                          # top / front / side
gain          = max(sqrt(2)*cos(r), sqrt(2*sin(r)**2 + 1))   # iso, r = radians(iso_angle)
scale_world   = scale * gain                                 # px per WORLD unit
texels_per_px = max(|tu_w|, |tv_w|) / scale_world
level         = clamp(floor(log2(max(texels_per_px, 1.0))), 0, len(mips) - 1)
```

`_framing`'s `scale` is px per **projected** unit, and the iso projection maps a unit world vector to
a projected vector of length up to `gain` — so the conversion **multiplies**. `gain` is the map's
larger singular value; `preview._draw_sphere` already computes exactly this expression
(`preview.py:1843`) and it is reused rather than re-derived. (At the default 30° it is 1.2247; the
per-axis gains are all 1.0, which is why "worst-case axis gain" is the wrong quantity.)

`decode_texture` already decodes all mips and `mip0_to_rgb` is generic over any `Mip`. Mip choice
bounds texel fetches to ~1 per pixel regardless of texture size, and is the only cost control (§7).

### 4.5 `flat` mode

Fill is the `(front, back)` pair the wireframe already uses, chosen by `_is_front`:

- `--brush-colors csg` (default) → `_CSG_PALETTE[classify_brush(actor)]`
- `--brush-colors legend` → `(tint, _fade(tint))` from `assign_tints`, matching `_scene_geometry`
- the **legacy `color_by_csg=False` path** (`render_brushes_pgm`'s default, used by unit tests) →
  the same `(FRONT, BACK)` black/grey pair that path already uses for edges. *(Mechanically,
  `_scene_geometry` evaluates `_CSG_PALETTE[...]` unconditionally at `preview.py:1464-1467` and then
  discards it on this branch — the colours are as stated, the palette lookup is not skipped.)*

**No key-light shade** — multiplying the hue would break the "this exact blue means additive" cue the
legend is matched against. Accepted consequence: a subtract brush can only ever show its **back**
colour, since decision 2.10 culls every camera-facing subtract poly.

### 4.6 Wireframe presence

`wire` → the whole render. `flat` → **yes**, over the fills. `textured` → **no**; the only
*deliberate* line art is `--highlight` (§5). A default `textured` render is not literally line-free —
`--annotate` defaults to on and still paints decals, keylines and the legend (§5).

**Line art follows the cull.** A face suppressed by §4.7's subtract cull draws no wireframe edge and
no `--highlight` outline — the cull removes the face, not merely its fill.

### 4.7 Visibility: CSG-aware culling, then a depth buffer

| Brush op (`classify_brush`)               | Which faces render
|-------------------------------------------|---
| `subtract`                                | **only faces NOT facing the camera** — the far/interior surfaces
| `add`, `semisolid`, `nonsolid`, `mover`   | **all** faces; the depth buffer resolves visibility

Vertices are stored CCW-from-outside (`t3d.md`), so a subtract's near face is `_is_front` — exactly
the set to cull. Non-subtract brushes are **not** back-face culled: a `nonsolid` sheet is one face
and must be visible from both sides. `classify_brush` returns exactly these five values, so the table
is total.

*(That this matches the editor and the game is the owner's ruling of 2026-07-26, quoted in decision
2.10 — attributed, not asserted as independently verified engine fact.)*

**Depth**, after culling: `depth(P) = dot(P, _view_depth(iso_angle, view))`, **smaller = nearer**,
affine under ortho. Write iff `depth < zbuf[i]`. **Coplanar tie-break:** strictly `<`, so the first
face drawn wins and iteration is scene order (stable, as `assign_tints` already relies on) — no
epsilon bias, since a flush add/subtract pair is common pre-CSG and a bias would only move the
arbitrariness.

### 4.8 `--focus`

Every brush stays filled; non-focused brushes are dimmed. Two passes, **separate** depth buffers:

| Pass | Contents                | Depth buffer  | Colour
|------|-------------------------|---------------|---
| A    | all NON-focused brushes | `zbuf_ctx`    | resolved **opaquely** into a scratch buffer initialised to `BG`, then composited over the canvas **once**
| B    | the focused brush       | `zbuf_focus`  | opaque, full shade — drawn after A, never occluded by context

**Resolve-then-composite-once is required, not stylistic:** per-face alpha blending against a
nearest-wins depth buffer blends a pixel once per passing face, making the result depend on iteration
order.

**The dim strength is NOT fixed by this spec — it is chosen by render.** The originally-specified
`_fade(rgb, 0.75)` then alpha 0.25 was refuted (it leaves `0.0625·texel + 210` against `BG` 224, i.e.
invisible). The obvious replacement — one `_DIM_ALPHA = 0.15` composite, as the wireframe uses — was
independently flagged by all three round-2 reviewers as probably *also* too faint: it gives
`0.15·c + 190.4`, so a mid-grey texel lands ~210 against `BG` 224. `_DIM_ALPHA` was tuned for thin
**lines**, where a faint stroke still reads as a stroke; a large flat area at that strength is
near-uniform. **Owner ruling (2026-07-26): make it stronger, then verify with a real before/after
render rather than arithmetic.** The build produces that render, picks the constant from it, and
records the chosen value plus the image in `rationale/preview.md`. Starting point ≈ 0.35.

### 4.9 Declared divergences from `level preview --native`

| # | Divergence
|---|---
| 1 | **Masking** — `--native` renders masked faces opaque (making it a free cut-out detector); this tier honours the cut-out on genuinely masked faces
| 2 | **Mip selection** — `render.rs` is **mip-0 only**; this tier picks a mip per face (§4.4)
| 3 | **Precision** — `render.rs` is f32, this is f64; byte-identity is not claimed
| 4 | **`PF_Invisible`** — both drop those polys, and both test the **actor-OR'd** flags (§4.3a). Under `wire` they keep drawing, unchanged
| 5 | **Projection** — ortho vs perspective, hence affine UV
| 6 | **Unresolvable/undecodable refs** — `--native` checkerboards and warns; this tier **exits 2** (§8). `conventions.md` rejects warn-and-continue, so this tier conforms and `--native` does not; that is logged against `--native`, not softened here
| 7 | **Scaled/sheared brushes** — a **behavioural** difference, not just a message: `--native` rejects in every mode, this tier rejects only under `flat`/`textured` and still renders them under `wire`

### 4.10 Draw order within a pane

1. background (`BG = 224`)
2. **face fills + depth (new)** — under `--focus`, pass A then pass B
3. point-actor underlays (`_draw_point_underlay`) — selection brackets, **sprites**, and the `--show`
   collision/light/sound overlays
4. brush wireframe edges — **`wire` and `flat` only**
5. `--highlight` outlines
6. point markers → legacy leader labels → painted on-face decals → the overlap keyline → the legend
   (the existing order at `preview.py:1663-1749`, unchanged)

Fills sit at step 2, **ahead of the point layer**: they are brush geometry, and placing them later
would paint over every sprite and every `--show` overlay.

## 5. Interaction with every existing option

| Option              | Behaviour under `flat` / `textured`
|---------------------|---
| `--layout`          | all three accept it. See §7 for what `breakdown` costs
| `--view`            | unchanged. The UV math is view-independent; the **mip pick is not** — `iso` needs §4.4's `gain`
| `--iso-angle`       | feeds `_view_depth` and §4.4's `gain`
| `--brush-colors`    | `flat`: as today. **`textured`: passing it explicitly is a clean exit 2** (decision 2.7)
| `--annotate`        | unchanged and **left exactly as-is** (owner-decided). Two accepted consequences: (a) a tinted decal can be unreadable on a busy texture; (b) `_decal_opacity` still paints an *occluded* face's index at a 0.12 floor, so over an opaque fill that number sits on the wall in front of it — a wrong-face label. Read indices off `flat`, or pass `--annotate none`
| `--highlight`       | under `textured` its vivid outline is the only deliberate line art. Hue comes from `vivid`, `csg`-derived since `--brush-colors` is rejected here. A face removed by the §4.7 cull gets no outline
| `--focus`           | §4.8
| `--show`            | unaffected — the overlays draw at step 3, above the fills (§4.10)
| `--frame`/`--frame-tightness` | set `scale`, which feeds the mip pick
| `--size`            | uncapped (decision 2.4)
| `--from-t3d`        | works **when the referenced textures are readable**. Note a builder-generated snippet has `texture=None` on every poly, so it needs no textures at all — and per §8 it still requires a resolver. Recorded as an accepted consequence of decision 2.6
| `--prefab-dir`      | **does NOT imply "no project."** It overrides only the prefab *library root* (`dispatch._prefab_root`); `_preview_render_data` independently calls `_resolve_project(args)`. So `prefab preview --prefab-dir X --faces textured` succeeds normally from inside a project. The exit-2 case is *no resolvable project*, whatever the flags
| `--out`             | unchanged (always PNG)

**Point actors are unaffected** by `--faces`.

**How `--brush-colors` explicitness is detected.** Its argparse `default` is `"csg"`, so a defaulted
value is indistinguishable from an explicit `--brush-colors csg`, and decision 2.7 rejects only the
*explicit* case. The parser sets `default=None`. **Its three consumers are `dispatch.py:753`, `:854`,
`:861`** — and each is `getattr(args, "brush_colors", "csg")`, whose default does **not** fire for an
existing-but-`None` attribute, so **each needs an explicit `or "csg"`**. Only a non-`None` value
alongside `--faces textured` triggers exit 2.

## 6. Code shape

| Change                                                                     | Where
|----------------------------------------------------------------------------|---
| `world_uv_frame`, `tex_basis_default`, `newell` move to a shared stdlib-only module | new `uedcli/texframe.py`
| `preview._face_normal` is deleted; `preview.py`, **`query.py:13`** and **`polyalign.py:26`** all import `newell` from `texframe`. (A third copy at `builders.py:82` returns `Vec3` and is left alone — noted so it is not mistaken for an oversight) | `preview.py`, `query.py`, `polyalign.py`
| the mip-pyramid accessor + the `bMasked` predicate, on the decoder's typed-result contract | **folded into the texture-decoder item — §12**
| resolve each distinct face ref; map any typed error to exit 2; the four exit-2 validations | `uedcli/dispatch.py`
| `--faces` parsing; `--brush-colors default=None`; three corrected `help=` strings | `uedcli/cli.py`
| the fill rasterizer, depth buffers, focus two-pass, mip pick, texel loop | `uedcli/preview.py`

**The rasterizer is EVEN-ODD SCANLINE with affine UV, not a triangle fan.** `architecture.md` records
that **0.1–0.6 % of faces in real exported maps are concave** (spike `concave-faces/`, live
2026-07-23) — which is why `preview.py` already carries `_poly_is_convex_2d`. A fan triangulation
fills *outside* a concave face. Scanline with even-odd parity handles both cases in one path, and
under ortho `u`, `v` and depth are affine in screen space, so they interpolate exactly from the face's
plane without triangulation. Coverage rule: sample at the **pixel centre** (`x + 0.5`, `y + 0.5`),
matching `render.rs:241-244`.

**The `render_data` seam.** Today `dict[actor_name → PointRender]`; it becomes:

```
PreviewData(points: dict[str, PointRender], faces: FaceTextures | None)
FaceTextures:  by_ref: dict[str, list[tuple[int,int,bytes,bytes]]]   # casefolded ref → mip pyramid
               masked: dict[tuple[str,int], bool]                    # (actor, poly_idx) → §4.3a
```

`by_ref` is keyed on `ref.casefold()` (FName semantics, matching `preview_native._TextureTable`), and
every ref in the set is guaranteed present — an unreadable one exits 2 before rendering, so there is
no fallback slot and no missing-key path.

**All call sites, complete** (round 2 found the earlier list short and "mechanical" overstated):

- `preview._scene_geometry:1446` — `render_data.get(name)` then `if pr is None: continue`. Must stay
  a `.get`, on `.points`; `[name]` would raise `KeyError` for a legitimately-absent point actor
- `preview.render_brushes_pgm:1622` and `preview.render_quad_pgm:1868` — both do
  `render_data = render_data or {}`, which under the new type yields a bare `dict` with no `.points`
  ⇒ `AttributeError` to the user. Both must default to an empty `PreviewData`
- `preview.render_quad_pgm:1870` — `a.name in rd`
- `preview.render_brush_pgm:1563` — a fourth public entry point
- `dispatch._world_aabb:617` — both `in` and `[...]`; `_point_pane_region` and `_resolve_zoom` reach
  it through that
- `uedcli/tests/test_preview.py` constructs plain dicts and migrates with them

**`_preview_render_data` must be restructured.** It early-returns `{}` when the set has no point
actors (`dispatch.py:1036-1038`) — the common case for a brush-only textured preview — so neither
face resolution nor decision 2.6's exit 2 is reachable as written. Its docstring's "a pure-brush
preview works with no game install" stays true for `wire`/`flat` and is now false for `textured`.

## 7. Cost, and the accepted risk

| Layout        | Panes                                             | Pixels at `--size 1024`
|---------------|---------------------------------------------------|---
| `single`      | 1 at `size`                                       | ~1.05 M
| `quad`        | 4 at `size // 2` (`render_quad_pgm`)              | ~1.05 M total — **~1× a single pane**
| `breakdown`   | **N+1 at full `size`** (`_render_breakdown_grid`) | ~(N+1) × 1.05 M

**`--layout breakdown` is the worst case.** Only the per-**brush** panes are `--focus`ed — pane 0 and
every point-actor pane pass `focus=None` (`dispatch.py:774-782`) — so the two-pass count is the brush
count, not N+1.

**On timings, stated honestly.** The one measurement taken is `actor preview` quad @1024 **wireframe**
at 4.6 s (~1.05 M px). That is *not* a fill rate — its cost is dominated by label placement and decal
planning — so it cannot be extrapolated to fills, and this spec makes **no** slower/faster claim
against `--native`. What is certain is qualitative: fills are O(area) where wireframe is O(perimeter),
and a pure-Python per-pixel loop is far slower than the Rust one. **The build takes a real fill
measurement before any doc states a number.**

**The owner re-affirmed "no guard, no ceiling"** (*rejected: exit 2 for `textured` under `breakdown`;
rejected: a stderr cost warning*). Accepted consequence: a large breakdown textured render can run for
minutes with no progress output.

## 8. Failure and degradation

Validation runs in `dispatch` **before any pixel is drawn** — every failure refuses, none degrades.

| Situation                                        | Behaviour
|---------------------------------------------------|---
| bad `--faces` value                                | argparse choice error, exit 2
| `--faces textured` + explicit `--brush-colors`     | exit 2 naming both flags and the conflict
| `--faces flat\|textured` + a scaled/sheared brush  | exit 2 naming the actor and the offending field
| no resolvable project (so no resolver)             | exit 2 naming **which** of `_texture_resolver`'s three causes applies — no user games config, a `ConfigError`, or an empty composed file list (`dispatch.py:936-943`); all three are reachable *with* a valid project, so a generic "no project" message would violate "naming the offending value"
| a **bare (unqualified)** `Texture=` ref            | exit 2 naming the ref **and saying to qualify it as `Package.Name`**. `_decode_ref` rejects an unqualified ref before any lookup, so this is the most common miss on real content; `preview_native._TextureTable` already emits exactly this hint
| a ref that does not resolve, or does not decode    | exit 2 listing **every** such ref in one run (not just the first) with the decoder's typed-error case for each — §12's contract makes "which cause applies" answerable
| a poly with no `Texture` at all                    | `DEFAULT_GREY × shade`, silently — normal, not an error

`conventions.md` puts warn-and-continue under **Rejected**, and a textured render whose faces are
secretly checkerboards is exactly that: the picture looks like an answer.

## 9. Tests

| Test                                                                                | Guards
|--------------------------------------------------------------------------------------|---
| `--faces wire` output **byte-identical** to today for a fixed scene                   | the change is additive — the primary regression guard
| `u = (V − Origin)·TextureU + Pan` on a rotated, pre-pivoted brush                     | the UV convention
| **mip level L samples the same world point as level 0** (the `/2**level` rescale)      | a test of level *selection* alone passes the buggy version
| **mip pick under `--view iso` uses §4.4's `gain`**, and differs from an ortho view      | §4.4 — the value round 2 found unspecified
| a **masked** face's index-0 texels leave `BG` and skip depth; an **unmasked** face's index-0 texels draw normally | decision 2.3, both directions
| a brush with **actor-level `PolyFlags=2`** masks even though its polys carry no flag    | §4.3a's OR — the round-2 defect that would re-hide a motivating bug
| **a synthesized fixture package carrying `bMasked`** exercises the texture-side arm     | neither committed fixture has one and the game corpus is gitignored, so without this the half the spike calls load-bearing ships untested
| a **scaled** and a **sheared** brush each exit 2 under `flat`/`textured`, and still render under `wire` | §4.2, both fields and both modes
| **subtract**: camera-facing faces culled, far faces drawn, an add brush inside a subtract visible, and no wireframe/highlight on a culled face | decision 2.10 + §4.6
| a `nonsolid` sheet renders from both sides                                             | the cull is subtract-only
| a **concave** face fills only inside its boundary                                      | §6's scanline choice; a fan would bleed outside
| two overlapping brushes: nearer wins; coplanar tie goes to scene order                 | §4.7
| point **sprites** and each `--show` overlay survive an opaque fill                      | §4.10
| `--focus`: focused brush visible when fully enclosed; context composited **once** (order-independent) | §4.8's two-buffer mechanism
| `PF_Invisible` (actor-OR'd) faces do not fill and do not write depth                    | §4.9 #4
| `flat` fill RGB for `csg`, `legend`, and the legacy `color_by_csg=False` path, unshaded | §4.5, all three
| bare `--faces textured` succeeds; `--faces textured --brush-colors csg` exits 2          | the `default=None` + `or "csg"` mechanism
| each of the resolver's three `None` causes, a bare ref, and an undecodable ref produce distinct exit-2 messages naming the case | §8
| `stash preview` / `prefab preview` accept `--faces`; `--prefab-dir` inside a project **succeeds** | §3, §5 — the inverted round-2 claim
| `--layout quad` and `--layout breakdown` render under `flat` and `textured`               | untested layouts in both rounds
| non-finite UV (`nan` **and** `inf`) produces a clean result, never a traceback            | §4.3
| a golden PNG of a textured cube                                                           | end-to-end pixel stability
| `uedcli/texframe.py` imports nothing outside stdlib + uedcli                               | §0's no-cargo constraint

**Dropped as unimplementable or vacuous:** the cross-renderer "same texel index" test — `render.rs` is
reachable only as `render_frame` → RGB bytes, never texel indices; the projections differ; and it is
`importorskip`-gated, so it would silently skip on the no-cargo machine §0 protects. Cross-renderer
agreement is instead guarded by `texframe` being the **single shared source** of the UV frame. Also
dropped: "`%` vs `rem_euclid`" (true by definition for positive divisors) and "runs with the native
extension absent" (`preview.py` never imports it — the `texframe` import test is the real guard).

## 10. Deferred

- The Rust port / a non-optional native extension.
- **Scaled and sheared brushes** under `flat`/`textured` — rejected in v1 (§4.2); supporting them
  needs UE1's actual scaled-brush texture-frame behaviour verified first.
- Bilinear filtering, real lighting, mesh rendering for point actors, the `Translucent` polyflag.
- A `texture list --cutout` filter over the catalog's dominant-colour signal.

## 11. The masking spike — DONE

[`spikes/2026-07-26-texture-masked-property/findings.md`](../spikes/2026-07-26-texture-masked-property/findings.md):
the stored property is **`bMasked`**, a UE1 bool written **presence-only** (present ⇒ masked), decoded
by the existing `utexture._read_props`. Two measurements size what decision 2.3 avoided:

- **464 of 2,669** corpus textures use index 0 while unmasked — **17.4 %**. Flat colour swatches
  (`LUM_CoreTex.White`, `.Red`, `.Yellow`, `.SILVER`, `.NAVY` and eight more — **13** in total) are
  **100 %** index 0 and would have rendered as nothing at all.
- **Reserved magenta at palette[0] is not a masking signal** — three unmasked textures park it and
  never use it, while `ArthurCallaway` (2.2 % index-0 usage) has real black there.

Pinned by two `test_engine_facts` regressions against committed fixtures.

## 12. Build order (owner ruling, 2026-07-26)

**The texture-decoder item builds FIRST, with this spec's texture accessor folded into its scope; then
all of this.**

`to-build.md`'s **"Native texture decode for any UE1 package"** (`p1`, on deck, spec + plan
self-contained) rewrites the same component this spec depends on: it **deletes
`TextureResolver.resolve_masked`**, **replaces `resolve`'s `None`-on-miss contract with a typed error
object naming the case**, and adds **`CompMips`**, a second compressed mip array. It also fixes a live
bug — **30 textures in `LUM/Textures/LUM_CoreTex.utx` are unreadable today** — and gates the asset
catalog, so it lands first regardless.

**Folded into its scope** (one texture-API change, not two):

1. **A mip-pyramid accessor** — every mip of a ref as `(w, h, rgb, mask)`, on its typed-result
   contract, replacing this spec's earlier `resolve_mips(...) -> … | None`.
2. **`texture_has_bMasked(ref)`** — `"bMasked" in <the export's property block>` (§4.3a, §11).

*Rejected: shipping `wire`/`flat` first and `textured` after; rejected: waiting for that item without
folding the accessor in (two API changes); rejected: building now against today's decoder.*

**Two consequences to carry into that item's revision:**

- Its plan was **already reviewed**, so widening its scope means its **plan re-enters the plan-review
  round** before it builds.
- Its S2 says a decoder error lets "**the caller** choose the disposition — per-ref requests exit 2;
  enumeration records `undecodable` and continues; **preview degrades and warns**." `--faces textured`
  is a caller that **refuses** (decision 2.6, §8). That is compatible — it is a command the user
  invoked with an explicit flag, not a background frame — but it must be stated there so its builder
  does not assume every preview caller degrades.


---

## 13. Re-entry round 1 findings (2026-07-26, 3 cold Opus) — to fix before round 2

Converged across reviewers unless noted. **No structural finding**; all three stated the design
(pre-CSG ortho tier, `--faces` shape, masking gate, subtract cull) holds.

| # | Defect
|---|---
| 1 | **`flat` must NOT reject scaled/sheared brushes.** §4.2's entire argument is that geometry uses `actor_linear` while the UV frame uses `actor_matrix` — a UV problem. `flat` reads no UV frame at all; its fill is the projected polygon, which `actor_linear` already builds correctly and which `wire` renders fine today. As written, one scaled brush costs you `--faces flat` on the whole level for a reason that does not apply. **Scope the rejection to `textured`.**
| 2 | **§4.4's "mip choice bounds texel fetches to ~1/px … the only cost control" is FALSE.** Under nearest-neighbour sampling there is exactly **one** fetch per covered pixel at every level; mip choice controls aliasing, not work. §7 and decision 2.4 lean on it. **Delete the claim** — §7's honest paragraph (fills are O(area), pure Python is far slower) stands on its own
| 3 | **§4.4 uses the LARGER singular value; minification needs the SMALLER.** Dividing by σ_max underestimates texels/px and picks too sharp a mip. Moot at the default 30° (σ_min = σ_max = 1.2247) but `--iso-angle` has no range validation: measured ratios 1.41 at 45°, 2.24 at 60°, **6.98 at 80°** (~3 mip levels too sharp). `_draw_sphere` computes σ_max for a *silhouette radius*, a different question with the same formula
| 4 | **The cull keys on `classify_brush`, whose mover arm is a documented NAME GUESS.** Its own docstring warns that `CEDoor`/`BreakableGlass`/`TNM.*mover` fall through to `CsgOper`. Under `wire` a misclassification costs a shade; under §4.7 it **deletes every camera-facing face** of that actor. **Key the cull on `CsgOper` directly**, or state the consequence
| 5 | **`actor_polyflags(actor)` does not exist.** The spelling is `preview_native._poly_flags_int(dict(actor.props))`, and importing it into `preview.py` would make the renderer import the module owning `TextureResolver` — against §1's resolver-free invariant. §6 has no row for it. Also the real line has an `if actor else 0` arm the spec's quote drops
| 6 | **§6 misses every `world_uv_frame` importer** — `polyalign.py:27` (used at :251/:324/:411), `tests/test_polyalign.py:445`, `tests/test_preview_native.py:167/181/195` — and misses `preview_native._newell` itself, a **fourth** Newell copy and the one `_world_uv_frame` calls. §6 also never lists `preview_native.py` as a file it changes, though that is where the moved symbols live
| 7 | **§8 rows 4–6 carry no mode qualifier**, so read literally `actor preview` outside a project exits 2 — breaking the default `wire` render and §9's own byte-identical guard
| 8 | **Under `flat`, hidden back-face wireframe edges paint over the fills.** `_scene_geometry` emits an edge for every face regardless of facing and `render_brushes_pgm` draws them with no depth test, so a cube's three hidden faces show through — destroying the "diagram of what occludes what" the `help=` promises. §4.6's cull rule is scoped to subtracts only, so nothing resolves this
| 9 | **§5's `--from-t3d` claim is false.** `brush build --texture` exists and stamps a ref onto every face, so a generated snippet does NOT always have `texture=None`
| 10 | **§5's `--prefab-dir` row is still wrong, in both directions.** No project ≠ no resolver: `config.composed_search_files` accepts `project=None` and falls back to the base dirs, which `_preview_render_data` already relies on. And a valid project ≠ a resolver (§8's own three causes). The trigger is `resolver is None`, not "no resolvable project"
| 11 | **`PF_Invisible`'s only normative home is the divergence table.** §4.7 claims its table is total and omits it; §4.3/§4.10 never mention it; the wireframe behaviour under `flat` is undefined
| 12 | **The depth-buffer representation is unspecified while `--size` is uncapped.** A `list[float]` at `--size 4096` is ~0.5 GB vs ~67 MB for `array("f")`; §8 has no row for `MemoryError`, which would reach the user as a traceback
| 13 | **The rasterizer's interpolation plane is undefined** — which normal, which anchor. Faces are not guaranteed planar (`--from-t3d` reads arbitrary editor T3D). Two implementers get different pixels
| 14 | **§4.6 vs §5 contradict on culled-face DECALS**, and whether a culled face still enters `occluders` — which grades every remaining decal's opacity, so the two readings re-shade annotations
| 15 | **`texture_has_bMasked(ref)` duplicates a field S2's typed result already carries**, i.e. a second way to ask one question — the opposite of the "one texture-API change, not two" argument that justified folding it in. **Read the flag off the typed result instead**
| 16 | **§12 is stale** — it says the two consequences "must be carried into" the decoder plan; they already are (that plan's S2b)
| 17 | **Every `cli.py` citation is stale**: `_preview_opts` is at **686/1476/1513** (spec: 685/1474/1511), `--brush-colors` at **155** (156), `--focus` at **190** (192). Every non-`cli.py` anchor checked out exact
| 18 | **`tests/test_actor_preview.py`'s `_prev` helper hardcodes `brush_colors="csg"`**, which under §5's `default=None` scheme is an *explicit* value — so every existing dispatch test would trip the §2.7 exit 2, and §9's "bare `--faces textured` succeeds" cannot be written without changing it
| 19 | **§4.9 omits the largest divergence:** `--native` renders post-CSG BSP node polys, this tier renders raw pre-CSG brush polys. Decision 2.10's cull exists *because* of it. Also omitted: the fan-vs-scanline concave difference this spec itself establishes, and `BACKGROUND [56,56,60]` vs `BG 224`
| 20 | **Test gaps:** no test for decision 2.5 (`textured` has no wireframe / `flat` does), the `DEFAULT_GREY` no-`Texture` path, §4.1's shade formula, §4.2's zero-axis fallback (which §4.2 justifies as the anti-drift guarantee), or the chosen dim constant. §9's iso-mip test as worded passes with `gain` hard-coded to 1.0
| 21 | **§7's one timing has no provenance** — no scene, actor count, machine, date or file pointer, and its "dominated by label placement" explanation is asserted, not measured
| 22 | **The header links `rationale/preview.md`, which does not exist yet** (`rationale/` holds `cli.md`, `emit.md`, `MIGRATION.md`, `README.md`)

## 14. Needs an owner ruling before round 2

1. **Should `--faces textured` require a texture resolver even when NO face needs a texture?** §8 refuses
   as soon as no resolver exists, before any ref is examined. But decision 2.6 is scoped to "any texture
   *the render needs*", and §4.3 says a poly with no `Texture` is normal. So a brush-only scene whose
   polys carry no texture refs refuses even though it needs nothing. A reviewer flagged this as an
   unrecorded choice that changes observable behaviour, not a consequence of 2.6.
2. **Decision 2.4 was re-affirmed partly on finding #2, which is false.** The "no guard, no ceiling"
   ruling was put with mip selection described as the cost control that made it safe. It isn't one.
   The decision may well stand on its own, but it was taken against a wrong statement and should be
   re-put.
