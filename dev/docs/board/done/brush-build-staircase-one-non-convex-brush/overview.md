+++
priority = "p?"
kind = "unknown"
summary = "`brush build` staircase = ONE non-convex brush + `doctor` T-junction-aware watertight"
+++

# `brush build` staircase = ONE non-convex brush + `doctor` T-junction-aware watertight

— BUILT
2026-07-21. `builders.staircase` now returns a single non-convex `Brush` (UED `LinearStairBuilder`
outer hull: Base + back + per-step Step/Rise + tiled convex Side strips, `2 + 4n` faces, floor-
anchored), reversing the 2026-07-18 box-per-step. `doctor.check_watertight` reworked to
per-supporting-line directed-interval parity (canonical WELD-quantized line key + B2 branch
precedence) so T-junctions read closed while a real hole collinear with a healthy seam still
flags. Multi-actor dispatch branch KEPT (spiral still `list[Brush]`>1); `stair_*` dropped from the
LIVE parity suite (`OFFLINE_ONLY`) with offline value goldens re-blessed. Spec
`specs/2026-07-21-brush-build-single-actor.md`; decisions 2026-07-21 12:06 UTC + 12:22 addendum.
**Remnant:** the native CSG core's convex assumption is now falsified for this brush — tracked as
the `[implement]` "Native CSG core assumes CONVEX brushes" item in `inbox.md`.
