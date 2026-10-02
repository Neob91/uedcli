+++
priority = "p2"
kind = "debug"
summary = "NYC_Bar bails at N=153: Light5 wrongly lights 3 world stair-tread surfs UED22 leaves dark, and native never lights the closed door's (DeusExMover9) own face either. Zone crossing, cross-light box-test ordering, the world-space/screen-space clip-formula bug class, and box occlusion (round 5) are all ruled out by direct measurement/live capture. Round 6 (2026-09-13) live-captured UED22's own OccludeBsp raster-commit verdict for Light5 directly and found the leading theory (a node-visit-order self-occlusion race) does not hold as stated: UED22 accepts real screen area for these surfaces multiple times and still excludes them. Round 7 (2026-09-14) filled a 928-byte disassembly gap round 6 left untranscribed, fully characterized BOTH of round 6's flagged stack slots, and live-captured them directly keyed by iSurf: NEITHER is the exclusion gate. Round 8 (2026-09-15) settled round 7's AddUniqueItem lead BY DIRECT READ: Light5's own GetVisibleSurfs call genuinely adds surf 67/95/97 to its OWN returned iSurfs array -- GetVisibleSurfs/OccludeBsp are now fully cleared. Round 9 (2026-09-15) statically found and live-CONFIRMED the downstream commit path: a per-surf TArray<AActor*> gather list (Editor.dll 0x100a4ba0-0x100a5010) that Light5 DOES get written into (before=0/after=1, live-verified), which illuminateSurf (0x100a5010+) reads back correctly (count=1) -- AND, critically, round 9 also DIRECTLY REFUTES round 3's foundational 'shadow-ray call site never fires' finding: a fresh live capture on the SAME golden-build recipe shows the raytrace call (0x100a5a04) firing repeatedly for Light5 against tread-region lumels, with genuinely mixed blocked(eax=0)/visible(eax=1) results matching a real partial door shadow. A further, not-yet-identity-confirmed commit step (0x100a5ab5-0x100a5ac2, gated by a per-light 'any lumel visible' flag) was found past the raytrace loop. Not fixed; no mask; next step below."
+++

# NYC_Bar N=153 — three world `LightMap` records get a light run UED22 leaves empty

Found 2026-09-06 pushing the ladder after the permeating-beam-plane fix
(`nyc-bar-n-151-world-model2-leaf-permeating-light`) took NYC_Bar from N=150 to N=152.

## The divergence

`parity_gate.py`: one failure, `BODY model model2: canonical bodies differ`.

    bbox/sphere/vectors/points/bounds/leafhulls/leaves/numsharedsides/tail   SAME
    nodes / surfs / zones                                                    permutation only
    lightmap / lights / lightbits                                            REAL

- The per-leaf permeating region is CLEAN: 0 of 155 leaves differ in run content or order, so this
  is `Model.Lights` region 2 (the per-surf raytraced shadow runs), not the portal flood.
- `lightmap` records **4, 8 and 12** carry `iLightActors` `0x149`/`0x14b`/`0x13f` in native and
  `-1` in UED22, with a real `DataOffset` where UED22 has 0. Everything else in those records
  (`Pan`, `UBits`/`VBits`, `iTexture`) matches.
- `lights` is 484 vs 478 — the six extra entries are those three runs (one light + terminator each).
  `lightbits` is 6003 vs 5891 — 112 extra bytes, the three extra records' bit planes.
- Records 46/49/50/62 differ only in `DataOffset` and `iLightActors` INDEX, which is the same shift.

So native decides one light illuminates three surfaces UED22 leaves dark. Same FAMILY as
`unatco-n-116-world-model2-light-runs-differ-on`, and here native is a strict superset rather than
trading decisions.

**The `wanchai-n45-spotlight22-light-runs-differ-on-4` sibling this used to cite is withdrawn**
(2026-09-07): those runs were a `FLightMapIndex` decode bug, and that level's real divergence is a
per-leaf permeating light. This item's evidence is independent of that tool — `LightBits` differs by
112 bytes, which no offset misread can produce — but re-derive the `iLightActors` figures with the
fixed `lmdiag.py` before building on them. Spike:
`dev/docs/spikes/2026-09-07-gather-box-verdict/`.

## NOT the OceanLab N=48 / UNATCO N=163 cause (measured 2026-09-07)

Those two were one bug — the gather never retired a zone whose span buffer had emptied, so it marked
`NF_BoxOccluded` on nodes UED22 never box-tests
(`oceanlab-n48-world-model2-lightbits-differ-on`). Rebuilt and gated here before and after that fix:
**N=153 is unchanged, N=152 still passes.**

Also recorded: N=153 fails on TWO bodies, not one — `model model2` and `model
model_deusexmover9`. The mover body was already failing on master before the box-occlusion work
(checked by rebuilding N=153 against `HEAD`), so it belongs to this item, not to that change.

## Root cause found (2026-09-12): native's world-level gather doesn't occlude through a closed Mover

Re-derived the 3 records with the correct `model_dump.py` field layout (`surf.ci[4]` is `iLightMap`,
not the raw `int32` two bytes later — `lightrun_diff.py`/`lmdiag.py`-style scripts that read that
next slot report a false "0 differing runs"; use `model_dump.py` directly). Records **4, 8, 12**
(0-indexed) belong to world surfs **95, 97, 67**, all `PF_HighShadowDetail` (`0x800000`, 16 uu lumel
grid), all sharing texture `-25`. Their node geometry is three stacked stair treads at
`Z=0/-16/-32`, `X` roughly `-3600..-3088`, `Y` `176..560`, with solid vertical riser surfs between
them (nodes 11/18 etc., planes `X=-3120`/`X=-3152`). The one light in all three extra runs is
**`Light5`** (`Location=(-2944.198486,384.973572,129.119934)`, `LightRadius=12` -> world radius
`(12+1)*25=325`) — the first N where `Light5` itself enters the trunk (`order[152]`, 0-indexed
152 = the 153rd actor), so this is a brand-new-light bug, not a geometry regression.

**Ruled out:** the gather's perpendicular-plane-distance filter (`OceanLab N=44`'s fix) doesn't
reject this — the three tread planes sit 145-161 uu from `Light5` along Z, nowhere near the 325 uu
radius, unlike OceanLab's 1026-vs-1025 near-miss. Confirmed by direct probe (see below) that this is
a **gather-stage (`GetVisibleSurfs`) over-inclusion**, not a per-lumel `line_clear` raytrace bug: a
throwaway `#[test]` in `visible_surfs.rs` parsed native's own built `Model2` body
(`model_read::parse`) and called `get_visible_surfs(&model, light5_location)` directly — it returns
surf 95/97/67 as visible, so `light::bake`'s `gathered()` predicate never even reaches the per-lumel
raytrace with a false verdict; the gather itself is wrong.

**The actual occluder: `DeusExMover9`, a closed wooden door, standing exactly at the gap.** Its
trunk actor:

    Begin Actor Class=DeusEx.DeusExMover
        Location=(X=-3088.000000,Y=416.000000,Z=0.000000)
        Rotation=(Yaw=32768)
        bIsDoor=True
        ClosedSound=Sound'MoverSFX.door.WoodDoorClose' ...

`X=-3088` is exactly the world-BSP boundary plane between `Light5`'s side (`X>-3088`, where `Light5`
sits at `X=-2944`) and the stair treads (`X<=-3088`, descending away from the light). The world model
has an OPENING there (nodes 89/90/93/94/100/101, all on the `X=-3088` plane) that the closed door
brush fills. **`model model_deusexmover9` ALSO fails the N=153 gate** (already noted above) — and its
divergence is the MIRROR IMAGE of this one: UED22's `lights` includes `Light5` on the door's own
surf 4 (`iLightActors` -> `[Light5, None]`), native's is empty (`[]`). So UED22's real behavior is:
`Light5` lights the door's own face (surf 4, facing the light) AND is blocked by the closed door from
reaching the stair treads behind it; native does the opposite on both counts — it lights the treads
straight through the door and fails to light the door's own face.

