+++
priority = "p1"
kind = "implement"
summary = "SHIPPED (c7b8b0b): rot_is_pure_rotation missed pure mirrors (orthonormal rows, det=-1), letting a mirrored Subtract brush's normals get inverted and its own BSP built inside-out -- root cause of the severe under-build family. Area51/Wanchai Garage/Paris Underground/NYC 747/OceanLab Lab all moved from -13%/-27% node deficits to normal noise range; UNATCO/Wanchai Market unaffected."
+++

# Mirrored-brush determinant fix closes the shared severe-under-build family

`native-under-builds-area51-entrance-geometry` root-caused Area51's severe under-build to
`Brush3252` (world-CSG index 5) over-carving, but never shipped a fix. `breadth-geometry-check-on-10-new-og-levels-1-10`
found the same signature (large negative node/surf/leaf deltas, -13% to -27%) on 4 other levels:
Wanchai Garage, Paris Underground, NYC 747, OceanLab Lab. This item confirms and fixes the shared
mechanism.

## Root cause

`rot_is_pure_rotation` (`bspcsg.rs`) checked only that each row of a brush's local-to-world linear
map had unit length — sufficient to reject a *scaled* (non-uniform) map, but **not** a pure mirror
(e.g. `MainScale=(-1,1,1)`): a mirror's rows are still orthonormal, only the determinant sign
(-1 vs +1) distinguishes it from a real rotation.

That let a mirrored Subtract brush's rows pass as "pure rotation," so the §48 subtract-normal-recompute
branch fired and remapped the brush's already-correct `FPoly::finalize()` face normals through the
mirror-baked `rot` — on top of the local winding `brush_marshal.py` had *already* reversed for the
mirror case. Net effect: every face normal on the brush came out inverted (pointing inward).
`build_brush_temp_bsp` then built that brush's own convex partition inside-out, so
`filter_world_through_brush` classified spatially-unrelated world geometry as "interior" and
discarded it — an over-carve with no direct relationship to the brush's actual footprint, matching
the originally-observed symptom exactly.

Live-traced on Wanchai Garage's `Brush24` (confirmed a pure mirror, not a scale).

## Fix

Add a determinant check to `rot_is_pure_rotation`: `det(rot) > 0.0`, alongside the existing
row-length check. A pure mirror now correctly falls through to the covariant `vec_xform`/winding-
recompute path that already handles it correctly for the non-CSG-subtract case.

## Measured (breadth_gate.py, before -> after; UNATCO/Wanchai Market via regression_gate.py, unaffected either way)

| level | nodes before -> after (golden) | surfs before -> after |
|---|---|---|
| Area51 Entrance | 9252 -> 12715 (golden 12630, d=+85) | d=-511 -> d=+0 (exact) |
| Wanchai Garage | 1696 -> 2078 (golden 2146, d=-68) | d=-141 -> d=+0 (exact) |
| Paris Underground | 2017 -> 2319 (golden 2427, d=-108) | d=-177 -> d=+0 (exact) |
| NYC 747 | 3870 -> 4541 (golden 4462, d=+79) | d=-127 -> d=+17 |
| OceanLab Lab | 23045 -> 29998 (golden 29533, d=+465) | d=-4469 -> d=+27 |

Before: -13% to -27% node deficits (the severe-under-build signature). After: node deltas ±0.7-4.5%,
the same range as the corpus's existing "normal" over-build noise; surfs exact or within dozens on
even the largest level tested (29533 surfs). None of the 5 reach full node/surf/leaf exactness yet,
but the *severe* under-build mechanism itself is closed — remaining deltas match the ordinary
over-build pattern already tracked elsewhere in this investigation, not a new distinct bug.

## Verification

TDD: added a pure-mirror case (`[[-1,0,0],[0,1,0],[0,0,1]]`) to the existing `rot_is_pure_rotation`
unit test, red before the determinant check / green after. Full `bin/test`: 12492 passed, 0 failed
(pytest, 8:49) + 90/90 cargo test — independently re-run and confirmed by the coordinating session
after catching a `tail`-truncation bug in the first verification attempt (the reported "exit 0" was
`tail`'s exit code, not `bin/test`'s — re-ran without truncation to get the real pytest summary).
`regression_gate.py`: UNATCO and Wanchai Market both stay node/surf/leaf-exact throughout.

## Not attempted

A synthetic minimal-fixture integration test for the full `rot_is_pure_rotation` -> inside-out-tree
-> misclassification chain turned out to need conditions a minimal fixture can't reach; documented,
not chased further. The unit-level determinant test is the regression pin.
