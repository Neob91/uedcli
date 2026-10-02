# OceanLab N=203: the divergent point's exact provenance, and why it isn't a crossing

Continues `dev/docs/board/to-spike/oceanlab-n-203-world-model2-split-vertex-ulp/`. That item's
2026-09-07 pass ruled out the raw brush transform and every `split_with_plane` crossing near the
divergence using DECIMAL printing; this session re-checked with HEX bit patterns (the method from
`2026-09-13-crossing-vertex-live-capture/`, which found a decimal-hidden sub-ULP bug elsewhere) and
went further: it pins down EXACTLY which computation produces native's divergent value, and narrows
the remaining gap to one specific, well-understood mechanism. Not fixed — no code change landed.

## Recap of the divergence

World `Model2.points`: native holds `(-256.0001220703125, 600.000244140625, -1800.0)` at index 617
and `(-256.0001220703125, 504.000244140625, -1704.0)` at index 619; UED22 holds
`(-256.00006103515625, ...)` at 612/614 instead (2 ULP apart at this magnitude: `0xc3800004` vs
`0xc3800002`, both ~`-256.0`). Multiset-diffed fresh this session (not just index-by-index) against
the current binary (post the 2026-09-13 portal-graph-freeze fix) — unchanged from 2026-09-07.
Both points are `surf.pBase` for surfs 951/953 (`iBrushPoly` 2/5 of `Brush483`, the last actor at
N=203, a CSG_SUBTRACT "2D loft" shape).

## New finding 1: the divergent value is a raw ORIGIN transform, not a crossing

Surf 951's `pBase` traces to `Brush483`'s polygon index 2 (`Item=2DLoftSIDE`, `Origin
-00008.000000,+00072.000000,-00064.000000`, `Normal +Y`). `FPoly::split_with_plane`'s `empty_copy`
preserves `self.base` across a split (it's the plane-defining field, not a per-fragment vertex), so
`bsp_add_point(model, edpoly.base)` (`bspcsg.rs:564`) adds this polygon's own transformed `Origin`
directly — never touching `line_plane_intersection`.

Brush483's `Location=(-240,592,-1712)`, `PrePivot=(8.000122,63.999756,24)` (no `Rotation`; `MainScale`/
`PostScale` are `SheerAxis=SHEER_ZX` with default `Scale=1`/`ShearRate=0`, i.e. true identity — the
`0.05` sheer deadzone gives an exact `0.0` coefficient, `dev/docs/spikes/2026-06-25-scale-transform-mechanics.md`
§3). `fpoly.rs::transform`'s `xf`: `world = Location + Identity·(Origin − PrePivot)`. For
`Origin.x=-8.0`: `-240.0 + (-8.0 − 8.0001220703125) = -256.0001220703125` — exactly native's stored
value.

**Verified this is the UNIQUE f32 result regardless of operation grouping** (checked all three
plausible groupings — `(loc+p)`, `(loc+origin)-pp`, `(loc-pp)+origin` — in Python `struct`-backed f32
arithmetic): every grouping yields `0xc3800004` bit-exact. So a reordering/associativity difference in
the plain translate cannot explain the 2-ULP gap; the transform math itself is not in question.

## New finding 2: native's own point-dedup trace shows a MISS, not a different transform

Ran a native-only build of N=203 with `UEDCLI_BSPCSG_POINT_TRACE="-256.0,552,-1750,120"` (the
existing Stage-1 trace from `2026-09-05-faithful-dedup-fix-attempt/`). At the query for this exact
polygon's base:

    PT tol=0.002 q=(-256.000122,600.000244,-1800.000000) ADD  target=30820
      tval=(-256.000061,600.000244,-1800.000000) gnear=(idx=30820,d=6.104e-5) reach=4336/5198 sb=[] vp=[]

