# Scale support — use/store `MainScale`/`PostScale` + offline permanent transform

**Status:** spec (ephemeral) — formalizes the fully-resolved board design (no new decisions; the
gating spike is CLOSED). **Ledger:** [`decisions.md` 2026-07-18](../decisions.md) (records the
2026-06-25 scale decisions, made during the original spiking, into the durable ledger).
**Gating evidence (RESOLVED 2026-06-25, zero open unknowns):**
[`spikes/2026-06-25-scale-transform-mechanics.md`](../spikes/2026-06-25-scale-transform-mechanics.md),
[`spikes/2026-06-25-mainscale-postscale-applytransform.md`](../spikes/2026-06-25-mainscale-postscale-applytransform.md)
(live measurements + `core.dll`/`Engine.dll` disassembly). **Closes** the to-spec item "Scale
support" and the "honour scale" deferral on `actor rotate`.

## 1. Motivation & model
uedcli ignores actor scale today: `MainScale`/`PostScale`/`SheerRate` round-trip as opaque strings,
but every model-side world-geometry measurement (preview, bounds, `query.*`, `rotation.world_vertices`)
drops them — so a scaled/sheared/mirrored brush renders and measures wrong, and there is no way to bake
a scale into geometry. This spec stops ignoring scale.

**Spike-confirmed transform** (the authored actor → world map):
`world = Location + PostScale · R · MainScale · (v − PrePivot)`.
- **MainScale** is **local / pre-rotation**; **PostScale** is **world / post-rotation**; `R` is the
  FRotator matrix (already offline via the GMath table). A negative axis = mirror; `SheerRate`/
  `SheerAxis` add a shear.
- `ACTOR APPLYTRANSFORM` bakes **all three** (`T = PostScale·R·MainScale`) into world-space vertices
  and resets the fields.

## 2. Three parts
1. **USE** scale in the world-vertex path — `rotation.world_vertices` (and every consumer: preview,
   bounds, `query.*`, `writes.actor_bounds`) applies the full `PostScale·R·MainScale·(v−PrePivot)` so
   scaled/sheared/mirrored brushes render and measure correctly.
