# NYC_Bar N=151 — the permeating-light beam clip used an unnormalized plane

**Result: one root cause, fixed faithfully, no mask.** `FEditorVisibility::ActorVisibility`'s beam
clip builds `FPlane(Light, ClipPoly->Vertex[j], ClipPoly->Vertex[jPrev])`, and `FPlane(A,B,C)`
**normalizes** the cross product. Native built the same cross product but never normalized it, so
`FPoly::SplitWithPlaneFast`'s `+/-0.25` epsilon was effectively divided by the cross product's
length — order 1e4 for room-scale geometry — and stopped gating anything. The clip kept slivers the
editor rejects whole, the beam survived hops it should not have, and leaves got permeating-light
runs UED22 leaves empty. Boards: `nyc-bar-n-151-world-model2-leaf-permeating-light` (fixed),
`island-n-123-world-model2-leaf-permeating-light` (a DIFFERENT cause, see below).

## The divergence

NYC_Bar N=151: `parity_gate.py` fails on `BODY model model2`. Every geometry array is byte-identical;
`leaves[74]` is native `(iZone=2, iPermeating=63, …)` against UED22's `(2, -1, …)`, every later leaf's
`iPermeating` shifts by +2 and `Lights` is 247 vs 245. The extra run is one light plus its `0`
terminator: native decides `Light3` permeates leaf 74, the editor does not.

## What the disassembly says

`ActorVisibility` (`Editor.dll 0xa6d00`, decoded in `spikes/2026-07-15-native-materialize/re-raw-zones/
lightflood-6d00.md`) narrows the portal poly it is about to cross by the beam from the light through
the poly it entered by:

```text
jPrev = ClipPoly->NumVertices - 1                    ; 0x100a7067
for( j = 0; j < ClipPoly->NumVertices; jPrev = j++ )
{
    if( Poly.NumVertices >= 14 ) break;              ; 0x100a7083  cmp eax, 0xe / jge
    FPlane Pl( Actor->Location,                      ; 0x100a7146  core.dll 0xb440
               ClipPoly->Vertex[j],                  ;   (Location is built LAST -> arg A)
               ClipPoly->Vertex[jPrev] );
    r = Poly.SplitWithPlaneFast( Pl, &Front, &Back ); ; 0x100a7152
    if( r == SP_Back  ) goto NextPortal;
    if( r == SP_Split ) Poly = Front;
}
```

Three facts the port was missing or had wrong:

1. **`FPlane(A,B,C)` normalizes** (`core.dll 0x1000b4c8` calls `FVector::SafeNormal`, `0x51090`).
   `SafeNormal` returns `FVector(0,0,0)` when `SquareSum < SMALL_NUMBER` (`1e-8`, `.rdata
   0x100a0a40`) and otherwise scales by a reciprocal built as
   `(float)(1.0 / (float)sqrt((double)SquareSum))` — the square root is rounded to f32 BEFORE the
   division (`0x100510f5` / `0x10051104`). `W = (A.y*N.y + A.x*N.x) + A.z*N.z`, and
   `FPlane::PlaneDot` (`core.dll 0x24e60`) sums as `(x*Nx + y*Ny) + (z*Nz - W)`.
2. **The 14-vertex guard is a `break`, not a truncate.** It is tested at the TOP of each edge and
   leaves the loop with the poly it has; native clipped against every edge and then chopped the
   result to 14, which corrupts the polygon instead of stopping.
3. `SplitWithPlaneFast`'s `+/-0.25` (`Engine.dll .rdata 0x206780`/`0x20b580`) is a **world-unit**
   epsilon, which is only true for a unit-length normal.

## The fix

`permeating_lights.rs`: `safe_normal` + `plane_w` + `plane_dot` reproduce the three `core.dll`
routines; `clip_beam` normalizes the beam plane, breaks at 14 vertices, and passes `(normal, w)` to
`split_with_plane_fast` instead of an origin. The orientation stays explicit (flip when the clip
poly's own vertices fall negative): the editor inherits it from its portal poly's winding, and
native's portal polys are synthesized by `zones::collect_portals` from `plane_axes`, which carries
no such guarantee.

## Evidence

- `uedcli/tests/test_engine_facts.py::test_permeating_light_beam_planes_are_normalized_and_stop_clipping_at_14_vertices`
  pins the eight instruction encodings and the three `.rdata` floats above.
- `permeating_lights.rs` unit tests `clip_beam_rejects_a_poly_that_only_grazes_the_beam` (0.1 units
  inside at one end, 10 outside at the other — rejected whole with the epsilon alive, sliver-clipped
  without it) and `clip_beam_keeps_a_poly_well_inside_the_beam`.
- `parity_gate.py`: NYC_Bar N=151 PASS, no new mask. `ladder_run.py` takes NYC_Bar from N=150 to
  **N=152**; it now bails at N=153 on a different array (three world `LightMap` records get an
  `iLightActors` run UED22 leaves at -1 — the per-surf raytrace pass, not this flood).
- Island N=123 is unchanged by this fix — a different cause, below.

## Island N=123 is NOT this bug — it is the portal graph

Island's single remaining mismatch (1 leaf of 163: leaf 26 gets `Light124`, UED22 gives it nothing)
survives the fix, and the beam that reaches it is not marginal. Traced with a temporary
`UEDCLI_PERM_TRACE`/`UEDCLI_PERM_CLIPTRACE` instrumentation of `actor_visibility`:

- The light is at `(-4528.35, 4385.68, 64.37)`, `WorldLightRadius` 1675, seeded in leaf 85, and
  reaches leaf 26 through leaf 32 and leaf 27. Of the 13 beams that arrive at the 27->26 portal,
  exactly one survives, and its tightest clip edge leaves the target 1.79 world units inside — 7x
  the 0.25 epsilon, so no arithmetic difference closes it. For UED22 to reject it the portal quad
  would have to move ~24 units.
- Leaf 26's own neighbours (27 and 45) BOTH carry `Light124` in UED22's build, and UED22 gives leaf
  26 no light at ALL — which is what `ActorVisibility` produces for a leaf with **no portals**
  (`0x100a6e0d` returns 0 before the radius gate). Only one BSP node references leaf 26 at all
  (node 358, `iLeaf = (-1, 26)`); native's two portals for it come from `zones::collect_portals`
  finding adjacency across other nodes' planes.
- The editor's portal builder differs from `collect_portals` in a checkable way.
  `FEditorVisibility::MakePortals` (`Editor.dll 0xa9750`) walks the tree pushing an ancestor stack
  at `this+0x14` (the `+0x20` child's entry ORed with `0x40000000`), builds
  `BuildInfiniteFPoly(Model, iNode)` (`0xa7ae0`), and hands it to `FilterThroughSubtree`
  (`0xa9970`), which clips it against each ancestor with `FPoly::SplitWithNode(Model, iNode, Front,
  Back, VeryPrecise = 1)` (`0x100a9a4c` pushes the `1`) and **discards the poly outright when the
  split comes back `SP_Coplanar`** (`0x100a9a80 test eax,eax / je <return>`). Native's
  `zones::clip_poly` is a plain Sutherland-Hodgman clip with a `1e-4` tolerance and no `SP_*`
  classification, so a face coplanar with an ancestor plane survives on BOTH sides instead of being
  dropped, and the precise threshold is `THRESH_SPLIT_POLY_PRECISELY`, not `1e-4`.

Porting that is a change to the portal graph the ZONE union-find also rides on, so it is scoped as
its own item rather than folded in here.