`bsp_add_point_tol` runs the FAITHFUL FNV descent here (`FNV_DEDUP` is on — this is inside
`bsp_brush_csg`'s incremental CSG for Brush483, not the `bsp_build` repartition stopgap the board
also flags). The query MISSES (`ADD`, new point pushed) even though the GLOBAL nearest existing point
(index 30820, the wall's own `line_plane_intersection` crossing value, itself confirmed bit-identical
to UED22's stored value by a companion hex trace on `fpoly.rs::line_plane_intersection` — see below)
is only `6.1e-5` away, two orders of magnitude inside the `0.002` threshold. The trace's own
reachability diagnostic reports `sb=[] vp=[]` for the miss target: at this exact query, point 30820 is
not currently wired to any surf-base or vert-pool slot on a reachable node (its owning wall surf may
be mid-reclassification by Brush483's own subtract).

## New finding 3: no crossing anywhere near x=-256 produces native's divergent value

Added a committed, env-gated hex trace to `fpoly.rs::line_plane_intersection`
(`UEDCLI_LPI_TRACE_NEAR="x[,eps]"`, dumps every crossing's P1/P2/base/normal/output as raw `u32` bit
patterns) and re-ran the whole N=203 native build with `UEDCLI_LPI_TRACE_NEAR="-256.0,0.001"`. Every
one of the crossings this brush's clip against the `x=-256` wall produces (16 hits) computes exactly
`0xc3800002` (`-256.000061035`, UED22's value) — none produce `0xc3800004`. So the wall's OWN crossing
computation is byte-faithful; the divergence is entirely in whether the polygon's `pBase` add gets
deduped onto it.

## What this rules in

Given finding 1 rules out a transform/rounding-order explanation and finding 3 rules out a crossing
formula difference, the remaining explanation is finding 2's own class: a genuine `bspAddPoint`/
`FindNearestVertex` MISS-vs-HIT divergence between native and the editor for this one query, distance
`6.1e-5` inside a `0.002` threshold — the same shape the 2026-09-05 `faithful-dedup-fix-attempt`
Stage 2b live probe found for UNATCO N=8 (editor MISSES where native's linear scan HITS; here the
suspected direction is reversed — native's descent MISSES where the editor's presumably HITS, since
UED22's final value matches the wall's own crossing exactly). This needs the SAME live-editor gdb
capture method that closed N=8/N=19 and, more recently, the Island N=332/UNATCO N=226/WanChai N=58
tie (`2026-09-13-crossing-vertex-live-capture/`, `2026-09-13-portal-graph-frozen-before-optgeom/`):
condition a breakpoint on `bspAddPoint`'s `FindNearestVertex` call with the query bits `0xc3800004,
0x44160004, 0xc4e10000` (verified: the f32 bit pattern of `(-256.0001220703125, 600.000244140625,
-1800.0)`) and read the HIT/MISS + returned index, to settle whether the editor's own tree-state
genuinely differs here or whether this is a faithful reproduction of the editor's own miss (in which
case the real gap is downstream — e.g. why
`bspoptgeom::merge_near_points`'s later 0.25-unit sweep, which SHOULD catch a `6.1e-5` gap regardless
of `bspAddPoint`'s outcome, doesn't remap this pair; native's `merge_near_points` is a faithful,
disassembly-verified port with no reachability gating, so if it's not merging these two points, the
wall's own point (index ~30820 mid-build) may already have been garbage-collected as unreferenced by
`bsp_refresh_points_vectors` before `bspOptGeom` runs — worth checking directly before the next gdb
session).

## What this does not do

No fix applied; OceanLab's ceiling is unchanged (byte-exact N=1..202, still bails at N=203). No mask
or exclusion proposed, per `NATIVE-MATERIALIZE.md`'s prime directive.

## Repro

    dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/ladder_run.py \
      --dx <…>/Maps/14_OceanLab_Lab.dx --from 203 --to 203 --keep-native
    # point-dedup trace (finding 2):
    UEDCLI_BSPCSG_POINT_TRACE="-256.0,552,-1750,120" <same ladder_run.py invocation>
    # crossing trace (finding 3):
    UEDCLI_LPI_TRACE_NEAR="-256.0,0.001" <same ladder_run.py invocation>

## 2026-09-13, later same day — live capture attempt aborted (shared-disk exhaustion)

Re-reproduced N=203: unchanged (still FAILs, same `model2` divergence, current binary post
`f1bd02a4`). Confirmed `point_wired`'s `sb=[]`/`vp=[]` is a full reachable-set DFS, not a
radius-sampled one — point 30820 is referenced by NO currently-live node, not merely "outside a
search radius."

Set out to run the live-editor gdb capture (same recipe as
`dev/docs/spikes/2026-09-05-faithful-dedup-fix-attempt/stage2b/probe_editor_fnv.py`: break at
`Editor.dll`-base-relative `0x100354a1`, right after `bspAddPoint`'s internal `FindNearestVertex`
call, condition on query x bits `0xc3800004`, threshold `0.002`) but stopped before starting any
container. `ued-x86-runtime:latest` (the base image the debug variant needs) was present in
`docker images` at session start and gone minutes later; `df -h /` swung 7.1G -> 159M -> 5.9G free
within ~15 minutes with no build of mine running — a concurrent session (at least the parent's
UNATCO `ladder_run.py` sweep) was consuming the shared daemon's disk hard enough to hit the
1.5GB abort threshold this session was briefed with. Rebuilding the ~4.2GB base image into that would
risk pushing the shared host to true zero during a peak. No image was built; the only docker commands
run were two `docker build` attempts that failed immediately (`pull access denied`, base image
already evicted) before any layer was pulled or written.

The capture recipe is otherwise unchanged and ready to run: same breakpoint, same condition, same
0.002/0.015 threshold split as the N=8 probe. Whoever picks this up next should check `df -h /` and
`docker images | grep ued-x86-runtime` are calm before starting `build-dbg-image.sh`.
