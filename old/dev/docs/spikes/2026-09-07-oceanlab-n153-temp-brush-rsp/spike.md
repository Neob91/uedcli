# OceanLab N=153 and N=155 — the temp brush BSP's missing `RebuildSimplePolys=1`, then Pass F

**Result: OceanLab N=93 → 155+, no parity-bar change.** Two independent fixes, both faithful ports
of already-decoded editor routines. §1–§4 are N=153 (the temp brush BSP), §5 is N=155 (Pass F).

N=153's two world `Model2` points came out 29 ULP off. The cut vertex arithmetic was fine; the PLANE
it was cut against was not. `bspBrushCSG` builds the per-brush temp BSP with
`RebuildSimplePolys=1`, which makes coplanar faces SHARE the splitter's surf. Native gave every face
its own surf, and a surf allocates its texture axes into the same `Vectors` pool the face normals go
into — so a coplanar sibling's authored texture axis got into the pool first and
`bspAddVector(exact)` deduped a later face's normal onto it.

## 1. The symptom

`ladder_run.py --dx 14_OceanLab_Lab.dx --from 153 --to 153` bails with two residuals: `BODY model
model2` and `BODY polys polys@model model2`. `model_dump.py` narrows it to exactly two of 2634
points (every other array, `vectors` included, byte-identical):

| slot | native | UED22 |
|---|---|---|
| 1530 | `(-12, 152.0001983642578, -1856)` | `(-12, 151.999755859375, -1856)` |
| 1584 | `(-36, 152.0001983642578, -1856)` | `(-36, 151.999755859375, -1856)` |

`151.999755859375` is `0x4317fff0` — exactly `Brush431`'s `Location.Y - PrePivot.Y`
(`80 - 71.999755859375`), i.e. the plane the vertex is cut against. Native's `0x4318000d` is 29 ULP
above it. `soup_poly_dump.py` (harness) shows the four affected soup polys all belong to
**`Brush147`** (trunk actor 152), split by **`Brush431`** (actor 153) as it subtracts.

## 2. The cut vertex is right; the plane is wrong