**This is the documented, previously-"assumed to never fire" gap**, `visible_surfs.rs`'s own header:
"**Moving-brush filter (step 3)** ... is not modeled. The board item says whether `BrushTracker` is
even non-NULL during `LIGHT APPLY` is undetermined, and native has no dynamic-brush tracking to
answer it ... assumed to never fire." `uedcli/native/unbuilt.py`'s `light_apply_movers` docstring
(from the NYC_Bar N=59/N=151 mover work) already describes the real mechanism from disassembly:
`FMovingBrushTracker` (`Engine.dll 0x1014d250`) mirrors every mover poly into a **transient** world
`Surfs` entry, appended after the world's own surfs, so the mover's geometry participates in the
SAME bake as a real occluder/target — then those transient surfs are dropped at the end of the bake,
leaving only the `iLink` bookkeeping and (per mover) a `PrecomputeSphereFilter` leaf-flag pass. Native
currently only uses that mechanism for the mover's OWN lightmap indices (`brush_lightmap_indices`)
and the `iLink`/sphere-filter side effects — the world's own `light::bake` /
`visible_surfs::get_visible_surfs` never sees the movers' transient surfs, so it can neither be
occluded by a closed door nor light the door's own face through the same gather.

**Not fixed.** The real fix is structural, not a local tweak: the world gather/raytrace and the
movers' bake need to run against ONE shared scene (world surfs + every mover's transient mirror,
matching `FMovingBrushTracker`'s real object lifetime), not two independent passes
(`light::bake` for the world, `light_apply_movers` for movers) that never see each other's geometry.
That is a larger change touching `light.rs`, `visible_surfs.rs`, and the `unbuilt.py`/`lib.rs`
orchestration between them — scoping and building it is follow-up work, not a local patch here. No
mask was added; the gate is untouched.

## Further static RE (2026-09-12) — the "moving-brush filter" theory does not hold as stated

Disassembled the two `FMovingBrushTracker` functions the theory above rests on
(`Engine.dll`, base `0x10000000`, no ASLR):

- **`Attach`, `0x1014d250`** (called per mover poly): allocates one `FBspSurf`, appended to
  `Model->Surfs` (three `TArray::Add`-shaped calls off the model's `+0x98` array header), and fills
  it exactly as the `nycbar-n59-light-apply-movers` spike already described (`iBrushPoly`/lightmap
  slot, `PolyFlags & 0x3cffffff` [+ `0x100000` on the `+0x1a8` bit-1 mover bool], `Actor` = the
  mover). It writes **nothing** shaped like a `Model->Nodes` element (no write scaled by the 64-byte
  `FBspNode` stride) — confirms the spike's own surf-only description, and rules out a static world
  node ever being handed a dynamic `iSurf` by this function.
- **`Update`, `0x1014d530`**, and its recursive helper **`0x1014ca00`**: `Update` does re-detect a
  moved/rotated mover (compares `+0x3a0.. / +0x3c4..` against `+0xd0.. / +0xdc..`) and, on the
  "still in old spot" path, walks `Model->Nodes` — `0x1014ca00` recurses over the WHOLE reachable
  subtree from an `iNode` argument via the node's own `iChild[1]`/`iChild[0]`/`iPlane` fields
  (`+0x24/+0x20/+0x28`, the same convention already documented elsewhere in this codebase), guarded
  by `NodeFlags & 0x20` (`NF_IsNew`) as a visited bit, and per node consults a table at
  `Model+0x50` indexed by `(iNode - Model+0x2c)*8` — if non-null, calls `0x1014be60` (looks like a
  detach/unlink, by its shape) with that value. This DOES touch `Model->Nodes`, but only a per-node
  scratch bit plus an association-table lookup/unlink — a stale-reference cleanup walk over the
  existing static tree, not geometry insertion: no node's `Plane`, `iSurf`, `iChild[*]`, or
  `NumVertices` is written here.

**Net: neither function inserts real BSP structure (planes/children/surf assignment) for a mover's
current pose.** That means the `port-urender-getvisiblesurfs`'s step-3 "moving-brush filter"
(`Level->BrushTracker->SurfIsDynamic(iSurf)` skipping a node) still cannot fire for a STATIC world
node under this reading — no such node's `iSurf` is ever set to a dynamic index by either function
examined. So the leading theory at the top of this item (a shared-scene fix inside
`visible_surfs.rs`/`light.rs` keyed on that filter) is not yet grounded in what these two functions
actually do; the real mechanism that makes a closed mover occlude the world's light bake (and get lit
on its own face by that same light) is still unidentified at the static-disassembly depth reached
here.

**Not attempted, and should not be, without more evidence:** a code change to
`visible_surfs.rs`/`light.rs` inferring a mechanism from this alone would be exactly the "guess a
plausible-sounding fix" the campaign's prime directive forbids. The next step is a live, single-step
capture of a real UED22 `LIGHT APPLY` run on this NYC_Bar N=153 subset, breakpointed in
`GetVisibleSurfs`/`illuminateSurf` for `Light5`, to see live what (if anything) changes about the
gather/raytrace when `DeusExMover9` is closed — same method already used for
`island-n-332-leaf-273-permeating-light-vertex-tie` and `unatco-n-226-leaf-12-gets-a-permeating-
light157`. No mask added; `visible_surfs.rs`/`light.rs`/`unbuilt.py` unchanged this pass.

## Live gdb capture (2026-09-13) — the moving-brush theory does NOT survive contact

Per the standing method (Island N=332 / UNATCO N=226 style), captured a real UED22 `LIGHT APPLY`
run on the N=153 subset live under gdb, harness committed at
`dev/docs/spikes/2026-09-13-nycbar-n153-mover-occlusion/`.

**`mover_occlusion_probe.py`** (breaks in `render.dll`'s `URender::GetVisibleSurfs`/`OccludeBsp`,
addresses confirmed by fresh live disassembly, `harness/disasm_probe.py` → `logs/disasm.log`):

- **`Level->BrushTracker` IS non-NULL during `LIGHT APPLY`** — settles the "NOT determined" question
  in `port-urender-getvisiblesurfs-so-each-light-gets/overview.md`.
- **A real static-tree `FBspNode` DOES carry a dynamic `iSurf`** (310–315, the door's 6
  mover-mirrored surfs) — `SurfIsDynamic` fires true on it during Light5's gather. This CONTRADICTS
  this item's own 2026-09-12 static-disassembly finding ("no node's iSurf is ever set to a dynamic
  index by either `Attach` or `Update`") — some third mechanism (not yet found, likely CSG reserving
  the opening node's `iSurf` for the mover at initial build) does assign it. Worth a separate finding.
- **But** the moving-brush filter, read correctly this time via live disassembly, does NOT prune the
  node's subtree — it only SKIPS THE BOX-OCCLUSION TEST for that one node (`or $0x10,0x37(%edi)` is
  never reached; execution jumps to the same place a `iRenderBound==-1` early-out reaches), then the
  node still runs through `IsFront`/frustum/backface/zone-reachability/emission like any other node.
- **The dynamic-surf node and the 3 tread-surf nodes are NEVER visited in the same cube-map face
  pass** for Light5 (checked directly against the per-hit sequence log): the dynamic hits cluster in
  one face's traversal window, the tread hits in two DIFFERENT, non-overlapping windows. Since
  `OccludeBsp`'s opaque-subtracts-spans occlusion only accumulates within ONE face's shared span
  buffer, the door's surf cannot be occluding the treads by rasterization — they're never in the same
  raster pass at all.

