+++
priority = "p1"
kind = "debug"
summary = "OceanLab Lab +27 surf over-build: bsp_validate_brush_links base fixed to authored Origin, now surf-exact"
+++

# OceanLab Lab +27 surf over-build: bsp_validate_brush_links base fixed to authored Origin, now surf-exact

Owner-directed follow-up on the worst-parity levels: OceanLab Lab (`14_OceanLab_Lab.dx`, 1886
brushes). Previously the worst instance of the severe-under-build family attributed to the
mirrored-brush determinant bug (fixed `c7b8b0b`, closed in `native-under-builds-area51-entrance-geometry`).
A 2026-09-01 breadth re-measure showed the shape flipped from severe under-build (nodes -22.0%, surfs
-19.7%) to a much smaller over-build (nodes +465, surfs +27, leaves +86, verts +3958, points +1003,
vectors -66) — a different, unexplored residual.

Full write-up, per-brush attribution evidence, live-verification method and non-regression numbers:
`dev/docs/native-materialize-findings.md`, search "OceanLab Lab +27 surf over-build".

## Summary

Root cause (surf half only): `bsp_validate_brush_links` (`uedcli-native/src/bspcsg.rs`) — the
coplanar-same-brush surf-merge gate — used each poly's `verts[0]` as its on-plane reference point
instead of the poly's own authored `Base` (T3D `Origin=`). 9 identical-shape "2D Loft"
`CSG_Add PolyFlags=32` decorative brushes (`Brush784`/`844`/`858`/`872`/`886`/`904`/`918`/`1852`/
`1868`) carry a few thousandths of a unit of construction noise between their own vertices — enough
to push some genuinely-coplanar face pairs outside the ±0.001 coplanar band when using `verts[0]`,
while their authored `Origin` sits exactly on the intended plane. NOT the same mechanism as the
Area51/mirrored-brush fix (these brushes are unscaled, unrotated, un-mirrored — plain `CSG_Add`, so
`rot_is_pure_rotation`'s code path never applies).

Fixed: `base.push(p.verts.first()...)` → `base.push(p.base)`. Live-verified against a real UED22
build (isolated brush + synthetic ADD-shell/SUBTRACT-room context, since a lone `CSG_Add` brush with
nothing subtracted first is a documented no-op) before shipping. New regression test added
(`validate_brush_links_uses_authored_base_not_verts0`).

**Result: OceanLab Lab surfs now byte-exact (11278=11278, d=+0; was d=+27).** Nodes/leaves/verts/
points/vectors are unchanged by this fix (nodes d=+465, leaves d=+86) — a separate, still-open
residual, most likely the same `bsp_build`/`FindBestSplit`-tie-break repartition-order class of
problem already open on UNATCO/freeclinic08/nsfhq04 (same-face-set, tree-shape-only divergence). Not
investigated further this round.

Non-regression confirmed on all cached goldens (geometry counts unchanged from pre-fix): `DX.dx`
exact on all 6 counts; NYC Bar exact on all 6; Wanchai Market nodes/surfs/leaves exact (verts/points/
vectors residual unchanged); UNATCO nodes/surfs/leaves exact (verts/points residual unchanged).
`cargo test`: 100/100 (99 pre-existing + 1 new). Scoped pytest touching the affected native paths:
169/169.

NYC 747 shows a parallel shape-flip (same breadth pass) with a similar small nonzero surf delta
(+12) — plausibly the same mechanism, not independently re-investigated (breadth over depth per the
task). Worth a quick per-brush attribution check there before assuming a new mechanism.

Harness: `dev/docs/spikes/2026-09-01-oceanlab-overbuild/harness/` (`oceanlab_isolate_golden.py`,
`oceanlab_isolate_check.py`).

## Left uncommitted

This item's code change (`uedcli-native/src/bspcsg.rs`) is uncommitted in the worktree
`breadth-parity-check` per this round's task instructions — the coordinating session verifies (full
non-regression incl. re-running `parity_report.py` on DX.dx/NYC Bar/UNATCO) and commits.
