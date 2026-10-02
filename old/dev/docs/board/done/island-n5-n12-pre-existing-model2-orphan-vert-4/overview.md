+++
priority = "p2"
kind = "debug"
summary = "RESOLVED. Island N=5's six 1-8 ULP Pass-D split vertices came from a mis-pooled surf pBase: the repartition point scan took the FIRST point within 0.002, not the nearest."
+++

# Island N5 world-`Model2` Pass-D split-vertex residual — RESOLVED

## What it was

Island N=5 (`LevelInfo0, Brush296, Brush570, Brush1355, Brush1359`) failed the gate on one residual,
`BODY model model2`: six world `Model2` `Points` differed by 1-8 float32 ULP, all of them Pass-D
landing vertices where an oblique node plane cuts the `x=13312` / `x=-13056` walls.

## Root cause

`Brush1355` and `Brush1359` are the two stacked seawall slabs; their oblique faces are coplanar to
within the pool threshold. Their `FPoly.Base` values are `(-3488, -6336.0, 0)` and
`(-3488, -6336.001953125, 0)` — **0.001953125 apart, just inside `THRESH_POINTS_ARE_SAME` (0.002)**.

`bspAddPoint` (`Editor.dll 0x35430`) dedups through `UModel::FindNearestVertex`
(`Engine.dll 0x1adeb0`), which returns the **nearest** point within the threshold. Native's
repartition-phase stand-in (`bspcsg.rs::bsp_add_point_tol`, non-`FNV_DEDUP` branch) scanned the
retained pool linearly and took the **first** point inside the threshold. `Brush1355`'s base was
pooled first, so `Brush1359`'s surf got it as its `pBase` — 0.00195 off its own plane.

`FPoly::SplitWithNode` (`Engine.dll 0x101517e0`) splits on `Points[Surf.pBase]` /
`Vectors[Surf.vNormal]`, so every Pass-D cut against that node's plane came out shifted by that
0.00195 in y. Reproduced exactly: with base y `-6336.001953125` all four east/west cut values match
UED22 bit-for-bit; with `-6336.0` all four are native's.

The node's own stored `plane.w` was right all along (`6992.7895508 = P1359base · normal`, vs
`6992.7880859` for `Brush1355`'s) — a node whose `plane.w` disagrees with
`Points[pBase] · Vectors[vNormal]` is the fingerprint of this bug. `UEDCLI_SPLIT_DUMP` prints both
per Pass-D split.

## Fix

`a762617` — the repartition point scan takes the NEAREST pool point instead of the first inside the
threshold, which is what the editor's descent returns here. `bsp_add_vector` keeps FIRST-within: it
never consults the tree, it calls `AddThing(..., Check=1)` (`0x35530` → `0x31ae0`), whose scan is
first-match. The `UEDCLI_BSPCSG_POINT_NEAREST` flag that used to gate the rule is gone.

**This narrows a stopgap; it does not make the branch faithful.** An opus review established that the
editor has no linear scan during a rebuild at all: on an FNV miss `bspAddPoint` calls
`AddThing(..., !FastRebuild)` (`0x354d1`) and `csgRebuild` sets `FastRebuild = 1` (`0x4a69f`), so
`AddThing` appends without scanning. Faithful = descend, else append. Tracked, with the decode, in
`repartition-point-dedup-still-uses-a-linear`.

Regression: `bspcsg.rs::repartition_point_add_snaps_to_the_nearest_pool_point_not_the_first`.

Ladder after the fix — Island 1-5 PASS, bails at N=6 (`island-n6-vector-pool-order`); UNATCO 1-28
PASS (fresh refs from N=26), bails at N=29; WanChai 1-44 PASS, bails at its own parked N=45; NYC_Bar
1-58 PASS (fresh refs from N=48, where its first mover appears), bails at its own N=59; OceanLab
1-33 PASS, past its recorded N=13.
