+++
priority = "p1"
kind = "debug"
summary = "level preview --game fails qualify_level_textures on imported retail levels (content/order drift)"
+++

# `level preview --game` fails `qualify_level_textures` on imported retail levels

`level preview --game` on an IMPORTED retail trunk fails in materialize at the texture-qualify step:

```
level import dev/games/deusex/Maps/02_NYC_Bar.dx --tree level/nyc-bar   # 203 brushes
level preview --game --tree level/nyc-bar --out-dir OUT "at:@PlayerStart0;rot:0,-16264"
# → materialize for preview failed: qualify_level_textures: no OBJ DEPENDENCIES Engine.Polys
#   block matches brush 'Brush9''s 6 textured polys ['Uob_Concrete','NYCstonBloc_A','Bricks_b',
#   'Bricks_b','Bricks_b','drtywater_a'] — 201 of 208 non-empty blocks still unclaimed
```

(Wanchai `--game` fails EARLIER — editor wedges on `OBJ DEPENDENCIES` for 1304 brushes; that's a
separate item. This one is the qualify step, reached because NYC Bar's 203 brushes materialize.)

## Mechanism (read `qualify.py::qualify_level_textures`)
Materialize drives `OBJ DEPENDENCIES PACKAGE=MyLevel`, which dumps one `Class Engine.Polys` block per
brush with each poly's FULLY-QUALIFIED texture ref. `qualify_level_textures` binds each trunk brush to
its dump block by EXACT match of the ordered per-poly texture object-NAMES (`_bare`, first-not-yet-
claimed), then patches the trunk refs to the qualified form. It raises when a brush finds no block.

**201 of 208 unclaimed ⇒ a SYSTEMATIC, near-total mismatch**, not a one-off. The match assumes the
imported trunk's textured-poly ORDER + COUNT + object-NAMES per brush equal the editor's rebuild dump.
Two candidate causes (rank in the spike):
- **Import poly-order/count drift** (dominant suspect): `level import` (`mapimport.py`, .dx→T3D)
  reconstructs each brush's polys in an order/count that differs from the editor's `OBJ DEPENDENCIES`
  walk of the rebuilt map, so the ordered content lists never match. Authored trunks qualify fine
  (their poly order matches the editor's) — so this is an IMPORT→materialize round-trip problem.
- **Missing/misnamed texture** in THIS install: `drtywater_a` is genuinely absent (the `--native`
  render checkerboarded it). A brush whose ref list contains a name the editor's dump omits (or vice
  versa) fails the exact match. Likely a contributor, unlikely to explain 201/208 alone.

## Scope
Blocks `--game` preview AND `level materialize` of IMPORTED retail maps. Does not affect authored
trunks. Distinct from the native-CSG geometry-drop item and the Wanchai editor-wedge.

## Investigation
Spike launched 2026-08-24 (subagent): compare an imported brush's textured-poly order/count/names vs
the editor's `OBJ DEPENDENCIES` block for the same brush; determine whether import drift, missing
textures, or both dominate; recommend whether the fix is in `mapimport` (poly order), `qualify`
(matching strategy), or texture resolution. Findings append here.
