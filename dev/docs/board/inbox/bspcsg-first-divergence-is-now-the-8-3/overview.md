+++
priority = "p1"
kind = "debug"
summary = "bspcsg first-divergence is now the §8.3 cospatial-facing-in surplus face — NEEDS A LIVE DIFFERENTIAL TRACE, do not guess"
+++

# bspcsg first-divergence is now the §8.3 cospatial-facing-in surplus face — NEEDS A LIVE DIFFERENTIAL TRACE, do not guess

p1 **bspcsg first-divergence is now the §8.3 cospatial-facing-in surplus face — NEEDS A LIVE
DIFFERENTIAL TRACE, do not guess.** The FindBestSplit param fix LANDED 2026-07-17 (Balance 50→12,
PortalBias 70→0, Opt=GOOD stride `max(NumPolys/10,1)` on the repartition path only; temp-brush kept on
its invariant OPTIMAL/50/70) + `bspOptGeom` wired after `bspRefresh`. Over-fragmentation is FIXED:
full-castle nodes 1263→**1028** (editor 1156), surfs 454, points 1579, `NumSharedSides` 0→940. But the
node-for-node matching prefix is STILL 0 — node[0] (the repartition ROOT splitter) differs. The N=2
subset differential (`harness/subset_diff.py diff 2`) isolates the cause cleanly: **shared planes 14,
only-native 1, only-editor 0** — native carries all 14 editor node-planes PLUS exactly ONE surplus
face (WallBack's floor-coplanar bottom face `(0,0,-1,0)`), and that extra face flips FindBestSplit's
root choice. The param fix itself is CORRECT (it reproduces the editor node-for-node on the editor's
OWN 14-face soup — `harness/validate_params.py`). The surplus face is the §8.3 `F_COSPATIAL_FACING_IN`
classification: native mis-classifies it as FACING_OUT (filter 5, added) where the editor gets
FACING_IN (filter 4, dropped). This is the §8.3 coplanar Outside-seed nuance — **already tried and
REVERTED once (no improvement), and the §7b coplanar-goto branch is genuinely ambiguous from static
disasm; decode doc §8.3 says "do not re-apply blind; trace first."** So: STOP for RE — a node-for-node
repartition/coplanar differential trace against the live editor to pin which `Outside` the back-subtree
descent seeds when the coplanar node IsCsg. (spec §"Secondary residuals" #1.)
