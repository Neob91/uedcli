+++
priority = "p2"
kind = "debug"
summary = "Island is byte-exact N=1..122 and bails at N=123: native gives world leaf 26 a permeating-light run UED22 leaves empty. The PORTAL-GRAPH root cause is DISPROVEN — Pass B is now a faithful `MakePortals` port and UED22's own log reports the same 580 portals / 163 leaves / 427 nodes. Next step: a runtime dump of `AddPortal`'s fragments."
spikes = ["dev/docs/spikes/2026-09-06-island-n123-portal-graph/", "dev/docs/spikes/2026-09-06-permeating-beam-plane-normalize/"]
+++

# Island N=123 — world `Model2` leaf 26 gets a permeating-light run UED22 does not

Found 2026-09-06 pushing the ladder after the zone-actor ancestry fix
(`island-n-93-zone-actor-missed-resolve-zone`) took Island from N=92 to N=122.

## The divergence

`parity_gate.py`: one failure, `BODY model model2: canonical bodies differ`. Every geometry array
(`points`, `vectors`, `bounds`, `leafhulls`, `lightbits`) is byte-identical; `nodes`/`surfs`/`zones`
differ only by export-index permutation and the gate-excluded occlusion bits.

- `leaves[26]`: native `(iZone=1, iPermeating=107, iVolumetric=-1)`, UED22 `(1, -1, -1)`. Every later
  leaf carries native's `iPermeating` exactly **+2**, and `lights` is 1729 vs 1727 — leaf 26's run is
  one light (`Light124`) plus its terminator.
- Exactly **1 leaf of 163** mismatches; every other leaf's run matches in content AND order.

## Not the portal graph either (2026-09-06, corrected)

This item previously blamed `zones::collect_portals`: a plain `1e-4` Sutherland-Hodgman clip where
`FEditorVisibility::MakePortalsClip` uses `FPoly::SplitWithNode(VeryPrecise=1)` and DISCARDS an
`SP_Coplanar` result. That difference was real and **Pass B is now a faithful port of it**
(`dev/docs/spikes/2026-09-06-island-n123-portal-graph/`) — the `WORLD_MAX = 65536` surf-plane quad
from `BuildInfiniteFPoly`, `FindBestAxisVectors`, the ancestor stack, the precise classify/drop, and
`AddPortal` with `MIN_AREA` removed. (`front_leaf != back_leaf` had to stay as a recorded stopgap —
board `portal-graph-builds-self-portals-from-stale`.)

It does not move leaf 26, and the graph was never the problem: `Portalize` prints its own counts into
`Editor.log`, and UED22 reports **580 portals, 163 leaves, 427 nodes, 3 zones** — exactly what native
produces. The same log line also places `Portalize` BEFORE `BspOptGeom` (native runs the flood after
it), but dumping native's leaf-26/27 portals at both points gives identical polygons, so the
deferral does not move this decision either.

## Where it actually is

Native marks leaf 26 once, from light 34 (`Light124`), along
`leaf 85 (seed) -> 32 -> 27 -> 26` (nodes 193, 344, 351). Every gate clears widely (seed descent's
smallest `PlaneDot` is 63.6; the plane gates are -63.6 / -379.9 / -1092.3 against R = 1675; leaf 26's
re-entry radius gate qualifies at 1162 of 1675) and the beam reaches leaf 26 UNCLIPPED.

The tightest of the six beam edges clears by **+1.795**, and it is not a floating-point near-tie: the
constraint reduces to *"is the 27->26 portal quad on leaf 27's side of node 344's plane"*, and the
quad's nearest corner is **1.90 units** inside — measured on the REFERENCE package, whose points and
nodes are byte-identical to native's, on vertices that are real `Model.Points` entries. Moving the
light +/-64 units changes that margin by under 0.03.

`SplitWithPlaneFast`, `ActorVisibility`'s whole clip loop, the `FPlane(A,B,C)` argument order, the
14-vertex break and the portal orientation are all re-verified instruction-exact against native's
port (pinned in `test_engine_facts.py`). So under the algorithm as decoded UED22 should mark leaf 26
and does not.

## Next step — dump the editor's real portal fragments

Every count UED22 reports already agrees with native, so nothing cheaper discriminates. Capture
`FEditorVisibility::AddPortal`'s `(iFrontLeaf, iBackLeaf, FPoly)` triples from a live UED22
`MAP REBUILD` under `winedbg` (INT3 at `Editor.dll 0xa72a0`, base `0x10000000`, no ASLR — the method
the UnrealScript ordering work used) and diff all 580 against native's. That settles whether the
editor's node-344 (32,27) fragment or the node-351 (27,26) fragment differs, or whether
`ActorVisibility` has an undecoded behaviour.

The follow-up this item flagged — `clip_beam` orienting each beam plane by sign-sum instead of by the
clip poly's winding — is **DONE** (`dev/docs/spikes/2026-09-07-permeating-beam-plane-winding/`) and,
as predicted here, does not move leaf 26. It also did not move any level's ceiling: the two
orientations are provably the same wherever the clip poly is convex and the light is off its plane,
and they differed on 7 of 7166 clip edges on NYC_Bar N=152, all of them degenerate (sub-2.5e-4-unit)
edges.

## Repro

    ladder_run.py --dx dev/games/deusex/Maps/01_NYC_UNATCOIsland.dx --from 123 --to 123 --keep-native
    model_dump.py <native_N123.dx> <ref_N123.dx> Model2

The editor-side counts come from a one-off `--log` capture: add a `--log PATH` option to
`build_ued_import_built_golden.py` that snapshots `Driver.log_size()` before the EXEC batch and
writes `read_log_since()` after it (settle by driving `OBJ LIST CLASS=Class` until `Portalized:`
appears — `Editor.log` is 4KB-buffered). **Revert it afterwards**: the file digests into
`actor_parity.recipe_fingerprint()`, so leaving it edited marks every cached ref stale.
