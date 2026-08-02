# Spike 2 — DeusEx mesh format (confirm the "different format" hypothesis; native feasibility)

**Status: RESOLVED — the DeusEx mesh vertex format genuinely differs from stock
Unreal, characterized precisely and confirmed on 178/178 meshes.** Native mesh
decode is feasible (HIGH). Harness: [`harness/umesh_probe.py`](harness/umesh_probe.py).

## Question

Andrzej's hypothesis: stubs aren't needed because of package version (v68 vs v69) —
they're needed because *DeusEx stores a different mesh format than Unreal* (and
depends on different `Engine.u`/`Core.u`). Confirm the mesh-format claim concretely,
and assess whether we can decode DeusEx meshes natively (replacing `umodel.exe`).

## Answer: confirmed. The vertex stride differs.

| | vertex element | size | precision |
|---|---|---|---|
| **stock Unreal/UT** `FMeshVert` | bit-packed dword `X:11, Y:11, Z:10` | **4 bytes** | lossy (~±1023 range) |
| **Deus Ex** `FMeshVert` | `int16 X, int16 Y, int16 Z, int16 pad` | **8 bytes** | full int16 |

Decisive evidence (mesh `Keypad3`, a box): the package's first vertex array decodes
as int16 quadruples to exactly the 8 box corners —
`(-1600,256,-1152), (-1600,256,1152), (1600,256,-1152), …` — matching its FBox
`Min(-1600,-256,-1152) Max(1600,256,1152)`. umodel's export of the same mesh gives
packed dwords that decode to `(-511,82,-368)…` — the **same geometry scaled by
~1/3.13** (because the packed dword can't hold ±1600), with `MESHMAP SCALE` adjusted
to compensate. So **umodel down-converts DeusEx's 8-byte verts to Unreal's 4-byte
packed format**; the exact 72-byte packed frame umodel emits is NOT present in the
package (the package holds 8-byte verts).

(Corpus: the RETAIL v68 `Tools/uedcli/uned/DeusExAssets/System/DeusExDeco.u` — NOT the
v69 stub at `uned/UED22/DeusExDeco.u`, which is a re-encoded packed-vert package and
returns 0/178 here.)

Generality: across **all 178 LodMesh/Mesh objects in `DeusExDeco.u`**, the first
vertex array has element size exactly 8 and every decoded int16 vertex lies within
that mesh's own FBox — 178/178.

## Why this is a (second) reason stubs exist

The UT-lineage UED22 editor and stock Unreal mesh code expect the 4-byte packed
`FMeshVert`. A DeusEx mesh's 8-byte verts have a different stride, so loading a
DeusEx code package's meshes into UED22 fails / corrupts — which is why the stub
pipeline runs `umodel` to re-encode meshes into the packed format UED22 accepts.
This is the mesh half of "why stub"; the code half is the `Engine.u`/`Core.u`
divergence (Spike 6). **Neither is a package-version (v68/v69) problem** — UED22's
UCC reads v68 fine (direction/containers.md 2026-06-22); it's a *content-format* + *class-graph*
problem. Both are sidestepped by never loading DeusEx packages into UED22 (the
native-write thesis).

## Decoded body layout (so far)

```
<tagged property list> None      # usually empty for a mesh
FBox  PrimitiveBox    25 bytes   # Min FVec(12) + Max FVec(12) + IsValid(1)
FSphere PrimitiveSphere 16 bytes # center FVec(12) + radius f32(4)
Verts : TLazyArray<FMeshVertDeusEx>
    i32 SkipOffset               # absolute file offset just past the data
    ci  Count
    Count x 8 bytes              # int16 X, Y, Z, pad
... Tris / AnimSeqs / Connects / VertLinks / Textures / Scale / Origin / RotOrigin
    / (LodMesh) LOD fields — standard TArrays/scalars, NOT parsed in this spike.
```
Only the first array uses the `TLazyArray` skip-int header; the rest are plain
`TArray`s. (Ground-truth counts to drive a full parse come free from umodel's
`_a.3d`/`_d.3d` headers: `WORD NumFrames, FrameSize` and `WORD NumPolys, NumVerts`.)

## Native feasibility & where it fits

- **Feasible, HIGH confidence.** Verts are trivial (int16); the remaining arrays are
  standard UE1 `TArray`s of `FMeshTri`/`FMeshAnimSeq`/etc., decodable with the same
  reader as textures, validated against umodel `.3d` counts. A full native mesh
  decoder is a **bounded (~1 day) follow-up**, not done here.
- **NOT on the de-containerization critical path.** Mesh extraction (umodel) exists
  today *only* for the stub pipeline. Under the native-write thesis stubs die, so
  umodel isn't needed to ship maps. Native mesh decode earns its keep for *optional*
  features — a mesh catalog (cf. the texture catalog), a native actor preview — and
  for fully retiring `umodel.exe` from every path. Scheduling it is a roadmap call.

## Serialize structure (disassembled 2026-06-27) — de-risks a future full decoder

Why these are LOD meshes: DeusEx decorations are **`ULodMesh`** (not bare `UMesh`), so the
renderable geometry is in the LOD `Wedges`/`Faces`, not `UMesh.Tris` (which is empty —
matching the `count=0` seen after the vertex array). umodel's `NumVertices=18`/`NumPolys=10`
for `Keypad3` = **Wedges / Faces**, over the 8 position-verts.

`ULodMesh::Serialize` (Engine.dll RVA `0x124300`, image base `0x10000000`) calls
`UMesh::Serialize` (`0x16e330`) then serializes member TArrays in order:

| member off | serializer | likely field |
|---|---|---|
| +0x12c | `0x1233e0` | `CollapsePointThus` (TArray<WORD>) |
| +0x138 | `0x1233e0` | `FaceLevel` (TArray<WORD>) |
| **+0x144** | `0x1234e0` | **`Faces`** (TArray<FMeshFace>: `iWedge[3]`+`MaterialIndex`) |
| +0x150 | `0x1233e0` | `CollapseWedgeThus` (TArray<WORD>) |
| **+0x15c** | `0x123720` | **`Wedges`** (TArray<FMeshWedge>: `iVertex`+UV) |
| +0x168 | `0x123600` | `Materials` (TArray<FMeshMaterial>: `PolyFlags`+`TextureIndex`) |
| +0x174 | `0x1234e0` | `SpecialFaces` |
| then raw 4-byte scalars at +0x180/+0x184/+0x188/+0x19c/+0x18c | `[0x101f90a8]` | `ModelVerts`/`SpecialVerts`/`MeshScaleMax`/`LODHysteresis`/… |

`UMesh::Serialize` (the base, reached first) serializes verts at `+0x54`/`+0x6c`, then a
sequence of ~12 TArray/field serializers (`0x1016d210`/`0x1016d070`/`0x10112270`/
`0x1016cb70`/`0x1016d3b0`/`0x1016d550`/…) with DeusEx-licensee-specific handling, ending in
raw scalars (`FrameVerts`/`AnimFrames`/`ANDFlags`/`ORFlags`/`Scale`/`Origin`/`RotOrigin`/…).

**Assessment:** a fully byte-accurate native mesh decoder is **feasible but a bounded
multi-hour RE project** — each of the ~19 serializers (`UMesh`'s ~12 + `ULodMesh`'s ~7)
needs its per-element byte format disassembled (as the Model decode did), then the parser
validated by EOF-consumption + umodel count-match (Faces=10, Wedges=18). The vertex format
(the spike's core finding) + the serialize map above are the hard-won starting points. It
stays **off the de-containerization critical path** (umodel only feeds stubbing, which the
native-write thesis deletes), so it's scheduled only if a mesh catalog / native preview of
actor meshes is wanted.

## Deferred
- Full native mesh decoder (Tris/anim/LOD/textures) + an exporter or in-memory mesh.
- The 4th int16 ("pad") semantics — 0 in every sample; likely true padding.
- Confirm the same 8-byte stride on `DeusExCharacters.u` (skeletal/anim-heavy) and a
  stock-Unreal `.u` (to show the 4-byte packed contrast in-repo) — expected, untested.
