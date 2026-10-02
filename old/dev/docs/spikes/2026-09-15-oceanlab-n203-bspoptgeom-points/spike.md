# OceanLab N=203: `bspOptGeom`'s `Model*`/`UModel` layout RE'd; the open question is ANSWERED — UED22 keeps the wall face alive; native's `FilterWorldThroughBrush` kills it one brush early

Continues `dev/docs/board/to-spike/oceanlab-n-203-world-model2-split-vertex-ulp/` and
`dev/docs/spikes/2026-09-14-oceanlab-n203-addpoint-capture/`. That session pinned the mechanism to a
dead-node "ghost" point on native's side and left one question open: is the wall's original face
(native node 5154) ALSO dead in UED22's real tree at the equivalent moment, or does UED22 keep it (or
an equivalent live face) alive through to its own `bspOptGeom`? This required locating `bspOptGeom`'s
`Model*` argument and enough of `UModel`'s in-memory layout to read `Points`/`Nodes`/`Surfs` directly
from a live gdb capture — new RE work, not attempted before this session.

**Answer: UED22 keeps it alive.** Confirmed twice, independently, from the real editor's own memory:
the wall's original surf survives as a live, separate `Surfs` entry through `bspOptGeom` alongside
`Brush483`'s own new point — not merged, not orphaned, not garbage-collected. Native's own points-GC
(`bsp_refresh_points_vectors`) is innocent; the true divergence is one step further upstream, in
`FilterWorldThroughBrush`'s classification of this exact face against `Brush482`'s CSG_Add. Not fixed
this session (the exact classification difference needs one more live capture); precisely scoped for
the next session.

## 1. RE: `bspOptGeom`'s `Model*` and `UModel`'s in-memory `TArray` layout

Not derived from scratch — an earlier spike session's own oracle harness
(`dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle/bspopt_pool_oracle.py`,
`repart_stage_oracle.py`) had already RE'd this and left it committed, uncredited in this campaign's
own status docs. Cross-verified against `uedcli-native/src/zones.rs`'s own disassembly comment
(`eax = iNode<<6 + [Model+0x58]`, etc.) — three independent sources agree:

| Field | Editor.dll `Model*` offset | Notes |
|---|---|---|
| `Nodes` | Data `+0x58`, Num `+0x5c` | stride `0x40` (`FBspNode`, confirmed layout below) |
| `Vectors` | Data `+0x78`, Num `+0x7c` | stride `12` (`FVector`) |
| `Points` | Data `+0x88`, Num `+0x8c` | stride `12` (`FVector`) |
| `Surfs` | Data `+0x98`, Num `+0x9c` | stride `0x40` (`FBspSurf`); `pBase`@`+0x08`, `vNormal`@`+0x0c` within it |
| `Verts` | Num `+0x6c` | (Data offset not needed this session) |

`bspOptGeom` itself: Editor.dll (preferred base `0x10000000`) entry `0x10036870` — first instruction
(`push ebp`, prologue not yet run), so the sole argument (`Model*`) sits at `[esp+4]`.

`FBspNode`'s exact in-memory layout was already hand-decoded in
`dev/docs/spikes/2026-07-15-native-materialize/sections/50-model-ondisk-layout-and-render.md`
(`Plane`@0x00, `ZoneMask`@0x10, `iVertPool`@0x18, `iSurf`@0x1c, `iChild[0]`@0x20, `iChild[1]`@0x24,
`iPlane`@0x28, `iCollisionBound`@0x2c, `iRenderBound`@0x30, `iZone[0/1]`@0x34/0x35, `NumVertices`@0x36,
`NodeFlags`@0x37, `iLeaf[0/1]`@0x38/0x3c) — reused here, not re-derived.

## 2. The live capture