**`illuminate_ray_probe.py`** (breaks in `illuminateSurf`'s own per-lumel `LineCheck` call,
`Editor.dll 0x100a5a04`/`0x100a5a07`, conditioned on `iSurf ∈ {67,95,97}`): `illuminateSurf` IS
entered once per target surf (`SURF_ENTER` fires exactly 3 times, matching "called once per lit
static surface") but **the shadow-ray call site never fires even once** for any of them. Per the
pipeline (§1 reset → §2 gather → §3 allocate → §4 raytrace), this means these 3 surfaces' per-surface
light list is EMPTY by raytrace time — Light5 was never committed to it.

**`gather_disasm_probe.py`** (full live disassembly of `0x100a4ba0`..`0x100a5010`, the gather's
per-surf commit loop that runs AFTER `GetVisibleSurfs` returns its `iSurfs` set, per surf per light):
decoded completely. The only two gates in this whole routine are (1) a light-flag bit test
(`bSpecialLit`-shaped) and (2) the already-known-and-ruled-out perpendicular plane-distance vs
`WorldLightRadius` cull. **No LineCheck, no BrushTracker reference, no other occlusion test exists
in this function.** So if `GetVisibleSurfs` itself had returned surf 95/97/67 in Light5's `iSurfs`
set, they WOULD have been committed to the light list (both known gates pass them: right light-flag
class, and 145–161 uu << Light5's 325 uu radius).

**Conclusion: `GetVisibleSurfs`'s own cube-map render must be excluding these 3 surfaces from
Light5's visible set**, and it is NOT via the moving-brush filter (ruled out above by traversal-order
evidence) and NOT via the known plane-distance cull (ruled out by measurement, 2026-09-07). An
earlier weaker read of this same session's `mover_occlusion_probe.py` log (matching `AddUniqueItem`
hits to Light5's call by sequence-number proximity) appeared to show surf 67/95/97 being added to
Light5's visible set — that was almost certainly a FALSE POSITIVE: `TArray<INT>::AddUniqueItem` is a
single shared template instantiation called from many unrelated places in `render.dll`, and the
tighter, unambiguous `illuminate_ray_probe.py` evidence (reading `illuminateSurf`'s own `iSurf` stack
arg directly, no correlation needed) contradicts it. Trust the direct read.

The real mechanism inside `GetVisibleSurfs` is still open — the two leading unexplored candidates are
(a) zone/portal reachability (step 10 in the port-urender doc: a zone's span buffer never gets
"reachable" until a visible `PF_Portal` surf merges spans into it — this could be a purely geometric
fact about the doorway portal's visibility from Light5's exact position, UNRELATED to the mover's
open/closed state, making the original "closed door occludes" framing a coincidence of geometry
rather than the true cause), or (b) something in the box/frustum/backface filters specific to these
nodes' geometry that native's `visible_surfs.rs` port models differently. Neither is confirmed. **Do
not guess a fix from this alone** — next step is instrumenting `GetVisibleSurfs`'s per-node zone/
portal bookkeeping (`ActiveZoneMask`, `ZoneSpan[].ValidLines`, the `MergeWith` calls) for Light5's
specific call, the same way this session instrumented the moving-brush filter.

The mirror-image half (`model_deusexmover9`'s own face not lit by Light5) is UNCHANGED and still
explained by the already-known, separate gap: `unbuilt.light_apply_movers` never runs the raytrace
half of `illuminateSurf` for a mover's own polys (`nyc-bar-n-59-brush-region-zone-and-ued22`'s spike,
"loose ends" — movers always get `iLightActors=-1`). That gap is real and understood; it is not what
this session's capture was investigating.

## Repro

    ladder_run.py --dx dev/games/deusex/Maps/02_NYC_Bar.dx --from 153 --to 153 --keep-native
    model_dump.py <native_N153.dx> <ref_N153.dx> Model2
    model_dump.py <native_N153.dx> <ref_N153.dx> model_deusexmover9   # the mirror-image half

Live-capture harness (2026-09-13): `dev/docs/spikes/2026-09-13-nycbar-n153-mover-occlusion/harness/`
(`disasm_probe.py`, `mover_occlusion_probe.py`, `illuminate_ray_probe.py`, `gather_disasm_probe.py`).

## Fourth round (2026-09-13, same day) — three more hypotheses ruled out; box occlusion is the untested lead

Re-approached with the state/ordering + hex-precision lens that just closed the Island N=332/UNATCO
N=226/WanChai N=58 tie (`spikes/2026-09-13-portal-graph-frozen-before-optgeom/`). No new live capture
this round — reused native's own `UEDCLI_VISGATE_TRACE_*` env tracer (`visible_surfs.rs`) on a fresh
N=153 build, plus a static `objdump` disassembly of `Editor.dll` (no docker) against the
already-committed `mover-occlusion.log` capture above.

**Zone-crossing ruled out by direct trace.** `UEDCLI_VISGATE_TRACE_SURF=-1
UEDCLI_VISGATE_TRACE_LOC="-2944.198486,384.973572,129.119934"` shows surf 67/95/97's nodes all report
`near_zone=1` — the same zone as `Light5` (`view_zone=1`). No portal crossing/merge is needed to reach
them; `active_mask` already includes zone 1 from the seed. The zone/portal-reachability candidate this
item's "Conclusion" section left open cannot be the mechanism.

**Box-occlusion cross-light ordering ruled out by the code's own invariant.** `light::bake` asserts
every node's `NF_BoxOccluded` starts clear, runs all lights' `get_visible_surfs` in PARALLEL from that
shared clear baseline, then replays `box_tests` into `Model.Nodes` afterward in light order — a real
candidate for an order-dependent bug (UED22's sequential run lets light K's box marks affect light
K+1's amortization gate; native's parallel batch can't see that). Ruled out by the gate's own math: a
node outside the `iNode % 16 == 0` residue class is only ever tested if it's ALREADY marked occluded or
in the residue class, so it can never transition clear->occluded within one bake on EITHER side
(UED22's own `NF_BoxOccluded` also starts clear on a never-before-lit freshly-imported map). Seeding
order cannot matter for this node class.

**`clip_bsp_surf`'s crossing formula is a different function, not the WanChai/Island/UNATCO bug
class.** That fix was `FLinePlaneIntersection` vs a naive `alpha` crossing in a WORLD-SPACE BSP split
(`FPoly::SplitWithPlaneFast`). `visible_surfs.rs`'s `clip_bsp_surf`/`clip_against` also uses an
`alpha` crossing, but it clips a PROJECTED polygon against the six SCREEN-SPACE cube-face frustum
planes (`render.dll 0x10013b70`) — the doorway's `X=-3088` grid coordinate never enters it. The doc
comment's claim that `alpha` IS what `0x10013b70` does is disassembly-confirmed (byte-level opcode
match). Dead end.

**Re-confirmed independently (static disassembly, not just re-trusting the prior live capture):
`illuminateSurf` has exactly one shadow-ray call site, and it never fires for these 3 surfs.**
`objdump -d Editor.dll` over the whole function body (`0x100a5043`..`0x100a5be6`, bounded by `int3`
padding + the next function's prologue at `0x100a5bf0`) finds exactly one `call [eax+0x58]`
(`0x100a5a04`, the address `illuminate_ray_probe.py` already watches). The `0x800000`
(`PF_HighShadowDetail`) test at `0x100a5c3b` belongs to a DIFFERENT, later function (the lumel-grid
step-size selector at `0x100a5bf0`+, not a second raytrace call site) — so "high-detail surfaces use
an unwatched raytrace call", which would have reconciled this item's own "`AddUniqueItem` looked like
inclusion but that's a false positive" tension, does not hold. `illuminate_ray_probe.py`'s zero-hits
finding stands: `GetVisibleSurfs` really does end these 3 surfaces' candidate light list at zero
entries (not just missing `Light5`) — a genuine gather-stage exclusion, not a downstream drop.

**New, untested lead: step-4 render-bound box occlusion, node 16 (native numbering), face 3
(`-X`).** `UEDCLI_VISGATE_TRACE_BOX=1` alongside the same whole-traversal trace shows Light5's face-3
(`-X`, toward the treads) box-testing node 128 (visible), then node 16 (`bound=0`,
`rect=Some([0, 888, 1024, 1014])`, verdict **`visible=false`**, subtree skipped) — sitting in the same
local region of the traversal as the accepted tread nodes (9/13/14/15/20/22/24, surfs 95/97/67). This
is the first concrete, node-identified box-occlusion candidate this item has produced. Untested
because it needs a LIVE capture of the real editor's own box test (`render.dll 0x1001932c`-
`0x1001952a`) for this exact light+face+node to compare the geometric verdict against native's — the
ancestor-chain reasoning done here only shows adjacency, not a mismatch. Also newly observed: Light5's
face-3 box-tests several other bounds (43/164/169/140/79/188/198/254) not previously enumerated here.

Not fixed. No mask. Next step for a future round: live-capture `BoundVisible`'s verdict for node 16's
UED22 counterpart (and its render-bound ancestors) during Light5's `-X` face pass specifically, same
method as `spikes/2026-09-05-lightapply-node-flags`/`spikes/2026-09-06-boundvisible-port`, to see
whether UED22's real box test rejects something upstream of the treads that native's accepts.

## Fifth round (2026-09-13) — node 16 box occlusion is a DEAD END; the real governing ancestor also matches. Not fixed.

Followed up on round four's "untested lead" (node 16, native numbering, rejected on Light5's `-X`
face). Two independent checks, static-then-live, both clear it.

**Static: node 16 is not an ancestor of the divergent surfaces — a pure traversal-order read, no
live capture needed.** Re-ran the N=153 native build with `UEDCLI_VISGATE_TRACE_BOX=1
UEDCLI_VISGATE_TRACE_SURF=-1 UEDCLI_VISGATE_TRACE_LOC=<Light5>` (single-threaded,
`RAYON_NUM_THREADS=1`, for a clean per-light sequential log) and hand-traced `traverse()`'s recursion
from the print order alone. Node 16 is the **far child of node 13's coplanar chain** (13 → 14 → 15,
the three surf-97 nodes) — i.e. a strict DESCENDANT, not an ancestor, of any of the three divergent
surfaces (95 at node 9, 97 at nodes 13/14/15, 67 at nodes 20/22/24). Box-rejecting node 16 only skips
node 16's own subtree; the divergent nodes are chain members/ancestors that are fully processed
BEFORE node 16 is even reached (13/14/15's own rasterize calls run before the chain's far-child
recursion into 16), so node 16's verdict cannot gate them either way — the "same local region of the
traversal" adjacency round four flagged was not a causal link.

