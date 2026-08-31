+++
priority = "p1"
kind = "debug"
summary = "level photo --game fails qualify_level_textures on imported retail levels (content/order drift)"
+++

# `level photo --game` fails `qualify_level_textures` on imported retail levels

`level photo --game` on an IMPORTED retail trunk fails in materialize at the texture-qualify step:

```
level import dev/games/deusex/Maps/02_NYC_Bar.dx --tree level/nyc-bar   # 203 brushes
level photo --game --tree level/nyc-bar --out-dir OUT "at:@PlayerStart0;rot:0,-16264"
# → materialize for photo failed: qualify_level_textures: no OBJ DEPENDENCIES Engine.Polys
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
Blocks `--game` photo AND `level materialize` of IMPORTED retail maps. Does not affect authored
trunks. Distinct from the native-CSG geometry-drop item and the Wanchai editor-wedge.

## Root cause (spike 2026-08-24, verified)
**A parser bug in `qualify.parse_obj_dependencies` — NOT missing textures, NOT import drift.** The
regex `_LINE = r"(?:Log:\s*)?\s*(Class|Texture)\s+(\S+)"` (`qualify.py:16`) captures only dependency
lines whose class token is the literal `Texture`, and silently drops every `Texture` **subclass**
(`WetTexture`, `FireTexture`, `ScriptedTexture`, `WaveTexture`).

`02_NYC_Bar` textures 60 of its 208 brushes with `Effects.water.drtywater_a`, whose export class is
**`WetTexture`** (animated water). The editor's `OBJ DEPENDENCIES` prints each dep as
`<ClassName> <FullPath>` (`spikes/2026-06-19-read-surface-texture-package.md` L63-100), so that poly's
line is `WetTexture Effects.water.drtywater_a` — the regex skips it, the parsed block comes back one
poly short, the brush's authored `want` (6 names) no longer equals the block (5) → the loud raise at
`qualify.py:129`, at the first such brush (`Brush9`). The "201 of 208 unclaimed" is just the abort
state (7 claimed before Brush9), not 201 broken brushes.

Verified: 38 distinct refs, **0 missing** (the earlier `drtywater_a` "miss" was a resolver artifact
from `class_index=None`; with a real `ClassIndex` it resolves — `no-mip-data` because animated, but
present). **60/208** brushes touch the one `WetTexture` — exactly the failing set. Import preserves
per-brush poly order + count (H2 excluded).

## Fix direction
In `qualify.py::parse_obj_dependencies`, not `mapimport`/texture-resolution. Import-INDEPENDENT: an
authored trunk with a `WetTexture`/`FireTexture` on any poly fails identically. Options: (a) within an
`Engine.Polys` block, treat every non-`Class` `<Word> <dotted.ref>` line as a poly texture ref
(smallest); or (b) pass the `Engine.Texture`-descendant class names and accept those prefixes. **Live
check before building:** confirm an `Engine.Polys` block for a subclass-textured brush contains ONLY
per-poly texture lines (no other dependency kind) so a broadened match can't absorb a non-texture line.
Quick win once that's confirmed.

Repro/measure scripts: `_scratch`-external, under the job tmp (`classify_ref_classes.py`,
`measure_nyc_bar_textures.py`, `probe_effects_and_dx.py`). Related native-preview bug filed:
`native-preview-texture-resolver-ignores-texture-subclasses`.
