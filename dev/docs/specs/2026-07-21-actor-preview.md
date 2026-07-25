# Spec: `actor preview` — rename `brush preview`, render point actors, collision cylinders

**Status:** ephemeral design scratch. Durable record → `docs/usage.md` + `architecture.md`;
load-bearing choices → `decisions.md` (2026-07-21 16:41). Goes stale once built.

**Board:** `[spec] p2` (Andrzej 2026-07-21). **Coupled to** and **built after/with**
`specs/2026-07-21-brush-preview-ergonomics.md` (same verb; sequencing is a hard dependency — see
§Sequencing). **Revised 2026-07-21 after the two-reviewer gate** (blockers folded in).

**Confirmed by Andrzej 2026-07-21:** global `--show-collision` switch (NOT per-name); clean rename
`brush preview` → `actor preview` (no alias); DT_Sprite → real sprite, DT_Mesh/DT_None → placeholder
marker (+ cylinder).

---

## 1. Rename `brush preview` → `actor preview` (clean, no alias)

Move the verb from the `brush` group to the `actor` group: `brush preview` is
`bsub.add_parser("preview")` (`cli.py:722`) — recreate as `asub.add_parser("preview")` and **remove
it from `brush`**. No alias. **Full cascade (a banner is NOT enough — reviewer L3):**
- `cli.py:722` (parser move); `dispatch.py:3035` branch (`args.cmd == "brush" and args.sub ==
  "preview"` → `args.cmd == "actor"`); `_preview_opts` help.
- **`--tree` exclusion foot-gun (reviewer L2):** `cli.py:161`'s `_tree_flag` docstring explicitly
  excludes `brush preview` from `--tree`; other `actor` verbs DO take `--tree`. `actor preview` must
  still be excluded — update the docstring and flip `test_tree_flag.py:301`
  (`["brush","preview",…]` → `["actor","preview",…]`).
