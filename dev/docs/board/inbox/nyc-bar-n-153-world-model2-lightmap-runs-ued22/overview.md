+++
priority = "p2"
kind = "debug"
summary = "NYC_Bar bails at N=153: Light5 wrongly lights 3 world stair-tread surfs UED22 leaves dark, and native never lights the closed door's (DeusExMover9) own face either. Live gdb capture (2026-09-13) confirmed the door's mover-mirrored BSP surf IS a real static-tree node and DOES get moving-brush-filtered during Light5's gather -- but in a DIFFERENT cube-map face pass than the one visiting the tread surfs, so it cannot be occluding them by rasterization. illuminateSurf's per-lumel raytrace is never even invoked for the 3 tread surfs (0 hits) with any light, and the gather-commit routine (0x100a4ba0) has no occlusion test beyond the already-ruled-out plane-distance cull -- so GetVisibleSurfs itself must be excluding them, via a mechanism not yet found (likely zone/portal reachability, possibly UNRELATED to the mover). The original mover-occlusion theory does not survive this capture. Not fixed; no mask; next step below."
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
