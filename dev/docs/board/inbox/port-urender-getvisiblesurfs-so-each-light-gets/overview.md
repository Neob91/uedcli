+++
priority = "p2"
kind = "implement"
summary = "The last structural gap in the native lighting bake: the editor picks each light's surface set with a six-face 1024x1024 cube-map rasterization (URender::GetVisibleSurfs -> OccludeBsp, per-zone span buffers), and native uses a plane test plus per-lumel LOS. On UNATCO that leaves native listing 618 (surface, light) pairs the editor rejects, against only 7 it misses. Fully decoded below."
+++

## Status 2026-08-30: pixel-center rasterization fix, gap smaller again, still NOT closed

`rasterize_node`'s screen-space rounding switched from full-coverage (`floor`/`ceil`, pads every
polygon's footprint outward) to pixel-center inclusion — see `getvisiblesurfs-wanchai-run-gap-root-
cause`, which also found `MergeWith`/zone-crossing is NOT the dominant cause of Wanchai's larger
`missed` count as the previous status here speculated (only ~20% of missed pairs cross a zone; the
rest are same-zone rasterization-precision losses in dense clutter). Wanchai: extra 134→79, missed
350→314, byte-identical 3228→3297/4530 (71.3%→72.8%). UNATCO (geometry-matched, tree not currently
node-exact): run_ok 92.0%→94.2%. Shipped, tested, committed.

## Status 2026-08-29: self-occlusion landed, gap much smaller, still NOT closed

`uedcli-native/src/visible_surfs.rs` now ports the full gather including true opaque-surface
self-occlusion (`SUBTRACT_OCCLUSION = true`, `SpanBuf` rewritten as a per-row interval list to
match the real `FSpanBuffer` — see `getvisiblesurfs-self-occlusion-regresses-missed`, resolved).
UNATCO: extra 618→151, missed 7→233, byte-identical records 2518→2628/3345. Wanchai: extra
526→131, missed 12→347, byte-identical 3229→3228/4530 (flat). Real, tested, committed — closer,
but not 0/0 on either level. `MergeWith` (`render.dll 0x1001e3b0`) is still undecoded — see the
2026-08-30 status above for why it turned out not to be the dominant cause of Wanchai's gap.

# Port `URender::GetVisibleSurfs` so each light gets the editor's surface set

The native `LIGHT APPLY` bake reproduces the editor's own output on `01_NYC_UNATCOHQ` to 99.0% of
per-(surface, light) shadow bit-planes byte-identical and 99.99% of lumel bits. The remaining
structural difference is WHICH surfaces each light is listed on: 368 of 3345 records have a different
light run, and it is one-sided — native adds 618 pairs, misses 7.

The editor's gather pass (`Editor 0x100a4ba0`) does not use a geometric predicate. Per light it sets
`ShowFlags = 0x800`, `RendMap = 6`, opens a 0x400 x 0x400 offscreen viewport at the light's Location
and calls `URender::GetVisibleSurfs` (`render.dll 0x100187b0`, `URender` vtable `+0x84`).

⚠️ The `uned/UED22/` DLLs are 2022 OldUnreal-469-lineage rebuilds (MSVC 14.32, `TimeDateStamp`
2022-10-29; `Engine.dll` exports `URenderDeviceOldUnreal469`), so all of this is what OUR editor runs
and must not be cross-checked against 1999 UT source expectations.

## What it is

A six-face cube map. Verified-from-instructions:

```c
for( i=0; i<6; i++ ) {                                   // 0x100187f2
  Viewport->Actor->Rotation = SixFaces[i];                // 0x10018938
  Frame = CreateMasterFrame(Viewport, Actor->Location, Actor->Rotation, NULL);
  save = Viewport->RenDev->VolumetricLighting; ... = 0;   // 0x100189a2
  OccludeBsp(Frame);                                      // 0x100189b2 -> 0x10018e10
  for( j=0; j<3; j++ )
    for( D = Frame->Draw[j]; D; D = D->Next )
      iSurfs.AddUniqueItem(D->iSurf);                     // 0x100120b0
  Viewport->RenDev->VolumetricLighting = save;
  FinishMasterFrame(); Mark.Pop();
}
```

The six rotators (`0x10018816`–`0x100188c2`, 0x4000 = 90°): `(0x4000,0,0)` +Z, `(0xc000,0,0)` −Z,
`(0,0,0)` +X, `(0,0x8000,0)` −X, `(0,0xc000,0)` −Y, `(0,0x4000,0)` +Y.

`OccludeBsp` (`0x10018e10`) is the standard UE1 span-buffer occluder and is where every accept and
reject happens. It keeps `FSpanBuffer ZoneSpan[64]` on the stack (`0x1001926b`, stride 0x20), all
empty except the view's own zone which gets the full screen (`0x1001928f`); clips and
scanline-rasterizes each node polygon (`ClipBspSurf 0x10019987`, rasterizer `0x1001b470`); and accepts
the surface iff `FSpanBuffer::CopyFromRaster(Update)` returns non-zero (`0x10019c1c`), i.e. **at least
one pixel span survived against the accumulated per-zone buffer**. An opaque surface then SUBTRACTS
its spans (`CopyFromRasterUpdate`, `0x1001df70`) so it occludes what is behind it; a
masked/translucent one uses the read-only `CopyFromRaster` (`0x1001dd10`) and does not
(`0x10019b57` selects on `PolyFlags & 0x10020047`).

So a surface with clear geometric line of sight from the light is still rejected when every pixel it
covers, in all six views, was already claimed by a nearer opaque polygon — or when its zone is never
reached (below). **That cannot be reduced to a per-surface geometric predicate.**

## The per-node/per-surface filters, in traversal order

Explicit-stack front-to-back DFS over `Model.Nodes` (24-byte GMem records: `iNode`, `farChild`,
`farOutside`, `Outside`, `resumeState`, `parent`). Per node:

1. **Zone-mask prune** (`0x1001930b`): `if bUseZones && (ActiveZoneMask & node->ZoneMask) == 0` → pop
   the whole subtree. `ActiveZoneMask` starts as `1 << Frame->ZoneNumber`, is OR'd with the far zone
   when a visible `PF_Portal` node is crossed (`0x1001a257`), and is cleared for a zone whose span
   buffer runs dry (`0x1001a7b7`).
2. **`bUseZones` is literally `Frame->ZoneNumber != 0`** (`0x10019303`). A light whose Location is in
   zone 0 gets a completely UNZONED pass: no zone prune, one shared span buffer, and `PF_Portal`
   surfaces skipped (`0x100198ea`). That is a different algorithm, not a special case — check whether
   any light in the corpus is in zone 0 before assuming it never happens.
3. **Moving-brush filter** (`0x10019349`): `Level->BrushTracker->SurfIsDynamic(iSurf)` skips the node
   (`ULevel+0xfc`, set by `GNewBrushTracker` at `Engine 0x1015b2a5`; slot `+0xc` is
   `Engine 0x1014d510` = `iSurf >= this->+0x20`). Whether `BrushTracker` is non-NULL during
   `LIGHT APPLY` is NOT determined.
4. **Bound-box occlusion** (`0x1001932c`): skipped when `node->iRenderBound == -1`; else
   `BoundVisible(Frame, &Model->Bounds[iRenderBound], …)` and, with zones, `BoxIsVisible` against
   every active zone's buffer. `0` → `NodeFlags |= NF_BoxOccluded (0x10)` and pop the subtree.
   `iCollisionBound` is not used. Amortization trap: the box test only runs when `NodeFlags & 0x10` is
   already set OR `((iNode ^ *(0x1005fa24)) & 0xf) == 0`, and that counter is bumped only in
   `DrawWorld` — which this path never calls — so the same fixed 1/16 of nodes is tested for every
   light. Box rejection is conservative, so skipping it should change cost and not the surface set;
   believed equivalent, not proven. `OccludeBsp` also MUTATES `NodeFlags` bits `0x08`/`0x10` and they
   persist across calls.
5. **`IsFront = PlaneDot(node->Plane, Frame->Coords.Origin) > 0.0f`**, epsilon exactly 0
   (`0x10019693`–`0x100196c6`); `Coords.Origin` is the light's Location.
6. **Frustum-cone reject** (`0x100197b8`–`0x10019884`): with `sign = IsFront ? +1 : -1`, pop when all
   four `sign * (node->Plane | Frame->ViewSides[k]) > 0`.
7. **Back-face** (`0x100198c7`): `!IsFront && PlaneDot < -1.0 && !(PolyFlags & 0x04000100)` → drop.
   ALREADY PORTED (see `native-lighting-backface-cull-assumes-single`, done).
8. `PF_Portal && !bUseZones` → drop (`0x100198e3`).
9. `Viewport->Actor` `IsA(PlayerPawn)` → a virtual `+0xb8` filter (`0x100198f7`). Not resolved; the
   editor camera is a `Camera`, which may or may not be a `PlayerPawn`.
10. **Zone reachability** (`0x10019961`): `ZoneSpan[iZone[IsFront]].ValidLines <= 0` → drop. A zone's
    buffer stays empty until a visible `PF_Portal` surface `MergeWith`es spans into it
    (`0x1001a2de`).
11. `PolyFlags &= 0xfffffffe | (ShowFlags >> 11)`, then `PF_Invisible` → not emitted
    (`0x1001a30d`).
12. Emission: a 0x4c-byte `FBspDrawList` onto `Frame->Draw[1 + ((PolyFlags & 0x10020047) != 0)]`;
    `Draw[0]` is never used here. Same surface + same Zone actor merges spans into the existing
    record, so a surface appears at most once per frame.

`AddUniqueItem` (`0x100120b0`) is a linear-scan dedup and the array is never emptied inside the
function, so the result is globally deduped across the six faces, in first-sighting order: face 0 (up)
… face 5 (+Y), and within a face the front-to-back DFS order (near child → own surface → `iPlane`
chain → far child) — not ascending `iSurf`.

## What `RendMap = 6` and `ShowFlags = 0x800` actually select

* `RendMap = 6` is read once on this path (`0x10019fe2`, `== 2`, in the portal branch) and falls into
  `ComputeRenderCoords`' default = perspective (`Engine 0x10132498`; only 13/14/15 are the ortho
  modes). It changes nothing.
* `ShowFlags = 0x800` — bit 11 makes the mask `0xfffffffe | 1` = all-ones, so **`PF_Invisible` is
  PRESERVED and invisible surfaces are excluded** (`0x1001908c`); with the bit clear they would be
  drawn. It also enables the `PF_Mirrored`/WarpZone `CreateChildFrame` recursion, but child frames are
  only created and linked — never occluded here, and only the MASTER frame's `Draw[]` is read — so
  mirrors and warp zones contribute no surfaces.

## Not used, contrary to a reasonable guess

`Model.Leaves`, `FLeaf.iVisibilityMask` and `Model.Visibility` play no part: `render.dll` imports no
`UModel::PotentiallyVisible`, and `Engine 0x101302d0` is a `mov eax,1; ret 8` stub. The only
`node->iLeaf[]` reads feed volumetric lighting, which this pass explicitly disables. `node.ZoneMask`
and `Bounds` ARE used. There is also no distance limit anywhere in `GetVisibleSurfs` — the radius
filter is entirely in the caller (`Editor 0x100a4ec6`: accept when `WorldLightRadius >=
|Plane.PlaneDot(light.Location)|`, note the ABS, so it does not filter back-facing surfaces either).

## The one unpinned input

`FovAngle` is `Actor+0x304` and the gather pass never sets it — it is whatever the temp viewport's
camera actor carries, and `Editor 0x100148ae` shows `NotifyPostChange` writing the editor's FOV
PREFERENCE into every viewport's actor, so it is not even a fixed constant. Six 90°-apart faces cover
the sphere only at FOV 90. `SpawnViewActor` (`Engine 0x10163470`) also REUSES a free existing `Camera`
rather than spawning fresh, so the value can be inherited. This needs settling (from `Engine.u`'s
`Camera` defaults and the editor ini) before a port can claim fidelity.

## Port sketch

A few hundred lines, all deterministic, no engine state beyond the Model:

1. Per light, per face: `Coords = ViewCoords/Rot` with `Origin = light.Location`,
   `Uncoords = Coords^T`, `Proj.Z = (SizeX/2)/tan(FovAngle·pi/360)` (= 512 at 1024 and FOV 90), the
   four clip slopes `= tan(FOV/2)`, `ViewSides[k] = normalize(±512, ±512, 512) · Uncoords`. Four side
   planes, no near/far (`ClipBspSurf` seeds the outcode accumulator `0x3c`, `0x10013d4a`).
2. `ZoneSpan[64]` empty except the view zone = full screen; `ActiveZones = {viewZone}`;
   `bUseZones = viewZone != 0`.
3. DFS from node 0 with `Outside = Model.RootOutside` and
   `ChildOutside(i, Outside, x) = i ? (Outside || IsCsg(x)) : (Outside && !IsCsg(x))`,
   `IsCsg(x) = NumVertices > 0 && !(NodeFlags & (0x21 | x))`; the filter order above.
4. Clip the node polygon (`Verts[iVertPool..+NumVertices]` → `Points[pVertex]`) to the four side
   planes, scanline-rasterize, `CopyFromRaster(Update)` against `ZoneSpan[zone]`; non-empty → emit
   `iSurf`, and for opaque `PolyFlags` subtract the spans.
5. On a visible `PF_Portal` node: `ActiveZones |= 1 << iZone[!IsFront]` and
   `ZoneSpan[farZone].MergeWith(portalSpans)`. Drop a zone when its `ValidLines` hits 0; stop when
   `ActiveZones` empties.
6. `AddUniqueItem` across all six faces, then the caller's `iLightMap != -1`,
   `bSpecialLit`↔`PF_SpecialLit` and `|PlaneDot| <= (LightRadius+1)*25` filters.

Still to decode for bit-exactness on marginal cases: `FSpanBuffer::CopyFromRaster` (`0x1001dd10`),
`CopyFromRasterUpdate` (`0x1001df70`), `MergeWith` (`0x1001e3b0`), and the rasterizer's edge stepping
(`0x1001b470`).

## Struct offsets pinned while decoding this

`FBspNode` = 0x40: `Plane 0x00`, `ZoneMask 0x10`, `iVertPool 0x18`, `iSurf 0x1c`, `iChild[0]`=Back
`0x20`, `iChild[1]`=Front `0x24`, `iChild[2]`=Plane `0x28`, `iCollisionBound 0x2c`,
`iRenderBound 0x30`, `iZone[2] 0x34/0x35` (bytes), `NumVertices 0x36`, `NodeFlags 0x37`,
`iLeaf[2] 0x38/0x3c`.
`FSceneNode` = 0x16c: `Viewport 0`, `Level 4`, `ZoneNumber 0x18` (byte), `Recursion 0x1c`,
`Mirror 0x20`, `Coords 0x34`, `Uncoords 0x64`, `Span 0x94`, `Draw[3] 0x98`, `Sprite[3] 0xa4`,
`X 0xa8`, `Y 0xac`, `Proj 0xd4/0xd8/0xdc`, clip slopes `0xec..0xf8`,
`ViewSides[4] 0xfc/0x108/0x114/0x120`.
`FSpanBuffer` = 0x20: `StartY 0`, `EndY 4`, `ValidLines 8`, `Index 0xc`, `Mem 0x10`.
`FTransform` = 0x20: `Point 0x00`, outcode byte `0x0c`, `ScreenX 0x10`, `ScreenY 0x14`, `IntY 0x18`,
`RZ 0x1c`.
`URenderDevice`: `Description 0x38`, `VolumetricLighting 0x58`, `ShinySurfaces 0x5c`, `Coronas 0x60`,
`HighDetailActors 0x64`.

Harness added while decoding: `rdis.py` (adds `render.dll` to the DLL map), `wstr.py`,
`fieldscan.py`, in `dev/docs/spikes/2026-08-27-native-light-apply-parity/harness/`.