- **`ValueError` catch relocates (reviewer #6/L4):** the ergonomics spec wires a selector `ValueError`
  catch at the preview dispatch (`dispatch.py:3039`, `KeyError`-only today); the rename moves that
  branch to `args.cmd == "actor"` — the catch moves with it.
- Tests: `test_stash_dispatch.py:224/246`, `test_tree_flag.py:301`, plus `test_cli.py` /
  `test_actor_name_resolution.py`.
- Docs: ~64 `brush preview` hits across `docs/` (usage.md, architecture.md, board, specs). **Flip the
  ergonomics spec's BODY too** (title, §-headers, testing) — its banner alone leaves it stale.
- `stash preview` / `prefab preview` KEEP their names (they're `stash`/`prefab` subcommands).

## 2. Render point (non-brush) actors

### 2a. The TWO filters to relax (reviewer B1/#1 — the spec's original claim was wrong)

Point actors are dropped in **two** places; BOTH must change, and the CSG/bbox filters must NOT:
- `preview.py:236` `if not actor.brush: continue` — relax to render point actors.
- **`_brush_actors_from` (`dispatch.py:430-434`)** `… and level.actors[n].brush` — feeds
  `_preview_stash` (`:439`) and prefab preview (`:713`) *before* the renderer, so **stash/prefab
  preview do NOT "inherit for free"** — they silently drop point actors until this filter is relaxed.
  Give preview an **unfiltered** actor path (a param/variant), leaving `_brush_actors_from`'s
  brush-only behavior intact for any non-preview caller.
- **Do NOT touch** `dispatch.py:354/564/623` — those are the stash-intersect/deintersect CSG
  generators + bbox `union_bounds` helpers, which MUST keep filtering to brushes. (The original spec
  wrongly cited these.)
- The top-level `actor preview` path (`dispatch.py:3035-3043`) already passes actors unfiltered (they
  die at `preview.py:236`).
- Update the stale warning `dispatch.py:398` `"nothing to render (no brush actors in the set)"` — wrong
  once point actors render (reviewer #7; natural regression anchor).

### 2b. Field resolution + render-API change (reviewer B2/#4 — the bulk of the real work, unscoped before)

`DrawType`/`DrawScale`/`CollisionRadius`/`CollisionHeight`/`Texture` are **NOT on the parsed `Actor`
model** (`model.py:62-82` has only name/cls/props/location/brush/scales/folder), and **`preview.py`
has no resolver** (imports only `model`/`rotation`). So:
- **Resolve in DISPATCH**, not in `preview.py`: instance prop else class default via the
  `_class_defaults` seam (`dispatch.py:2059`; `resolve_class_defaults`, `uprops.py:900`), and build a
  `utexture.TextureResolver` from `config.composed_search_files(...)` for sprite decode.
- **Extend the render-function signatures** (`render_brushes_pgm`/`render_quad_pgm`/`render_brush_pgm`,
  `preview.py:215/222/309`) to accept **resolved per-actor render-data** — a small frozen dataclass
  per point actor: `DrawType`, decoded sprite `(w, h, rgb, mask)`, sprite world-size, cylinder
  `(radius, height)`. `preview.py` stays resolver-free; dispatch computes the render-data. This API
  change is the core of the work.

### 2c. Schema-unavailable fallback (reviewer B3 — MUST define, else `SchemaError` hits the user)

Resolving a point actor's `DrawType` needs the game `.u` schema, which raises `uprops.SchemaError`
when unbuildable (no fallback — decision 2026-06-26 14:10). Define:
- **Brush-only previews stay schema-free** — do NOT resolve fields for brush actors (geometry needs no
  schema); a pure-brush `actor preview` works with no game install, exactly as today.
- **A point actor with unresolvable schema degrades to an unscaled labeled marker** + a one-line
  stderr note; **never a traceback** (per the CLI "no exception reaches the user" rule). Same for the
  cylinder in §3 (skip + note if radius/height unresolvable).

### 2d. DrawType branch

- **`DT_Sprite` → the real sprite.** Resolve the effective sprite texture (instance `Texture`, else
  class default). **Strip the `Texture'Package.Group.Name'` wrapper** (`uprops.render_object_ref`,
  `uprops.py:842`) before `TextureResolver.resolve()` — which expects a bare `Package[.Group].Name`
  and returns `None` otherwise (reviewer M2). Draw as a **billboard**: a new **scaled nearest-neighbor
  bitmap blit** primitive (today's renderer has only `_px`/`_line`/`_fill`/`_box`/`_dot` — no textured
  blit, reviewer M1), with **masked transparency** (DeusEx editor sprites are masked; palette index 0
  = transparent — `mip0_to_rgb` has no alpha out today, so a masked decode / companion mask channel is
  needed). Define **draw order** (sprite under the wireframe/highlight edges). **World footprint =
  `DrawScale · USize` × `DrawScale · VSize` (1 texel = 1 world unit at `DrawScale` 1), centered on
  `Location`, billboarded** — source-exact, `spikes/2026-07-21-unrealed-sprite-radii-rendering.md` Q1
  (`UnSprite.cpp` `FDynamicSprite::Setup`). Honor the actor's real `DrawScale` (the in-game footprint);
  the editor's *icon overlay* path forces `DrawScale=1`, which we do NOT emulate (we want the true
  size for placement judgement).
- **`DT_Mesh` / `DT_None` → a small labeled marker** at `Location` (true mesh render deferred to the
  class-screenshot / in-engine path). **Acknowledged limit (reviewer #8):** a large mesh decoration
  reads as a tiny dot — no size cue; `--show-collision` only mitigates when the mesh has a cylinder.
- **Sprite miss vs non-P8 (reviewer M3/#5):** `resolve()` returns `None` for BOTH not-found and
  non-P8, so use `TextureResolver.exists()` (`utexture.py:318`, True for a real-but-undecodable
  texture) to distinguish: exists-but-undecodable → non-P8, marker + a note citing the tracked non-P8
  decoder item; truly absent → marker (open-Q fallback). P8 claim verified (`utexture.py:370`).

### 2e. Interaction with the ergonomics spec

- Poly selectors (`--zoom-poly`/`--highlight-poly`, `BRUSH:idx`) are meaningless for point actors (no
  polys) → a selector naming a point actor is a clean named error (no traceback).
- **CSG-color gate (reviewer #3 — real bug):** `_csg_oper(actor)` (`dispatch.py:554`) returns
  `"CSG_Add"` for ANY actor lacking a `CsgOper` prop — including every point actor — so the ergonomics
  §4 palette would paint markers/sprites additive-blue. **Gate the CSG-color branch on `actor.brush is
  not None`**; point markers/sprites use their own neutral color. Add a test.
- Point actors contribute to framing/bbox (Location + sprite/cylinder extent); a pure point with no
  sprite/cylinder = a zero-size box at `Location`. Composes with `--zoom-factor`/`--zoom-region`.

## 3. `--show-collision` — faint red collision cylinders (global boolean)

Boolean `--show-collision` on `_preview_opts` (shared → `actor`/`stash`/`prefab preview`). Draws a
**solid light-red** cylinder (NOT alpha — the renderer has no blend buffer, reviewer L1) for every
previewed **actually-colliding** actor — gate on **`bCollideActors`** (UED's radii view guards on
exactly this — spike Q2 `UnEdCam.cpp`), with `CollisionRadius`/`CollisionHeight` resolved via the §2c
seam (skip + note if unresolvable). So a no-collision Light/decoration draws nothing (Andrzej-confirmed
2026-07-21: colliding actors only, not literally every non-brush actor). No per-name flag: the
previewed SET selects; to spotlight one, preview that one actor (the `actor bbox` "set IS the selection
/ no `--union`" principle).

**Geometry — source-verified (`spikes/2026-07-21-unrealed-sprite-radii-rendering.md` Q2, ✅ UE1 v200
source `UnEdCam.cpp`; corroborated by `kb/actors-collision-pathing.md`):**
- `CollisionRadius` = horizontal radius (UU, as-is); `CollisionHeight` = **half**-height, so the
  cylinder spans `Location.Z ± CollisionHeight` (total `2·CollisionHeight`); **always upright /
  world-axis-aligned regardless of actor rotation**.
- Per-view (UnrealEd's own `SHOW_ActorRadii`): **circle** radius `CollisionRadius` in TOP; **rectangle**
  `2·CollisionRadius` wide × `2·CollisionHeight` tall in FRONT/SIDE; ISO/perspective = an **8-sided
  wire cylinder** (added in UnrealEd 2.x, which Deus Ex ships — 🔬 patch-notes; the ortho circle/rect
  is ✅ source). This resolves the earlier ISO open question.

## 4. Range overlays — `--show-sound-range` / `--show-light-range` (Andrzej 2026-07-21)

Same `--show-*` overlay family as `--show-collision`, on the shared `_preview_opts` (→ all three
preview verbs). Each is a global boolean drawing a faint sphere/circle for the relevant radius,
resolved via the §2c schema-default seam (skip + note if unresolvable):
Conversions are **source-exact now** (spike Q3, ✅ UE1 v200 `AActor.h`; the byte is 0–255, the `+1` is
real — `LightRadius=0` still reaches 25 UU):
- **`--show-light-range`** — for light-emitting actors (`LightType != LT_None`, brightness &
  `LightRadius` set), a faint sphere of `WorldLightRadius = 25·(LightRadius + 1)` UU.
- **`--show-sound-range`** — for actors with an `AmbientSound`, a faint sphere of `WorldSoundRadius =
  25·(SoundRadius + 1)` UU.

Per-view rendering mirrors §3 (circle in each ortho view — reach is spherical, no view guard; 8-sided
wire sphere/cylinder in ISO). **Colors:** UED draws collision + light both dark red and sound dark
blue — since collision and light are separate toggles that can be on together, keep **collision =
red** and **sound = blue** (UED-faithful) but **deviate light to a distinct hue** (they'd otherwise be
indistinguishable). Overlay colors must also stay distinguishable from the CSG brush palette (§4 of
the ergonomics spec: add=blue, subtract=yellow, …) and the highlight — pick the exact faint RGBs at
build (seed from UED's `Default.ini` values in the spike). **Scope:** ship `--show-collision` in this
spec; `--show-sound-range`/`--show-light-range` are a **follow-on** in the same spec (no new rendering
machinery beyond §3's circle/sphere now that the conversions are pinned).

## Sequencing (hard dependency — reviewer L4)

`actor preview` **cannot land before the ergonomics spec is built**: §2e's selector error depends on
ergonomics §2's `BRUSH:idx` selector + its `ValueError` catch; §2e's CSG-gate depends on ergonomics
§4; "red is free" (§3) depends on the highlight moving off red (ergonomics §3 / `decisions.md`
14:34). Both specs edit `_preview_opts`, `preview.py`'s render signatures, and the same dispatch
branch — build them together (ergonomics first or in one pass), not `actor preview` alone.

## Spike — RESOLVED 2026-07-21 (`spikes/2026-07-21-unrealed-sprite-radii-rendering.md`, ✅ UE1 v200 source)

All three questions the spec must not assert blind are now source-exact:
1. **DT_Sprite display + size:** draws the actor's **`Texture`** prop (default `S_Actor`), footprint
   `DrawScale·USize × DrawScale·VSize` (1 texel = 1 UU at DrawScale 1). (Only unknown left: the actual
   `USize×VSize` of the editor-icon PCXs — read from the game `.utx` at build, not blocking.)
2. **Radius conversions:** `WorldLightRadius = 25·(LightRadius+1)`, `WorldSoundRadius =
   25·(SoundRadius+1)` (the "×27/float" figure was UE2 — discarded).
3. **Radii geometry/colors** confirmed (§3). No pre-build spike remains; fold the numbers as done above.

## Testing

- Rename: `actor preview` works; `brush preview` gone (asserted); `--tree` still excluded on `actor
  preview`; `stash`/`prefab preview` still work.
- **Point actor in a stash/prefab renders** (pins the `_brush_actors_from:434` fix — reviewer 1a).
- DT_Sprite: P8 sprite renders at Location; `DrawScale=2` doubles size; instance `Texture` overrides
  class default; `Texture'…'` wrapper stripped; **masked pixels are transparent** (don't occlude the
  wireframe).
- DT_Mesh/DT_None → labeled marker (not skipped, not a sprite); `--no-label` drops the label.
- **Schema-unavailable point actor → unscaled marker + stderr note, NO traceback**; a brush-only
  preview still works with no game install (schema-free).
- **Non-P8 vs absent sprite distinguished** (via `exists()`), each → marker + the right note.
- **CSG-color neutral gate:** a point actor does NOT get the additive-blue hue (reviewer #3).
- `--show-collision`: an actor with `CollisionRadius/Height > 0` draws the cylinder; **FRONT rect is
  `2·CollisionHeight` tall** (explicit — the half-height off-by-2 trap, reviewer 2b); zero-collision →
  none; off by default; across `actor`/`stash`/`prefab preview`.
- Selector (`--zoom-poly`/`--highlight-poly`) naming a point actor → clean named error, no traceback.
- Framing: point-only scene frames around Locations (+ extents); mixed brush+point frames both.
- **Engine-fact regressions** (pin the spike, per the "pin the finding" rule): `world_light_radius(0)
  == 25`, `(8) == 225`, `(255) == 6400`; `world_sound_radius(32) == 825`; collision box total height
  `== 2·CollisionHeight`, half-width `== CollisionRadius`; sprite footprint `== (DrawScale·USize,
  DrawScale·VSize)`. Keep in a `test_engine_facts`-style module back-referencing the spike.

## Docs to update

- `decisions.md`; `docs/usage.md` (rename + point-actor rendering + `--show-collision`); `leveldesign/`;
  `architecture.md` (`preview.py` render-data API, point-actor rendering, cylinder); cite
  `kb/actors-collision-pathing.md` + `rendering.md` for the geometry facts; flip the ergonomics spec
  body's verb name.

## Out of scope

- True mesh (DT_Mesh) geometry rendering — deferred to the class-screenshot / in-engine path.
- Non-P8 sprite decode — the tracked `[spike/implement] Native non-P8 texture decoders` item.
- DrawScale3D / non-uniform scale; rotated collision (cylinder is upright regardless of rotation).

## Open questions

1. ~~Sprite source + DrawScale world-size~~ / ~~ISO cylinder fidelity~~ — **RESOLVED by the spike**
   (`Texture` prop, `DrawScale·USize`, 8-sided wire cylinder).
2. Sprite fallback when neither instance `Texture` nor class-default sprite resolves → marker (§2d).
3. Actual `USize×VSize` of the editor-icon PCXs (`S_Actor`, `S_Light`, …) — read from the game `.utx`
   at build; not blocking (the formula is pinned, only the texture dims are per-package).
