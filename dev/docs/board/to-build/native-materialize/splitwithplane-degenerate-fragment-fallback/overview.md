+++
priority = "p3"
kind = "debug"
summary = "FPoly::SplitWithPlane degrades a degenerate cut to SP_Back/SP_Front (whole poly, one side); native always returns Split and leaves callers to drop the <3-vert fragment"
+++

# `SplitWithPlane` degenerate-fragment fallback is missing

From a fresh disassembly of `FPoly::SplitWithPlane` (`Engine.dll 0x1518b0`) while auditing the
repartition. After building both fragments the engine `Fix`es each and checks the survivor count
(`FPoly::Fix` = `0x150da0`):

- front `Fix() < 3` → warn, **return `SP_Back` (2)** (`0x151edd`..`0x151f03`)
- back `Fix() < 3` → warn, **return `SP_Front` (1)** (`0x151f0d`..`0x151f3d`)
- both `>= 3` → `SP_Split` (3) (`0x151aa5`)

So when a cut produces a degenerate sliver, the engine classifies the poly as lying WHOLLY on the
other side, and the caller carries the **original, uncut** poly down that branch.

Native's `FPoly::split_with_plane` (`uedcli-native/src/fpoly.rs`) always returns
`Split::Split(front, back)`. Each caller then deals with the degenerate half its own way:
`split_poly_list` drops a fragment whose `fix()` is under 3 but keeps the CUT other half (whose ring
carries the two cut vertices, not the original ones), and `filter_ed_poly`
(`uedcli-native/src/bspcsg.rs:701`) does not check at all — it recurses with a <3-vertex poly.

Reachability is low: a poly only reaches the split branch with a vertex more than 0.25 in front and
one more than 0.25 behind, so a fragment collapses only when the two cut points fall within
`THRESH_POINTS_ARE_SAME` (0.002) of each other or of a ring vertex. Not measured, and no observed
divergence is attributed to it — filed so the decode is not lost.

**Do not fix it by having `split_with_plane` return `Split::Back`/`Split::Front` for everyone.**
Two callers stand in for `SplitWithPlaneFast` (`Engine.dll 0x151f90`), the classify-only variant,
and it has NO degenerate fallback — it returns purely from its `has_front`/`has_back` flags
(`0x152070`). Those callers are `find_best_split_exact` (`uedcli-native/src/bspcsg.rs:1363`, the
`FindBestSplit` scoring loop) and `build.rs:271`. Giving them the fallback would silently change
scoring. The fix has to separate the two roles.

Related, from the same comparison: those two callers use the FULL `split_with_plane` where the
engine calls `SplitWithPlaneFast`. The two disagree at exact equality — with `MaxDist == +0.25` and
every other vertex in band, `Fast` returns Coplanar (unscored) while the full routine returns Front
(scored into `|F-B|`) — and the full routine also allocates two fragment `Vec`s per straddling pair
in the hottest loop of the build.