Tracing `FPoly::split_with_plane`'s crossing branch shows the edge `(-12, 96, -1856) → (-12, 160,
-1856)` cut against base `(0, -0.000244140625, -1704)` — `Brush431` poly 8's world `Origin` — with
TWO different normals across the build:

* `(0, 0xbf3504f7, 0xbf3504f7)` — symmetric, from the world tree's own surf, → `0x4317fff0`.
* `(0, 0x3f3504e6, 0x3f350508)` — **asymmetric**, from the temp brush tree, → `0x4318000d`.

`lpi_normal_variants.py` (harness) confirms the arithmetic is not the variable: `CalcNormal`'s
`3f3504f4`, the authored `3f3504f7`, the world pool's `3f3504f3` and the negated face all give the
editor's `0x4317fff0`. Only the asymmetric normal moves it.

`0x3f3504e6`/`0x3f350508` is `0.707106`/`0.707108` — the **authored `TextureU` of `Brush431`'s poly
4**, a coplanar sibling of the `x = -12` face group. It reaches the split as a plane normal because:

1. `alloc_surf` adds a surf's `vNormal` (`exact = true`, `THRESH_NORMALS_ARE_SAME` 2e-5) and then its
   `vTextureU`/`vTextureV` (`exact = false`, 4e-4) into ONE `Vectors` pool.
2. Native's temp BSP gave each of `Brush431`'s 20 faces its own surf, so poly 4's texture axes were
   pooled at surf 7 — before poly 8's surf 14.
3. Poly 8's normal is `(0, 0x3f3504f4, 0x3f3504f4)`, within 2e-5 of poly 4's axis per component, so
   `bspAddVector` returned the axis's slot instead of pushing the normal.

This is the same absorb-a-normal-into-a-texture-axis mechanism the Island N=6 work pinned
(`a_texture_axis_absorbs_a_later_near_equal_normal`) — correct behaviour, wrong pool contents.

## 3. Why the editor's pool never holds that axis

`bspBrushCSG @0x35b83`–`0x35b85` calls `bspBuild(TempModel, LAME, 0, 0, RebuildSimplePolys=1)`
(**[DISASM]**, `spikes/2026-07-15-native-materialize/re-raw-zones/findbestsplit-params-decode.md`
Evidence 4 — already cited by `build_brush_temp_bsp`'s own doc comment for the `Opt`/`Balance`
values, but the flag itself was never wired up). With `RebuildSimplePolys` non-zero,
`SplitPolyList` seeds the links itself: the splitter gets `iLink = Surfs.Num()` (`0x100345cf`) and
every COPLANAR poly gets `Surfs.Num()-1` (`0x1003468c`) — the splitter's surf. A shared surf
allocates no `pBase`, no `vNormal` and no texture axes.

`Brush431` is a 2D loft: its 20 faces fall into coplanar groups (six at `x = 12`, six at `x = -12`,
the rest one-offs). Under the editor's rule each group contributes ONE surf, so only the group
splitter's texture axes are pooled — and poly 4 is not a splitter. Poly 8's normal is then pushed
fresh, symmetric, and the cut lands on `0x4317fff0`.

`build_brush_temp_bsp` passed `rsp_links: None` and forced `p.i_link = -1`, i.e. a surf per face.
`split_poly_list`'s `rsp_links` mode is already the exact engine rule (it is what the mover build and
the repartition frontier use); the fix is to engage it here too.

## 4. Result

* N=153 gates **PARITY: YES**, no mask, no exclusion.
* Regression: `bspcsg.rs::temp_brush_coplanars_share_the_splitters_surf` — three faces (a coplanar
  pair carrying the real `0.707106`/`0.707108` axis, plus a 45° face) must make TWO surfs, and the
  45° face's plane normal must be its own bits. It fails with `left: 3, right: 2` without the fix.

## 5. N=155 — Pass F was a portal-fragment walk that skipped zone 0

With N=153 fixed, OceanLab reached N=154 and bailed at N=155 on ONE residual: two `Zones`
connectivity masks. Native `Zones[0] = 0x01`, `Zones[1] = 0x82`; UED22 `0x03` / `0x83` — the two
zones are mutually connected in the editor's build and not in native's. `leaves` (so every leaf's
`iZone`), `nodes`, `points` and `surfs` were byte-identical, which rules out the zone ASSIGNMENT and
leaves Pass F.

Native built connectivity from the Pass-B portal FRAGMENT list, filtered by the zone-barrier set,
and skipped any pair with `za == 0 || zb == 0`. `FEditorVisibility::BuildConnectivity`
(`Editor.dll 0xa7960`, **[DISASM]**, `re-raw-zones/passesEFG-8850-7960-7e60.md` Pass F) does
neither. It walks the NODES:

```c
for (i = 0; i < 64; i++) Zones[i].Connectivity = 1ull << i;
for (iNode = 0; iNode < Nodes.Num; iNode++) {
    if (!(Surfs[Nodes[iNode].iSurf].PolyFlags & PF_Portal)) continue;   // 0x100a79f7
    Zones[Node.iZone[1]].Connectivity |= Bit64(Node.iZone[0]);          // 0x100a7a23
    Zones[Node.iZone[0]].Connectivity |= Bit64(Node.iZone[1]);
}
```

The edges are the node's own two sides, and zone 0 is not special-cased. Ported as
`zones.rs::build_connectivity`; N=155 gates **PARITY: YES**. Regression:
`zones.rs::portal_node_connects_zone_zero_to_its_other_side`.

## Harness

* `harness/lpi_normal_variants.py` — the f32 `FLinePlaneIntersection` on this exact edge/plane for
  each candidate normal.
* `harness/soup_poly_dump.py` — world CSG-soup `FPoly`s with vertices as f32 bits, filterable by
  brush or by proximity to a point; the "which face got cut, and by whose plane" view
  `model_dump.py` cannot give.
