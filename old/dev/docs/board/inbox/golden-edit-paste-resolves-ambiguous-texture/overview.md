+++
priority = "p2"
kind = "unknown"
summary = "On `02_NYC_Bar`, 139/953 surfs' textures differ between native and its self-built golden — and NATIVE is the correct side: the trunk and the ORIGINAL shipped map both say `NewYorkCity.Metal.trough1`, the golden says `NYCBar.Metal.trough1`. The editor's `EDIT PASTE` T3D texture lookup picks a different package when the same leaf name exists in two loaded packages, and drops the texture entirely (`texture_ref = 0`) when the named package was not `OBJ LOAD`ed. A golden-fidelity limit, not a native bug."
depends-on = ["texture-ref-i-actor-divergence-traced-to-golden"]
+++

# The self-built golden's `EDIT PASTE` mis-resolves ambiguous texture names

Found in round 8 of `texture-ref-i-actor-divergence-traced-to-golden`, once surf `texture_ref` was
compared by resolved identity instead of raw import index.

## Measurement

`02_NYC_Bar`: 139 of 953 surfs disagree on the resolved texture path. Every one has the same shape —
same leaf name, different package (and often a different group inside it):

| count | native | golden |
|------:|--------|--------|
| 53 | `NewYorkCity.Metal.NYC_GalvMetl_A` | `NYCBar.Metal.NYC_GalvMetl_A` |
| 24 | `NewYorkCity.Metal.trough1` | `NYCBar.Metal.trough1` |
| 21 | `NewYorkCity.Brick.NYCstonBloc_A` | `NYCBar.Stone.NYCstonBloc_A` |
| 17 | `NewYorkCity.Wood.PoolTable_A` | `NYCBar.Wood.PoolTable_A` |
| 10 | `NewYorkCity.Metal.stall1b` | `NYCBar.Metal.stall1b` |
| 6 | `NewYorkCity.Signs.outoforder1` | `NYCBar.Misc.outoforder1` |
| 6 | `NewYorkCity.Tiles.NYC_ceilin_B` | `NYCBar.Tile.NYC_ceilin_B` |
| 1 | `effects.water.drtywater_a` | `<none>` (golden `texture_ref = 0`) |

## Native is the correct side

- The trunk (extracted from the shipped map by `ingest_dx_trunk.py`) says
  `Texture=NewYorkCity.trough1`.
- The ORIGINAL shipped `02_NYC_Bar.dx`'s own import table says `NewYorkCity.Metal.trough1`.
- `trough1` exists in BOTH `NewYorkCity.utx` and `NYCBar.utx`, in group `Metal` in both.
- That golden's build log shows both packages were `OBJ LOAD`ed
  (`['CoreTexGlass', 'CoreTexMisc', 'CoreTexWood', 'Engine', 'FreeClinic', 'NYCBar', 'NYCBar2_Music',
  'NewYorkCity', 'UNATCO']`).

So the editor had both packages loaded, was handed a package-qualified name, and resolved to the
other package anyway. Mechanism not investigated — a name-only `FindObject` that hits the
most-recently-loaded package would explain it, but that is a guess, not a measurement.

The single `<none>` case is separate and simpler: `effects` is absent from that `OBJ LOAD` set, so
the editor could not resolve `effects.water.drtywater_a` at all and silently left the surface
untextured.

## Why it matters

Two consequences, neither fixed:

- The golden is not a faithful oracle for `texture_ref` on any level whose textures have
  cross-package leaf-name collisions. `parity_report.py` will keep reporting these 139 as
  divergence, and they will never close, because native is right.
- `<none>` shows the golden build can silently drop content when `_level_referenced_packages`
  under-reports the packages a level needs. Worth checking whether that under-reporting affects
  anything beyond textures.

Candidate handling (a decision, not picked here): either widen the golden build's `OBJ LOAD` set and
find out whether that changes the resolution, or exclude cross-package leaf-name collisions from the
`texture_ref` comparison the way session artifacts are excluded — but only after the mechanism is
actually pinned, since "the editor is wrong here" is a strong claim to bake into the oracle.