**Found the real governing ancestor instead: node 128 (`iRenderBound`=60, `FBox`
min=(-3072,420,0) max=(-3068,512,132)) — the true common ancestor of all three divergent surfaces**
(its far child chain leads to nodes 9/10/11/13-chain/20/22/24 exactly, confirmed the same way: node
128's own `iFront=-1, iBack=129`, `is_front=false` for Light5, so `far_child=129`, which is the very
next node visited). Native box-tests it (index 128, in the `%16==0` residue) and gets
`visible=true` for the `-X` face.

**Live-captured the real editor's `BoundVisible` for both boxes**, harness
`harness/box_verdict_n153.py` (same call site/verdict addresses as
`spikes/2026-09-06-boundvisible-port`), full trace `logs/box-verdict-n153.log`:

- Node 128's box (`min=(-3072,420,0) max=(-3068,512,132)`), Light5, `ZAXIS=(-1,0,0)` (the `-X`
  face): **`ret=1`, path=accept — UED22 ALSO accepts it.** Matches native exactly.
- Node 16's box (`min=(-3120,176,-16) max=(-3092,560,0)`), same light: UED22 tests this exact
  geometry only ONCE across all six faces, on `ZAXIS=(0,-0,-1)` (the `-Z` face, not `-X`) — the
  editor's own real node numbering never subjects it to the box test on the `-X` face at all — and
  where it IS tested, **`ret=1`, path=zone — also accepted**, not rejected. So even taken literally,
  UED22 never rejects this box; round four's native-only "visible=false" is a pure amortization-index
  artifact (node 16 lands on native's `%16` residue on the `-X` pass; the same geometric node, at
  whatever index UED22's own permutation gives it, does not).
- The `-X` face's box-test COUNT also matches except for this one artifact: UED22 runs exactly 2 box
  tests on that face (root `+` node-128-equivalent, both accept); native runs 3 (same 2, plus node
  16 — an extra, harmless test from the index/permutation mismatch, not a missing or wrong one).

**Conclusion: box occlusion is fully cleared as this divergence's cause**, at every node checked
(round four's candidate, its literal geometry on the face where UED22 does test it, and the actual
governing ancestor identified this round) — not just re-asserting the round-three finding, but
closing the one candidate mechanism that survived round three's own live capture. The real cause is
still in `GetVisibleSurfs` somewhere else — with box occlusion, zone crossing (round four), cross-
light box-test ordering (round four), the world-space/screen-space clip-formula bug class (round
four), and per-lumel raytrace divergence (round three) all now ruled out by direct measurement, the
remaining unexplored territory is the RASTERIZATION/span-buffer-accumulation layer itself: node
DRAW ORDER (near-to-far, front-to-back) determines how much of each zone's span buffer is already
claimed by the time a later node's own surface is tested, and node order across native/UED22 is only
a PERMUTATION match at N=153 (not identity) — a reordering of two overlapping or coplanar occluders
ahead of the treads in the `-X` face's traversal could change how much of the light's screen area is
still unclaimed by the time surf 95/97/67 rasterize, without touching box occlusion, zones, or
per-lumel raytracing at all. Not attempted this round — it needs a NEW live capture (rasterize/span-
subtract call sites, not `BoundVisible`) with node identities matched by geometry, the same
discipline this round used for the box test. No mask added; `visible_surfs.rs`/`light.rs` unchanged.

Harness: `harness/box_verdict_n153.py`; log: `logs/box-verdict-n153.log`.

## Sixth round (2026-09-13) — live-captured `OccludeBsp`'s own raster-commit verdict for Light5; the "self-occlusion order race" theory is FALSIFIED as stated. Not fixed.

Round 5 left one untested lead: node-visit ORDER inside one cube face determines how much span-buffer
area is still unclaimed when a target node's own rasterize attempt runs, so a target that is a strict
subset of an earlier occluder's screen footprint could "lose the race" in one build and "win" in the
other. This round built a live capture that measures this DIRECTLY (not by inference) and found the
theory, in its simple form, does not hold: UED22's own `OccludeBsp` **does accept real, non-trivial
screen area for surf 95/97/67 multiple times** during Light5's gather, yet the surfaces still end up
excluded from Light5's final per-surf run. Something AFTER the raster-commit accept/reject decision
also has to say no, and that something is not yet found.

**Harness**: extended `harness/disasm_probe.py`'s ranges into `OccludeBsp`'s raster-commit tail
(`raster_commit` RVA `0x10019a40`, `portal_emit_retire` RVA `0x1001a1e0`) and added
`harness/raster_order_probe.py`. It breaks at `test %edi,%edi` (RVA `0x10019c1c`), the instruction
immediately after `%edi` is overwritten by the return value of `FSpanBuffer::CopyFromRaster`
(no-subtract, `0x1001dd10`) or `CopyFromRasterUpdate` (subtract, `0x1001df70`) — the exact call sites
`2026-09-06-raster-clipbspsurf-port/spike.md` already documented. Zero means nothing was left
unclaimed (the node gets `NF_PolyOccluded` and the loop moves on without ever reaching zone-crossing/
emission, confirmed by the immediately-following `orb $0x8,0x37(%edi); jmp 0x1001a7eb`); non-zero
means real area was accepted and the node proceeds toward the zone-crossing/emission code. At the
breakpoint the node pointer is still readable from a stable stack slot the function's own code uses
the same way (`$ebp-0x8bc`, confirmed against the moving-brush filter's own `push 0x1c(%edi)` argument
to `SurfIsDynamic`), giving `iSurf` at `+0x1c`; the `FSceneNode* Frame` argument is at `$ebp-0x8b4`
throughout, the same struct `box_verdict_n153.py` already reads ORIGIN (`+0x34/+0x38/+0x3c`) and the
face Z-axis (`+0x4c/+0x50/+0x54`) from.

This breakpoint sits inside `OccludeBsp` itself — the same function `box_verdict_n153.py`/
`mover_occlusion_probe.py` already broke in for a FULL `LIGHT APPLY` run without crashing the
container. It is NOT the raw per-pixel scanline setup (`0x1001b470`) that crashed
`2026-09-06-raster-clipbspsurf-port/harness/raster_probe.py` four times — that address is shared with
real-time viewport rendering (hence hit continuously even at editor idle); `OccludeBsp`'s own
raster-commit code is gather-exclusive. The probe ran clean: 1202 hits across the whole N=153
`LIGHT APPLY`, no crash, no `--hits` cap needed.

**Surf identity, confirmed by geometry, not assumed**: rather than trust that "editor surf 97" is the
same surface as "native surf 97" (this level's `nodes`/`surfs` are only a PERMUTATION match), cross-
checked by node PLANE + vertex-ring bbox (`model_dump.py`'s `nodes`/`verts`/`points`, not `pBase` —
`pBase` for these particular surfaces is a distant on-plane point near world origin, e.g. native surf
97's `pBase` is `(0,0,0)`, a legitimate but non-corner reference point, which makes `pBase`-only
matching unreliable here). Both native and the REF build number these specific nodes/surfaces
IDENTICALLY (native node 9/13/14/15/20/22/24 = surf 95/97/67; REF node 9/13/14/15/20/22/24 = the same
surf numbers, verified by matching plane `(∓0,∓0,±1,{-16,0,-32})` and vertex-ring bbox against
native's own). So reading `isurf` directly off the live capture is valid here, coincidentally.

**Filtering the capture for Light5** (`origin=-2944.19849,384.973572,129.119934`, exact match to
Light5's `Location`) and looking at every face that visits surf 95/97/67:

    zaxis=-1,0,0            : surf 67 -> edi=0, edi=0                        (2 rejects)
    zaxis=0,-0,-1           : surf 97 -> edi=1,0,0,1,1,1  (4 accepts, 2 rejects)
                              surf 95 -> edi=1                               (1 accept)
                              surf 67 -> edi=0,0,1         (2 rejects, 1 accept)

Full log: `logs/raster-order-n153.log`. **Surf 97 in particular gets a real accepted raster area on 4
of its 6 raster-commit attempts** (its coplanar-chain fragments each get tested once per face they're
visible on) — this is not a near-miss or a single ULP-scale sliver, it is the SAME qualitative pattern
native's own trace shows (native's nodes 13/14/15 for surf 97 get accepted_px 69/15575/47 — mostly
real area, not zero). **Yet the ground truth is that Light5 does NOT appear in surf 97's (or 95's or
67's) final `iLightActors` run.** An OccludeBsp-level "accept" therefore does not by itself decide
membership in the light's final per-surf set — something downstream of the raster-commit accept/
reject branch this round instrumented (in the zone-crossing/portal-merge/emission block starting
around RVA `0x1001a1e0`, only partially disassembled this round — `PF_Invisible`'s own gate is
confirmed at `0x1001a30d` matching the previously-documented address, but the code between raster-
commit and there was not fully traced to a register-precise level) must also reject these particular
surfaces for this particular light, on every accepting face, without rejecting them on every face
(rejects and accepts are mixed even for the SAME surf/light pair).

**What this rules out**: the "first occluder to rasterize a screen region wins the pixels" self-
occlusion race, AS THE SOLE MECHANISM, cannot be the whole story — if it were, an accepted raster
region should mean the surface is visible and gets emitted; instead UED22 accepts area for these
surfaces repeatedly and still excludes them. Node visit ORDER inside `OccludeBsp` may still matter
(it changes WHICH accept/reject pattern results, and a different pattern could tip whether it happens
to end up empty), but it cannot be reasoned about in isolation from whatever gate lives after
raster-commit — that gate is the real next target, not order by itself.

**Not fixed. No mask.** Next step for a future round: extend `raster_order_probe.py` (or a new probe)
past the `test %edi,%edi` branch, register-tracing `0x1001a1e0`-`0x1001a800` to a precision that
identifies the SPECIFIC test that turns an accepted raster-commit into a non-emission for surf
95/97/67 specifically — most promisingly, whatever computes `-0x8ec(%ebp)` (tested at `0x1001a30d`
and `0x1001a314`, gating a jump straight to the loop-continue) and whatever sets `-0x918(%ebp)`
(tested at `0x1001a436`, branching between two very different code paths at `0x1001a43e` — one of
which writes `iSurf` into what looks like an output record at `+0x4` off a pointer at `$ebp-0x8c8`,
`0x1001a473`-`0x1001a476` — this LOOKS like the real "commit to output" step, but was not confirmed
live this round). A live capture reading BOTH of those slots, keyed by iSurf, alongside the existing
`edi` accept/reject read, is the natural next probe.

Harness: `harness/disasm_probe.py` (extended ranges), `harness/raster_order_probe.py` (new);
logs: `logs/raster-order-n153.log`.

## Seventh round (2026-09-14) — both round-6-flagged slots characterized and RULED OUT; a stronger, unresolved `AddUniqueItem` signal found instead. Not fixed.

Executed round 6's own recommended next step: extended `disasm_probe.py` (new
`raster_commit_to_portal_emit` range, RVA `0x10019a40`-`0x1001a8e0`) and found the two previously
disassembled ranges (`raster_commit` and `portal_emit_retire`) are CONTIGUOUS but the committed log
never covered the 928 bytes between them (RVA `0x10019e40`-`0x1001a1e0`) — `disassemble start,
start+len`'s own boundary cut the transcript exactly at a function-internal point, and round 6's
two-call capture never noticed the gap. Re-ran with one combined range spanning both plus the gap
(`dev/docs/spikes/2026-09-13-nycbar-n153-mover-occlusion/logs/disasm.log` still has the old two-range
form; the new full capture is reproducible via the harness, not separately committed — see below).

**Static finding: both flagged slots are now fully characterized, and neither is a plausible
candidate for the exclusion gate.**

- **`-0x8ec(%ebp)`** is computed (RVA ~`0x1001a1fa`: `mov %ecx,%eax; not %eax; and $1,%eax; mov
  %eax,-0x8ec(%ebp)`, i.e. `NOT(PolyFlags & PF_Invisible)`) ONLY on the branch reached when the
  current surf's `PolyFlags` has `PF_Portal` (`0x4000000`) set (`test $0x4000000,%ecx; je
  0x1001a324`). For a NON-portal surf — every ordinary opaque world surf, tread surfaces 95/97/67
  included — that `je` is taken and jumps straight PAST both the write at `0x1001a1fa` and the two
  reads at `0x1001a2be`/`0x1001a30d`, landing directly at `0x1001a324` (a DIFFERENT, direct
  `PF_Invisible` test off `PolyFlags`' own low byte, `cl`). So `-0x8ec(%ebp)` never enters the control
  flow at all for any surf this item cares about — it only gates PORTAL surfaces, a different code
  path entirely.
- **`-0x918(%ebp)`** is a per-face DEDUP check, not a visibility decision. Near the top of this whole
  block (RVA ~`0x100199e9`, unconditional for every node), it walks a linked list at `table[iSurf]`
  (`-0x948(%ebp)`, a per-surf head-pointer array local to this render pass) comparing each entry's
  `+0x34` field against a key from a repeated call through `Frame->Level`'s own accessor (the SAME
  call site, `*0x15e438c`, used 4 times in this function — almost certainly `Level->GetLevelInfo()`,
  a per-level constant, not a per-light one). The result — the matching entry if found, else 0 — is
  left in `-0x918(%ebp)`. For a non-portal surf that passes the `PF_Invisible` test at `0x1001a324`,
  `-0x918(%ebp)` reaches the later `test %edi,%edi` at RVA `0x1001a436` UNCHANGED from this early
  lookup (the `xor %eax,%eax; mov %eax,-0x918(%ebp)` reset at `0x1001a31a` only runs on the portal
  path). Zero falls through to `0x1001a43e`, which ALLOCATES A NEW RECORD, fills it (`iSurf` at
  `+0x4`, `PolyFlags` at `+0x10`, the `Level` key at `+0x34`, a `Frame->0x98[idx]` value — plausibly
  the current light actor — at `+0x38`), and PREPENDS it onto `table[iSurf]` (`mov %edi,(%ecx,%eax,4)`
  — confirmed a genuine linked-list insert, `edi->0x3c` = old head). Nonzero (a match already exists
  for this surf) diverts to RVA `0x1001a621`, a different code path (does NOT create a new record).
  So `-0x918(%ebp)` is exactly what its name suggests once its provenance is traced: "does surf iSurf
  already have an entry in this pass's bookkeeping table" — a dedup preventing the SAME surf's
  multiple coplanar-chain BSP-node fragments (e.g. NYC_Bar's nodes 13/14/15, all `iSurf=97`) from each
  creating a duplicate record. It is NOT a "should this light illuminate this surf" test.

**Live capture (harness: new `harness/gate_probe_round7.py`, breaking at RVA `0x1001a436` itself,
reading `iSurf`, the tested `-0x918(%ebp)` value, `-0x8ec(%ebp)`'s value, and the light Frame's
origin/z-axis; log: `logs/gate-round7-n153.log`, 867 hits, clean run, no crash) DIRECTLY REFUTES both
slots as the exclusion mechanism.** Filtered to Light5's exact origin and `iSurf ∈ {95,97,67}`:

    G hit=837 isurf=97 s918=0         zaxis=0,-0,-1   <- NEW record created (not diverted)
    G hit=840 isurf=97 s918=288443232 zaxis=0,-0,-1   <- diverted (dedup: node 14, same iSurf as 837)
    G hit=841 isurf=97 s918=288443232 zaxis=0,-0,-1   <- diverted (dedup: node 15, same iSurf)
    G hit=842 isurf=97 s918=288443232 zaxis=0,-0,-1   <- diverted (dedup: a 4th surf-97 node)
    G hit=844 isurf=95 s918=0         zaxis=0,-0,-1   <- NEW record created
    G hit=845 isurf=67 s918=0         zaxis=0,-0,-1   <- NEW record created

This is a CLEAN cross-check against round 6's own independent `raster_order_probe.py` measurement on
the SAME face (`zaxis=0,-0,-1: surf 97 -> edi=1,0,0,1,1,1` [4 accepts], `surf 95 -> edi=1` [1 accept],
`surf 67 -> edi=0,0,1` [1 accept]) — 4+1+1=6 raster-accepted nodes, exactly the 6 hits captured here,
confirming this breakpoint fires on precisely the set round 6 already measured. **All three surfaces —
95, 97, AND 67 — get an actual "commit" record created in `table[iSurf]` for Light5** (`s918=0` on
their first/only node), the exact opposite of what an exclusion mechanism should show. No OTHER light
in the whole N=153 capture ever reaches this breakpoint for these 3 surfaces (only Light5's geometry
reaches this corner), so no comparison case exists in this dataset, but the internal consistency with
round 6's independently-measured raster-accept counts leaves no ambiguity: **this gate commits the
records, it does not reject them.** Round 6's two flagged leads are both closed off.

**New finding, from re-reading the EXISTING committed `mover-occlusion.log` (no new capture) with
sharper node-identity cross-referencing: round 6's own dismissal of the `AddUniqueItem` signal as a
"false positive" may itself be wrong.** Round 6's log format is `NODE seq=<n> isurf=<s>
origin=[...]` and `ADD seq=<n> isurf=<s>` (no origin on `ADD` — it's a shared `TArray<INT>
::AddUniqueItem` entry point called from many unrelated places, hence round 6's "sequence-number
proximity is unreliable" caveat). Restricting to Light5's own `NODE` sequence window (seq 7460-8402,
found by filtering `NODE` on Light5's exact origin) finds:

    NODE seq=8239 isurf=67   origin=[Light5's exact location]
    NODE seq=8240 isurf=67   origin=[Light5's exact location]
    NODE seq=8244 isurf=67   origin=[Light5's exact location]
    NODE seq=8214 isurf=95   origin=[Light5's exact location]
    ADD  seq=8245 isurf=67
    ADD  seq=8246 isurf=95
    ADD  seq=8248 isurf=97

All THREE divergent surfaces (67, 95, 97) have an `ADD` entry landing within single-digit sequence
numbers of their own `NODE` entries, inside Light5's own window — a materially stronger signal than
round 6's original "weak positive" (which it dismissed as likely spurious given the shared call site).
This is NOT yet confirmed (still sequence-proximity inference, not a direct origin read at the `ADD`
site itself — the callee-entry breakpoint at `0x100120b0` fires before the callee's own `push %ebp`,
so it inherits the CALLER's frame, not `OccludeBsp`'s, and reading a light origin from it needs first
identifying which caller-frame slot holds it), but it directly contradicts round 6's stated reason for
dismissing this same signal, and is worth resolving before ruling it out again.

**Conclusion: the exclusion mechanism is still not found.** Both of round 6's flagged candidates are
now definitively closed by live measurement (not just re-asserted). The likely remaining possibilities,
in order of how directly they're now motivated: (a) `table[iSurf]`'s records — proven to exist for all
3 surfaces here — are CONSUMED or PRUNED by a later step neither this round's nor round 6's
disassembly window reached (RVA past `0x1001a8e0`, or a separate pass reading `-0x948(%ebp)` this
round's ~2400-byte window never revisits); (b) `table[iSurf]` is unrelated bookkeeping (a rendering
cache, not what feeds `iSurfs`), and the real answer lives in tracing what `AddUniqueItem`'s TArray
actually is and where its final content gets filtered before `illuminateSurf` reads it — the
`ADD`-entry re-finding above is the concrete, actionable lead for this. **Not fixed. No mask.** Next
step for a future round: a live capture of `AddUniqueItem`'s call site (RVA `0x100120a0`, already in
`disasm_probe.py`'s `adduniqueitem_call` range) that reads the CALLER's own light-origin slot (needs a
short static disassembly of the caller function first, to find where it stashes `Frame`/light identity
across the call) so the `ADD seq=8245..8248 isurf=67/95/97` correlation above can be confirmed or
refuted directly instead of by sequence proximity — settling this settles whether `AddUniqueItem`'s
target array is `iSurfs` itself or an unrelated list.

Harness: `harness/disasm_probe.py` (new `raster_commit_to_portal_emit` combined range),
`harness/gate_probe_round7.py` (new); log: `logs/gate-round7-n153.log`. No live capture of the new
`AddUniqueItem`-origin lead was attempted this round (it needs a preliminary disassembly pass of the
caller function first, scoped as the next step above); the `ADD`/`NODE` cross-reference above reuses
the EXISTING `mover-occlusion.log` from round 3, no new capture.

## Eighth round (2026-09-15) — the AddUniqueItem lead is CONFIRMED TRUE by direct read; GetVisibleSurfs/OccludeBsp are now fully cleared. Not fixed.

Executed round 7's own recommended next step: a static disassembly pass on the `AddUniqueItem` CALLER
(to find where it stashes `Frame`/light identity across the call), then a live capture reading that
slot directly — settling whether the `ADD seq=8245..8248 isurf=67/95/97` correlation is real or, as
round 6 argued, a sequence-proximity false positive from a shared template call site.

**Static: the caller is `URender::GetVisibleSurfs` itself, not an unrelated call site.** A wider live
disassembly of `GetVisibleSurfs`'s body (`render.dll 0x100187b0`-`0x100189b0`, harness
`disasm_wide_probe.py`, log `logs/disasm-wide.log`) finds a DIRECT `call 0x100120b0` at RVA
`0x100189da`, inside a per-face post-`OccludeBsp` walk that matches
`port-urender-getvisiblesurfs-so-each-light-gets/overview.md`'s own documented pseudocode exactly:

    for( i=0; i<6; i++ ) {
      ...
      OccludeBsp(Frame);
      for( j=0; j<3; j++ )
        for( D = Frame->Draw[j]; D; D = D->Next )
          iSurfs.AddUniqueItem(D->iSurf);          // RVA 0x100189da
      ...
    }

`GetVisibleSurfs`'s own prologue (live `0x015c87ef`: `mov 0xc(%ebp),%ebx`) shows **`0x8(%ebp)` = arg1 =
the `FSceneNode* Frame`, and `0xc(%ebp)` = arg2 = `%ebx`, held in that register for the WHOLE function
body — the output `TArray<INT>* iSurfs`.** Both are stable across the entire per-face loop, so both are
readable AT `AddUniqueItem`'s own callee-entry breakpoint (`0x100120b0`) after all: that breakpoint
sits exactly at `push %ebp` (confirmed by disassembling `AddUniqueItem`'s own body,
`adduniqueitem_body` range) — `$ebp` there is STILL `GetVisibleSurfs`'s frame, since `GetVisibleSurfs`
never moves `%ebp` around the call. No new call-site breakpoint was needed; `mover_occlusion_probe.py`'s
existing `ADD_ENTRY` address just needed two more reads.

**Live capture (harness: new `adduniqueitem_origin_probe.py`, reusing `ADD_ENTRY` at `0x100120b0` and
adding `$ebp+0x8`/`$ebp+0xc` reads; log `logs/adduniqueitem-origin-n153-v2.log`, 457 hits, clean run):**
filtered to `isurf ∈ {67,95,97}` —

    ADD hit=439 isurf=67 iSurfsArr=0x1136f770 origin=-2944.19849,384.973572,129.119934
    ADD hit=440 isurf=95 iSurfsArr=0x1136f770 origin=-2944.19849,384.973572,129.119934
    ADD hit=442 isurf=97 iSurfsArr=0x1136f770 origin=-2944.19849,384.973572,129.119934

`origin` is `Light5`'s exact `Location` (`-2944.198486,384.973572,129.119934`), read directly off the
call's own `Frame` argument — not inferred from sequence proximity. All three surfaces hit exactly
once, sharing the SAME `iSurfsArr` pointer (i.e. the same single `GetVisibleSurfs` call, Light5's own).
(A first attempt at this same capture mis-read `Frame`'s Origin at `+0x34/+0x38/+0x3c` — the convention
`OccludeBsp`'s own local `Frame` copy uses — and got `0,0,0`: `GetVisibleSurfs`'s arg1 is one level
further out, a wrapping struct whose `+0x30` field is a POINTER to the `Coords`-like struct that
actually carries Origin at `+0xd0/+0xd4/+0xd8`. Fixed and re-run; see the harness docstring.)

**This confirms round 7's `AddUniqueItem` lead TRUE, and DISPROVES round 6's dismissal of the earlier
`ADD`/`NODE` correlation as a sequence-proximity artifact — Light5's own `GetVisibleSurfs` call
genuinely, unambiguously adds surf 67, 95, AND 97 to its own `iSurfs` output array.** Cross-referenced
against `port-urender-getvisiblesurfs-so-each-light-gets/overview.md`'s own architecture doc: `iSurfs`
is exactly the array `GetVisibleSurfs` exists to compute and return to its caller (`Editor 0x100a4ba0`,
"per light... calls `URender::GetVisibleSurfs`"), sourced from `Frame->Draw[]` — the SAME per-face
emission list `OccludeBsp`'s own accept path (round 6/7's raster-commit code) populates. Round 7's
`table[iSurf]` dedup table (which created a "NEW record" for all 3 surfaces, not a diversion) and this
round's `iSurfs`/`Frame->Draw[]` are consistent, complementary evidence of the SAME fact from two
different angles, not competing theories.

**This DISPROVES this item's own "Conclusion" section above (2026-09-13): `GetVisibleSurfs`'s cube-map
render is NOT excluding these 3 surfaces from Light5's visible set — it includes them, confirmed by
direct read of the returned array's own content, not inference.** Combined with round 6's independent,
already-complete disassembly of the DOWNSTREAM commit loop (`Editor.dll 0x100a4ba0`-`0x100a5010`, the
routine that consumes `GetVisibleSurfs`'s returned `iSurfs` per surf per light) finding only two gates
there (a light-flag class test and the already-ruled-out radius cull, both of which surf 67/95/97 pass
for Light5) — **`GetVisibleSurfs`, `OccludeBsp`, AND the immediate post-return commit loop are now ALL
cleared by direct measurement.** The exclusion must happen in what that commit loop's "commit" step
actually WRITES TO (not yet examined — round 6 characterized its GATES, not its write target) or in a
separate, later step that reads that write target before `illuminateSurf`'s own per-surface candidate-
light list is built.

**Not fixed. No mask.** Next step for a future round: statically re-examine `Editor.dll`
`0x100a4ba0`-`0x100a5010`'s WRITE side (what a surf that passes both known gates is committed INTO —
not yet traced), then live-capture that exact write for Light5/surf 67/95/97 to see whether it happens
normally and something LATER drops it, or whether the write itself is silently skipped by a mechanism
round 6's gate-only pass didn't register as a "gate" (e.g. a duplicate-suppression keyed on something
per-surface, or a separate per-surface running list `illuminateSurf` reads that this commit loop only
sometimes populates). This is the same "keep tracing the write path" method that closed round 7's two
false leads and this round's real one — direct reads of arguments/writes, not renewed static inference.

Harness: `dev/docs/spikes/2026-09-15-nycbar-n153-adduniqueitem-origin/harness/disasm_wide_probe.py`
(new, static), `adduniqueitem_origin_probe.py` (new, live); logs in the same spike's `logs/`
(`disasm-wide.log`, `adduniqueitem-origin-n153-v2.log`; an earlier `adduniqueitem-origin-n153.log` is
the first, mis-offset attempt, kept for the record).

## Ninth round (2026-09-15) -- the WRITE side is traced and confirmed to work; round 3's "raytrace
## never fires" finding is DIRECTLY REFUTED. Not fixed, no mask; identity confirmation is the next step.

Executed round 8's own recommended next step: statically traced `Editor.dll 0x100a4ba0`-`0x100a5010`'s
WRITE side (what a surf that passes both known gates gets committed INTO), then live-captured that
exact write plus the read side and, going further than round 8 asked, the entire per-light raytrace
loop past it -- since chasing the write led straight into new territory none of rounds 1-8 had reached.

**Static (plain `objdump -d -M intel` against `Editor.dll` extracted from `dx-lum-uned-dbg:latest` --
no docker/gdb needed for this half; the DLL's own `ImageBase` is `0x10000000` and it does not relocate
under Wine, so RVA == live VA, same as `gather_disasm_probe.py`'s existing note).**

- The commit call at RVA `0x100a4f10` (`call 0x100123e0`) is a generic `TArray<AActor*>::AddItem`
  (confirmed by disassembling `0x100123e0` itself: pushes element-size 4/count 1, grows the array via
  `[0x100ce5ec]`, writes `*arg` into `Data[OldCount]`). Its `ecx` ("this") is computed as
  `*(GatherCtx+0x1c) + iSurf*12` -- a per-surf `TArray<AActor*>` array living at `GatherCtx+0x1c`, one
  12-byte TArray slot per surf. Call this `CandidateLights[iSurf]`.
- `illuminateSurf` (RVA `0x100a5010`, the function immediately following the gather loop) reads the
  SAME array through the SAME offset off its OWN `this`: `eax = *(this+0x1c); cmp [eax+iSurf*12+0x4],0`
  (RVA `0x100a557f`) -- `CandidateLights[iSurf].ArrayNum`. If zero, execution jumps straight to the
  function's own epilogue (`0x100a5b33`), skipping the whole per-light raytrace loop for that surf.

**Live (gdb, `dev/docs/spikes/2026-09-15-nycbar-n153-commit-write-readback/harness/
commit_write_readback_probe.py`): the write and the read are the SAME object, and the write lands.**
Three breakpoints -- the commit call, its return, and `illuminateSurf`'s read gate -- on a fresh N=153
golden build. For Light5 x world surf 67/95/97: `GatherCtx`/`CandidateLights` base is IDENTICAL
(`0x146c6c8`/`0x113c377c`) at both the write and the read; the write shows `before=0, after=1` for all
three (the slot really is empty before Light5, and holds exactly one entry after); the read shows
`count=1` for all three (`illuminateSurf` does NOT take the empty-skip branch). **This closes round 8's
own open question decisively: the commit is not silently dropped, misdirected, or read from a stale/
reset copy -- it is the same array, the write succeeds, and the read sees it.** So `illuminateSurf`'s
per-light raytrace loop genuinely STARTS running for Light5 on all three surfaces.

**Following the loop further (harness: `perlumel_radius_probe.py`, same spike dir) found a SECOND,
finer-grained radius cull inside the per-lumel loop** (RVA `0x100a5971`, `comiss xmm1,xmm0` --
`xmm1`=`WorldLightRadius^2` cached once per light, `xmm0`=squared distance from THIS LUMEL's own
projected world position to the light) -- different from the already-ruled-out SURF-PLANE distance
cull (round 6/8; that one is coarse, once per surf, and passes for these surfaces at 145-161uu). This
is per-lumel and genuinely geometric: it is NOT the exclusion mechanism by itself (see below), but it
was new, unexplored territory this round had to clear to keep tracing.

**THE MAJOR FINDING: round 3's `illuminate_ray_probe.py` conclusion ("shadow-ray call site never
fires even once" for Light5/surf 67/95/97) is DIRECTLY REFUTED by a fresh live capture on the exact
same golden-build recipe.** Breaking at RVA `0x100a5a04` (`call [eax+0x58]`, the identical address
round 3/4 already documented as the shadow-ray call site) and its return (`0x100a5a07`, eax = result),
filtered to Light5 by Location and to lumels in the tread's X range (<= -3080): the call fires
REPEATEDLY (229 hits in one run), and its result is genuinely MIXED -- `eax=0` (blocked) for 178
lumels, `eax=1` (visible/unblocked) for 51, in a pattern that lines up with real partial occlusion by
the closed door (e.g. at one fixed Y, the four lumels farthest from the doorway return `eax=1` while
the five nearest the door return `eax=0` -- consistent with the door's own Y-extent not spanning the
full opening, so some sightlines from Light5 pass the doorway plane outside the door mesh and some
don't). `eax=1` also fires for lumels sitting ON the closed door's own face (Z near 0-4, X near -3088,
Y inside the door's Y-range) -- matching round 6's "UED22 lights the door's own face" half of the
mirror-image finding. **`illuminate_ray_probe.py`'s zero-hit result was almost certainly the same class
of bug this round's OWN first attempt hit: an `iSurf` identity read that evaluates to garbage (this
round's naive `(SurfPtr - SurfsBase)/64` at this point in the function produced `1015325`, not a real
surf index) silently making a `iSurf ∈ {67,95,97}`-conditioned breakpoint never fire, mistaken for "the
call never fires."** The static "no LineCheck ever called" claims in the fourth/fifth-round static
re-derivations were built on trusting that same zero-hit result, not independently re-derived.

**A further commit step exists past the per-lumel loop, not yet identity-confirmed.** Static disasm of
the loop's exit path (RVA `0x100a5aa2`-`0x100a5ac2`): a per-light flag `[ebp-0x6c]`, reset to 0 before
each light's lumel loop and set to 1 the FIRST time a lumel's raytrace returns nonzero (`0x100a5a0c`:
`test eax,eax; je <skip>` guards the flag-set), gates a SECOND `TArray::AddItem` call
(`0x100a5ac2`, same generic `0x100123e0` entry point) into a DIFFERENT array
(`*(SomeWrapper+0xe4)`, off the SAME base `illuminateSurf`'s prologue also uses for the Vectors/Points
pools) -- skipped entirely (jump to `0x100a5ae9`) if NO lumel was ever visible for this light. Given
this round's own capture shows Light5 DOES get at least one visible (`eax=1`) lumel on the sampled
surface, the flag should be 1 and this commit SHOULD fire -- but whether the sampled lumels (Z ≈
-28/-12/4, matching the documented tread heights 0/-16/-32 to within one lumel-grid offset) are
REALLY surf 67/95/97, or an adjacent, non-divergent tread that correctly receives Light5, is NOT
confirmed: this round's `iSurf` derivation is independently proven broken at this point in the
function (see above), so surf identity here is geometric inference only, not the register/address
cross-reference discipline round 6 established as the bar ("surf identity, confirmed by geometry, not
assumed").

**Not fixed. No mask.** Next step for round 10: identity-confirm which surf the captured lumels
belong to, then re-run the `[ebp-0x6c]`/`0x100a5ac2` commit-step capture filtered to that confirmed
surf + Light5. Two ways to get identity right (round 6's own two prior methods): (a) read
`[ebp-0x24]` (the `&Model.LightMap[iLightMap]` pointer this round already found, static section
above) and cross-reference its exact address against a companion read of `Model.LightMap[4]`/`[8]`/
`[12]`'s real addresses (the divergent records' known indices, from `model_dump.py`); or (b) match
node PLANE + vertex-ring bbox against `model_dump.py`'s decode, the same discipline round 6 used to
confirm native/REF surf-number identity for these exact three surfaces. If the lumels this round
sampled turn out to genuinely be surf 67/95/97, the open question becomes why UED22's real saved
`iLightActors` is `-1` (no light at all) despite a live capture showing the commit-step's own gate
(`[ebp-0x6c]`) should be 1 -- meaning either this round's flag-semantics read is subtly wrong, or a
STILL LATER step (after `0x100a5ac2`, not yet traced) discards the commit. If the lumels turn out to
belong to a different, non-divergent surf, the search moves to finding the REAL surf 67/95/97's own
per-lumel raytrace pattern directly (same probe, correct filter) -- which this round's tooling can now
do in one more live run once identity is pinned.

Harness: `dev/docs/spikes/2026-09-15-nycbar-n153-commit-write-readback/harness/
commit_write_readback_probe.py` (write/read confirmation), `perlumel_radius_probe.py` (radius cull +
raytrace-call + raytrace-return capture, evolved across several fixes this round -- see its own
docstring for the `iSurf`-derivation dead end); logs in the same spike's `logs/`
(`commit-write-readback-n153.log`, `perlumel-radius-n153.log`).
