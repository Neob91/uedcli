+++
priority = "p2"
kind = "debug"
summary = "Island is byte-exact N=1..122 and bails at N=123: native gives world leaf 26 a permeating-light run UED22 leaves empty. Root-caused to the PORTAL GRAPH, not the beam clip — `zones::collect_portals` clips with a plain 1e-4 Sutherland-Hodgman where `FilterThroughSubtree` uses `SplitWithNode(VeryPrecise)` and DISCARDS an `SP_Coplanar` result."
spikes = ["dev/docs/spikes/2026-09-06-permeating-beam-plane-normalize/"]
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

## Not the beam clip

The unnormalized-beam-plane bug that this item was originally paired with is fixed
(`nyc-bar-n-151-world-model2-leaf-permeating-light`, spike
`2026-09-06-permeating-beam-plane-normalize`) and does not move Island. Measured with a temporary
trace of `actor_visibility`:

- `Light124` sits at `(-4528.35, 4385.68, 64.37)`, `WorldLightRadius` 1675, seeds in leaf 85 and
  reaches leaf 26 via leaf 32 and leaf 27. Of the 13 beams arriving at the 27->26 portal exactly one
  survives, and its tightest clip edge leaves the target **1.79 world units** inside — 7x the 0.25
  epsilon. No arithmetic difference closes that; the portal quad would have to move ~24 units.
- UED22 gives leaf 26 **no light at all**, which is what `ActorVisibility` produces for a leaf with
  no portals (`Editor.dll 0x100a6e0d` returns 0 ahead of the radius gate). Only one BSP node
  references leaf 26 (node 358, `iLeaf = (-1, 26)`); native's two portals for it come from
  `zones::collect_portals` finding adjacency across other nodes' planes.

## Next step — port the editor's portal filter

`FEditorVisibility::MakePortals` (`Editor.dll 0xa9750`) recurses the tree pushing an ancestor stack
at `this+0x14` (the `+0x20` child's entry ORed with `0x40000000`), builds
`BuildInfiniteFPoly(Model, iNode)` (`0xa7ae0`) per node and hands it to `FilterThroughSubtree`
(`0xa9970`). That clips against each ancestor with
`FPoly::SplitWithNode(Model, iNode, Front, Back, VeryPrecise = 1)` (the `1` pushed at `0x100a9a4c`)
and **discards the poly outright on `SP_Coplanar`** (`0x100a9a80 test eax,eax / je <return>`); it
keeps `Front` in the front subtree and `Back` in the back one, and discards whole on the wrong-side
`SP_Front`/`SP_Back`. `AddPortal` (`0xa72a0`) has no area gate at all — only `iFrontLeaf != -1 &&
iBackLeaf != -1`.

Native's `zones::clip_poly` is instead a plain Sutherland-Hodgman clip with a `1e-4` tolerance and
no `SP_*` classification, so a face coplanar with an ancestor plane survives on BOTH sides rather
than being dropped, and native adds a `MIN_AREA = 1.0` gate the editor does not have.

Porting this changes the portal graph the ZONE union-find also rides on, so re-verify all five
ladders after it, not just Island.

## Repro

    ladder_run.py --dx dev/games/deusex/Maps/01_NYC_UNATCOIsland.dx --from 123 --to 123 --keep-native
    model_dump.py <native_N123.dx> <ref_N123.dx> Model2