2. **STORE** it structured — parse `Scale`+`SheerRate`+`SheerAxis` into typed fields (they already
   round-trip as an opaque string; now they're first-class).
3. **BAKE** it — an offline permanent-transform verb (`actor apply-transform`) folds the transform
   into the PolyList and resets the fields.

**Fully offline at runtime** (pure math: `R` is offline via the GMath table, scale is a multiply). The
editor is the **test-time parity oracle only** (one integration-gated suite, like `actor rotate`).

## 3. v1 CLI surface (in the `actor` group, beside `rotate`/`move`)
- **`actor scale <names…|-> (--to | --by) SX,SY,SZ [--pivot X,Y,Z | --pivot-actor NAME]`** — set the
  **MainScale** field. A negative axis = mirror (**no separate `actor mirror` verb**; `mirror` =
  `actor scale --by -1,1,1`).
- **`actor apply-transform <names…|-> [--lock-textures | --no-lock-textures]`** — the offline
  `ACTOR APPLYTRANSFORM`: bake `MainScale+Rotation+PostScale` into the PolyList, reset the fields.
  `--lock-textures` default ON (textures follow the geometry, mirroring the editor's TEXTURELOCK).
- **`actor rotate` gains `--to P,Y,R`** (it has only `--by` today) — the `--to`/`--by` consistency
  pass; also gives the mover `mover key rotate 0` redirect a real absolute target.

`<names…|->` = the compose-pipe stdin form (names from `-`).

## 4. Decisions (all 2026-06-25 — Andrzej; formalized here)
- **`--to`/`--by` symmetric across `move`/`rotate`/`scale`:** exactly one of `--to` (absolute
  field target) / `--by` (relative), a mutually-exclusive REQUIRED group (mirrors `actor move`).
- **`--to` sets the field IN PLACE (`Location` never moves), MUTUALLY EXCLUSIVE with `--pivot`.**
  Reason: `--to` derives a *per-actor* delta (`target ⊖ current_i`), but `--pivot` is a group op that
  only stays coherent with a *uniform* delta — so `--to --pivot` over multiple actors at differing
  values scrambles the group (and equals `--by --pivot` when uniform, adding nothing). `--pivot`
  therefore pairs only with `--by`. *(Rejected: allowing `--to --pivot`.)*
- **`--pivot` OPTIONAL on `rotate`/`scale` (with `--by`)**, default = computed center of the targets
  (`best_grid_pivot`) → in-place. `move` has **no** `--pivot`. The pivot is a transient GROUP-transform
  world center (orbits each `Location`), **NOT** `PrePivot` (D8-protected). *Open (documented, not v1):*
  a single actor whose `PrePivot` ≠ its center still gets a `Location` nudge under the default center;
  a future `--in-place` covers "field-only `--by`, zero `Location` move".
- **`move --to` on MULTIPLE actors** collapses onto one point → single-actor (recommended) or
  anchor-based; `rotate`/`scale --to` don't (orientation/scale are per-actor absolutes).
- **Verb name `actor apply-transform`** (not `bake` — collides with bake-lighting / `BAKEPREPIVOT`).
- **v1 AUTHORS MainScale only; PostScale authoring is the deferred `actor post-scale` verb — but the
  MATH handles the full `PostScale·R·MainScale` chain.** Defer the *verb*, handle the *field*:
  preview/bounds, the clip/vertex-move inverse, and apply-transform all honor a non-identity PostScale,
  because (a) ingested brushes from real maps carry one, and (b) apply-transform must bake all three to
  match the editor or H3 fails. For uedcli-authored brushes PostScale is identity (no-op). *(Rejected:
  rejecting brushes that carry a non-identity PostScale — apply-transform needs it for parity and
  rejecting blocks real maps.)*
- **Geometry edits work DIRECTLY on a scaled brush — no bake-first.** `brush clip`/`vertex move`
  extend their rotation-aware world→local inverse to include `MainScale⁻¹` (a true matrix inverse;
  normals use inverse-transpose). The LLM works entirely in the scaled WORLD frame it previews
  (`preview`/`vertex list`/`poly list` report scaled world coords; edits accept them and de-scale
  internally). *(Rejected: forcing `apply-transform` before editing a scaled brush.)* *Caveat:*
  matching a fractional corner on a scaled+rotated brush can occasionally miss (float ÷ scale;
  `clean()` 0.001 covers common cases) — same family as the rotated-brush note.
- **`mirror` = `actor scale --by -1,1,1`** — no sugar verb.

## 5. Emission format (must byte-match the editor or H3 fails — golden-guarded)
- Write a `Scale` axis iff `≠1.0` (negatives count); write `SheerRate` iff `≠0.0`; `SheerAxis`
  ALWAYS present; omit the whole `Scale=(...)` if all axes are 1.0; 6-dp.

## 6. Bake formula (`actor apply-transform`, `T = PostScale·R·MainScale`)
- `v' = T·v`, **`PrePivot' = T·PrePivot`** (transformed, NOT zeroed), `Location` UNCHANGED, fields
  reset to identity. Confirmed under rotation+PrePivot, not just scale (D8 honored — the bake rewriting
  PrePivot is its explicit intent).
- **Sheer:** axis rule `SHEER_AB ⇒ B += k·A`; the rate→coefficient `k` is an EXACT disassembled
  piecewise snap (`sheer_coeff` in the spike) — no lookup table.
- **Winding:** reverse each polygon's vertex order when `det(T) < 0` (incl. shear; odd # of −1 axes) —
  the editor's own `FPoly::Transform` rule — else it emits an inside-out CSG-crashing brush.

## 7. Guards / footguns
- **Disallow zero (or sub-epsilon) scale factors** → exit 2.
- **Movers:** `actor scale` on a mover → **ALLOW + warn** (keyframe travel `KeyPos`/`KeyRot` doesn't
  scale with the brush). `apply-transform` on a mover → **reject/defer in v1** (the `KeyRot`-vs-baked-
  base interaction is unverified and the bake rewrites `PrePivot` = the swing axis).
- **Warn on `actor rotate` of a NON-UNIFORM-PostScale brush** (stderr, exit 0): rotating it warps it
  (PostScale is world/post-rotation, so old→new = a shear-conjugated rotation) — **inherent UE1
  behavior** (UnrealEd's own gizmo distorts identically, silently). MainScale rotates cleanly; uniform
  PostScale rotates cleanly. Suggest `apply-transform` first. Rare (only ingested brushes). **`brush
  clip` on a PostScale brush is fine.**

## 8. Testing (first-class — mirror the GMath-rotation + builder-parity suites)
- **Offline unit** (CI, no editor): forward-transform coords for every combo (MainScale/PostScale/
  rotation/PrePivot/sheer/mirror + compositions — order is where bugs hide); inverse round-trip
  `world_to_local(local_to_world(v)) == v`; bake → expected PolyList + winding reversal + texture
  vectors under lock on/off + field reset; guards (disallow-0, reject-movers, scale-field
  parse→emit→parse identity).
- **Editor-parity differential harness** (`integration`-gated oracle): a corpus of scaled/sheared/
  rotated/mirrored brushes — incl. PostScale and Main+Post combos — `APPLY`'d in the real editor, baked
  geometry asserted **0-diff** vs the offline bake; asserts emission byte-match.
- **Golden fixtures** frozen from the editor (like `fixtures/builder_parity.json`) so CI guards parity
  without the editor. An **engine-fact** test pins the `sheer_coeff` piecewise snap + the emission rule.

## 9. Touchpoints
`model.py` (typed `MainScale`/`PostScale`/`SheerRate`/`SheerAxis` fields) · `rotation.py`
(`world_vertices` + the inverse gain the scale/sheer factors; `actor_matrix` composition) · `emit.py`
(the §5 emission rule) · `clip.py`/`vertex.py` (world→local inverse includes `MainScale⁻¹`) ·
`builders.py`/`query.py`/`preview.py`/`writes.py` (consume scaled world verts) · `cli.py`/`dispatch.py`
(`actor scale`, `actor apply-transform`, `actor rotate --to`) · a scale/transform algebra module.

## 10. Review-gate resolutions (2026-07-18 — two cold reviews)
Both reviewers verified the transform algebra (bake identity, `det(T)<0` winding, the D8 carve-out for
`apply-transform` rewriting `PrePivot`, and the drop-scale-today motivation) is **sound**. Additive
fixes / hidden work to fold in:
- **Emit must de-dup the typed Scale/Sheer fields against `props`** — exactly as `Location` does
  (`emit.py:123-126`: "never emit a props copy — a stray one would double-emit"). Once
  `MainScale`/`PostScale`/`SheerRate`/`SheerAxis` are typed model fields, they must be PULLED OUT of
  `props` on parse and emitted SOLELY from the typed field, or a stale `props` copy double-emits.
- **`propedit.TYPED_FIELDS` + nested-struct parse are real work the touchpoints hid.** Today
  `TYPED_FIELDS` holds only `"location"` (`propedit.py:864`) and `model.py`'s line parser doesn't
  handle a nested `MainScale=(Scale=(X=,Y=,Z=),SheerRate=,SheerAxis=)` struct. Add: (a) nested-struct
  parse in `model.py`; (b) `MainScale`/`PostScale` to `TYPED_FIELDS` so `actor prop get/set` route to
  the field, not a stale `props` read. **Add `propedit.py` to §9.**
- **`actor scale --by … --pivot` pivot semantics differ from rotate and are inexact on rotated
  brushes** — document/warn: (a) the Location-orbit for scale is component-wise `Loc' = P + S∘(Loc−P)`
  (NOT the rotation orbit); (b) MainScale is local/pre-rotation, so `--by` with a world `--pivot` on a
  ROTATED brush with NON-UNIFORM S doesn't reconcile (scale doesn't commute with R for non-uniform S).
  v1: warn on non-uniform `--by --pivot` over a rotated brush (or restrict), like the rotate-warp warn.
- **`--to` is FIELD-space, an explicit exception to "the LLM works in the world frame"** — on a brush
  with non-identity PostScale the previewed world scale is `PostScale·MainScale ≠ --to`. Rare (ingested
  only) but must be documented, not left implicit.
- **`apply-transform` on a PostScale brush is DESTRUCTIVE + IRREVERSIBLE** (bakes + resets PostScale to
  identity, and there's no PostScale-authoring verb in v1 to reconstruct it) → **warn** before baking,
  beside the mover guard (§7).
- **§5 naming precision:** the emitter targets the `MainScale`/`PostScale` property KEYS (each a
  `Scale`-typed struct); tighten prose that blurs the struct type `Scale` with the field names.
- **Texture-lock (TEXTURELOCK) vectors under mirror+shear = its OWN golden corpus** (§8), not one
  checkbox — it's the hardest parity surface. And pin the `sheer_coeff` piecewise snap as an
  engine-fact test (`test_engine_facts.py`), the one number most likely to need re-derivation.
- `world_to_local_normal` (`rotation.py:289`, today `Rᵀ`) must become the **inverse-transpose** of the
  full linear part `PostScale·R·MainScale` under scale (§4 already says normals use inverse-transpose —
  name the function in §9).