`harness/capture_bspoptgeom_points.py`: same gdb-attach recipe as
`2026-09-14-oceanlab-n203-addpoint-capture/harness/capture_addpoint.py` (ptrace inside the
`dx-lum-uned-dbg` container), breakpoint at `bspOptGeom` entry, drives the OceanLab N=203 subset
through `MAP IMPORT` + `MAP REBUILD` (no `LIGHT APPLY` — the divergence is CSG-only). At the single hit
(one `bspOptGeom` call; `nodes=2640` matches the world `Model2`'s known final node count exactly),
dumps the live `Points` and `Surfs` arrays whole (`dump binary memory`) via `docker exec ... cat`
(**`docker cp` is broken on this rootless daemon** — it deterministically fails with an overlay
`remount-ro .../stubs ... operation not permitted` error touching the container's read-only `/stubs`
bind mount; not transient, retrying does not help — switched the transfer to `docker exec ... cat`
piped to a local file, which never touches that machinery).

`harness/analyze.py` scans the dumped `Points` array (4189 entries) for the divergence's two target
coordinates (`x` bits `0xc3800002` = UED's surviving wall value, or `0xc3800004` = native's own added
value; `y`/`z` bits for both `Brush483` polys):

    idx=947  target=A (-256.00006103515625, 600.000244140625, -1800.0)  x-bits=0xc3800002  UED-surviving
    idx=950  target=B (-256.00006103515625, 504.000244140625, -1704.0)  x-bits=0xc3800002  UED-surviving
    idx=968  target=A (-256.0001220703125,  600.000244140625, -1800.0)  x-bits=0xc3800004  native-added
    idx=970  target=B (-256.0001220703125,  504.000244140625, -1704.0)  x-bits=0xc3800004  native-added

**Both values are present, at DIFFERENT indices** — this alone settles the headline question: UED22's
own `Points` array has NOT dropped the wall's pre-existing value by the time `bspOptGeom` runs.

A cross-check needing no node-reachability walk at all: `Surfs`' `pBase` field (offset `+0x08`,
confirmed above) is scanned across all 1085 live surfs for a match on any of `{947, 950, 968, 970}`:

    surf 1053  pBase=947  (the WALL's own surf — separate from Brush483's)
    surf 1055  pBase=950
    surf 1074  pBase=968  (Brush483's own new surf)
    surf 1076  pBase=970

Four DISTINCT, live surfs, two per point — the wall's original surf (1053/1055) is not a ghost, not an
orphan reference from a dead node: it is a fully live `Surfs` entry, structurally on par with
`Brush483`'s own brand-new surf (1074/1076). This directly refutes the "same dead-node ghost" framing
the prior session left open, in the strongest possible way: this is not a GC-timing/ordering
difference in the points-refresh passes at all (`bsp_refresh_points_vectors`/
`compact_points_to_surf_bases` are re-confirmed innocent — the point genuinely IS still surf-referenced
in UED22's real tree, not merely "kept anyway pending GC"). The real divergence is upstream: whichever
brush's own CSG step makes native's wall-node dead never makes it dead in UED22's real tree.

## 3. Pinpointing the exact CSG step, offline (no gdb needed)

Native's own committed `UEDCLI_BSPCSG_BRUSH_STATE=FULL:lo-hi` diagnostic (already wired for exactly
this: `bspcsg.rs`'s Pass-1 per-brush loop) traces every node's plane/links/`NumVertices` after each
structural brush, with no docker/editor involved
(`harness/trace_node_death.py`, offline `build_native` only):

    BRUSHSTATE k=164 bi=164 nodes=5154 surfs=1053 ...   <- node 5154 / surf 1053 FIRST created here
    BRUSHSTATE k=165 bi=165 nodes=5177 surfs=1065 ...
    P1NODE k=165 i=5154 pb=3f800000,80000000,80000000,c3800002 iF=5155 iB=-1 iP=5156 isurf=1053 nv=3 nf=0x0
    BRUSHSTATE k=166 bi=166 nodes=5197 surfs=1073 ...
    P1NODE k=166 i=5154 pb=3f800000,80000000,80000000,c3800002 iF=-1  iB=-1 iP=-1  isurf=1053 nv=0 nf=0x0
    BRUSHSTATE k=167 bi=167 nodes=5245 surfs=1085 ...   <- Brush483 itself

Node 5154's own plane (`pb`) is `(1.0, -0.0, -0.0, -256.00006103515625)` — literally the wall plane
`x = -256.00006103515625`, i.e. this node IS the wall face itself, not merely near it. It is ALIVE
(`nv=3`) through brush `bi=165`, then DEAD (`nv=0`, and its own two re-add children `5155`/`5156`
spliced away to `-1` by `bsp_cleanup`'s Case-B "no coplanar successor, no children" path — see
`bspcsg.rs`'s `cleanup_nodes`) immediately after brush `bi=166` runs.

Resolving `bi` against the trunk (`brushes[164..167]`, the brush-actor-only sub-order):

| `bi` | Actor | `CsgOper` |
|---|---|---|
| 164 | `Brush480` | `CSG_Subtract` — creates the wall face (opens it up) |
| 165 | `Brush481` | `CSG_Subtract` |
| **166** | **`Brush482`** | **`CSG_Add`** — native's `filter_world_through_brush` (`bspcsg.rs`, port of Editor.dll `FilterWorldThroughBrush` `0x33250`) decides this ADD volume genuinely consumes node 5154's face (`g_discarded != 0` -> `filter_one_world_node`'s "commit" branch, `world.nodes[ni].num_vertices = 0`) |
| 167 | `Brush483` | `CSG_Subtract` — the actor whose own `bsp_add_point` produces the divergent `0xc3800004` |

**The exact open item, precisely scoped:** does UED22's real `FilterWorldThroughBrush`, filtering this
same wall face through `Brush482`'s (CSG_Add) temp BSP, ALSO decide the face is consumed
(`GDiscarded != 0`), or does it decide the opposite (a graze, `GDiscarded == 0`, roll back and keep the
face whole) — which the live capture above now proves must be UED22's real answer, since the face
survives all the way to `bspOptGeom`. This is not a different bug class than the campaign's other
found-and-fixed "near-tie boundary classification" cases (Island N=332, WanChai N=45/58, UNATCO
N=226 — all traced to a sub-ULP `FLinePlaneIntersection`/crossing-vertex tie); it is the SAME shape of
bug (native and the editor land on opposite sides of a genuine near-tie) but in a DIFFERENT function
(`FilterWorldThroughBrush`'s own INSIDE/OUTSIDE classify, not a permeating-light beam clip), not yet
confirmed by a matching live capture of that specific function.

## What this does NOT do

- **No fix applied.** `bspcsg.rs` is unmodified. The prior session's own hypothesis (native's dead-node
  "ghost" survives only via a surf reference from a node bsp_cleanup already spliced dead) is now
  narrowed further and, in one respect, corrected: it is not merely that native discards a point pending
  GC while UED22 defers the same GC — UED22's wall surf is a genuinely LIVE, undamaged surf, structurally
  no different from any other. The actual gap is one step further upstream, in `FilterWorldThroughBrush`'s
  own consume-vs-graze verdict for this one face against `Brush482`.
- OceanLab's ceiling is unchanged: byte-exact N=1..202, still bails at N=203 on the same `model2`
  `points` divergence (re-confirmed unchanged this session, `ladder_run.py --dx 14_OceanLab_Lab.dx
  --from 202 --to 202` still PASSes; the N=203 divergence itself was not re-run, since the mechanism
  above already fully explains it and no code changed).
- No mask, no exclusion proposed, per `NATIVE-MATERIALIZE.md`'s prime directive.

## Next step for whoever picks this up

A live gdb capture of the REAL editor's `FilterWorldThroughBrush` (`Editor.dll` preferred-base
`0x33250`) — or its inner `SplitWithPlane`/classify call — during `Brush482`'s own `bspBrushCSG`,
scoped to the wall face's exact plane bits (`0x3f800000, 0x80000000, 0x80000000, 0xc3800002`), to read
the real `GDiscarded` verdict (or the per-vertex classify results feeding it) and compare against
native's own computed classification for the identical inputs. Same method class as
`2026-09-13-crossing-vertex-live-capture/`; the harness infrastructure (`capture_bspoptgeom_points.py`,
this session's `Model*`/`UModel` layout table above) is directly reusable for staging the same N=203
subset up to brush `bi=166`.

## Repro

    # live capture (Points + Surfs at bspOptGeom entry):
    .venv/bin/python3 dev/docs/spikes/2026-09-15-oceanlab-n203-bspoptgeom-points/harness/capture_bspoptgeom_points.py
    .venv/bin/python3 dev/docs/spikes/2026-09-15-oceanlab-n203-bspoptgeom-points/harness/analyze.py
    # offline node-death trace (no docker):
    .venv/bin/python3 dev/docs/spikes/2026-09-15-oceanlab-n203-bspoptgeom-points/harness/trace_node_death.py --node 5154 --lo 160 --hi 170
