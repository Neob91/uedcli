# Spike — native mesh decode + render (no editor, no container, no umodel)

**Status: RESOLVED — YES.** A pure-Python decoder reads the complete `UMesh`/`ULodMesh` body of
both Deus Ex (v68) and UT-lineage (v69) packages, and a software rasterizer renders textured
thumbnails from it offline. Verified byte-exact on **902 meshes** (466 v68 + 436 v69) with zero
failures, and visually on decorations, items, and animated characters.

**Question (Andrzej, 2026-07-25):** for the class arm of the asset catalog, can we decode how
Deus Ex / Unreal store meshes and render them ourselves — rather than driving the OG Deus Ex
UnrealEd, or reverse-engineering the stub pipeline's `umodel.exe` export?

**Answer: we can decode them directly.** Neither fallback is needed. `umodel.exe` stays only for
the stub pipeline it already serves.

Harness: [`harness/umesh.py`](harness/umesh.py) (decoder), [`harness/render.py`](harness/render.py)
(mesh → PNG), [`harness/render_class.py`](harness/render_class.py) (class → PNG via class
defaults), [`harness/trace.py`](harness/trace.py) + [`harness/tail_probe.py`](harness/tail_probe.py)
(the instruments used to find each desync).
Builds directly on [`2026-06-27-decontainerize-uedcli/02-native-mesh-format.md`](../2026-06-27-decontainerize-uedcli/02-native-mesh-format.md)
(Spike 2), which established the 8-byte Deus Ex vertex and disassembled `ULodMesh::Serialize`'s
member order. Regression: `uedcli/tests/test_mesh_decode.py`.

---

## The method: consume-to-exact-end as the oracle

An export body occupies exactly `[soff, soff + ssize)`. So a parse that lands on the **final byte**
of every mesh in a package is structurally correct — a wrong field width, a missing array, or a
mis-ordered member desyncs and misses the end, essentially always by a lot. That turns layout
recovery into a search with a crisp pass/fail signal over a 900-mesh corpus, and it needed **no
further disassembly** beyond what Spike 2 already had.

A second, free check comes from `TLazyArray` itself: its header stores the absolute offset just
past its element data, so **each lazy array self-verifies** — a wrong element width is caught at
the array that has it, not 200 bytes downstream.

## Verified body layout (UE1 `UMesh` → `ULodMesh`)

```
<tagged property list, terminated by None>       # usually empty on a mesh
--- UPrimitive
FBox    PrimitiveBox           25 bytes          # Min FVec + Max FVec + IsValid byte
FSphere PrimitiveSphere        16 bytes          # center FVec + radius f32
--- UMesh
TLazyArray<FMeshVert>   Verts                    # stride 8 (Deus Ex) or 4 (stock Unreal) — below
TLazyArray<FMeshTri>    Tris                     # 20 B/elem; EMPTY on a LodMesh
TArray<FMeshAnimSeq>    AnimSeqs                 # variable; see the two traps below
TLazyArray<FMeshVertConnect> Connects            # 8 B/elem
FBox                    BoundingBox              # INLINE — UMesh re-serializes its own bounds,
FSphere                 BoundingSphere           #   duplicating UPrimitive's above
TLazyArray<INT>         VertLinks
TArray<UTexture*>       Textures                 # compact-index object refs
TArray<FBox>            BoundingBoxes            # per-animation-frame; PLAIN TArrays, not lazy
TArray<FSphere>         BoundingSpheres
INT FrameVerts; INT AnimFrames; DWORD AndFlags; DWORD OrFlags
FVector Scale; FVector Origin; FRotator RotOrigin
INT CurPoly; INT CurVertex
if ver == 65:  FLOAT (one scalar)
if ver >= 66:  TArray<FLOAT> TextureLOD
--- ULodMesh (only when the export's class is LodMesh)
TArray<WORD>          CollapsePointThus
TArray<WORD>          FaceLevel
TArray<FMeshFace>     Faces                      # 8 B: WORD iWedge[3] + WORD MaterialIndex
TArray<WORD>          CollapseWedgeThus
TArray<FMeshWedge>    Wedges                     # 4 B: WORD iVertex + BYTE U + BYTE V
TArray<FMeshMaterial> Materials                  # 8 B: DWORD PolyFlags + INT TextureIndex
TArray<FMeshFace>     SpecialFaces
INT ModelVerts; INT SpecialVerts
FLOAT MeshScaleMax; FLOAT LODHysteresis; FLOAT LODStrength
INT LODMinVerts; FLOAT LODMorph; FLOAT LODZDisplace
TArray<WORD>          RemapAnimVerts   📖         # empty in every mesh of the corpus
INT                   OldFrameVerts    📖         # == FrameVerts in retail v68; 0 in the v69 stubs
```

Confidence: the **structure** is ✅ (consume-to-exact-end on 902 meshes, both package versions).
The two final field **names** are 📖 — inferred from UE1 conventions; what is verified is an empty
`TArray<WORD>` followed by an INT. That INT equals `FrameVerts` in every **retail v68** mesh (which
is what identified it), but is **0** in the UED22-rebuilt v69 stubs — so only the field's PRESENCE
is invariant, not its value. A decoder must not validate on the value.

## The five things that are not guessable (each one silently destroys the parse)

1. **`FMeshAnimSeq.Group` is a SINGLE `FName`, not UT's later `TArray<FName> Groups`.** ✅
   A sequence with no group writes one `0` byte, which reads identically as an empty TArray — so
   the difference is invisible until a mesh actually uses groups. `DeusExCharacters.Pigeon` seq5
   (`Idle1`, Group=17) is the discriminator: the TArray reading takes 17 as an element count and
   detonates. This is why 4 of 5 packages appeared to parse cleanly at one point while characters
   and weapons failed.

2. **`FMeshAnimSeq`'s serialized order is not its declaration order:** `Name, Group, StartFrame,
   NumFrames, Notifys, Rate` — **`Notifys` before `Rate`**. ✅ (`DeusExDeco.Keypad3` seq0 decodes to
   Name=`All`, Group=None, Start=0, NumFrames=1, Notifys=[], Rate=30.0; reading Rate first desyncs
   by one byte.)

3. **`UMesh` re-serializes its own `BoundingBox`/`BoundingSphere` INLINE** right after `Connects`,
   duplicating the `UPrimitive` bounds already read — while the *per-frame* `BoundingBoxes`/
   `BoundingSpheres` come later as **plain `TArray`s**, not lazy arrays. ✅

4. **`SpecialVerts` sit at the FRONT of every frame.** ✅ A wedge's `iVertex` is relative to
   `frame_base + SpecialVerts`, not `frame_base`. Decorations have `SpecialVerts == 0`, so they
   render perfectly without the shift — the bug only appears on meshes with attachment points
   (`GM_Trench` has 3), and it appears as a *shredded spike-ball*, not as an obviously-off-by-3
   image. Frame `f` starts at `f * FrameVerts` (verts are **frame-major**, confirmed by measuring
   that the same index one frame later is ~3–27× closer than the adjacent index in-frame).

5. **The `ULodMesh` 5-byte tail is stock UE1, NOT a Deus Ex licensee addition.** ✅ It was initially
   read as licensee-specific because it appears on all 174 v68 `LodMesh` exports and on none of the
   4 plain `Mesh` exports — but the **committed v69 UED22 packages, built by UED22's own UT-lineage
   UCC, carry it too**. It tracks `LodMesh`-vs-`Mesh`, not Deus Ex-vs-Unreal. (Its INT is
   `FrameVerts` in retail v68 but 0 in the v69 stubs — presence is invariant, the value is not.)

## The vertex stride is self-describing — one decoder, no substrate flag

Spike 2 established that Deus Ex stores `FMeshVert` as **8 bytes** (`int16 X,Y,Z,pad`) where stock
Unreal uses a **4-byte** bit-packed dword (`X:11, Y:11, Z:10`). That looked like it would force a
per-substrate configuration flag. It does not: `Verts` is a `TLazyArray`, whose header carries both
the element count and the absolute end offset, so

```
stride = (skip_offset - first_element_offset) / count
```

reads the format straight off the data. ✅ The same decoder handles Deus Ex `.u` and stock
Unreal/UT `.u` with no flag and no guessing — which is what `direction/scope.md`'s generic-UE1 goal needs.
(The 4th int16 of the Deus Ex vertex is 0 across every vertex sampled — confirming Spike 2's
"likely true padding" on a much larger sample.)

## Coverage

| corpus | packages | meshes | parsed byte-exact | renderable |
|---|---|---|---|---|
| Deus Ex retail v68 | DeusExDeco, DeusExItems, DeusExCharacters, MPCharacters, TNM | 466 | **466/466** | 436/436 sampled |
| UED22 stubs v69 (packed verts) | DeusExDeco, DeusExCharacters, DeusExItems | 436 | **436/436** | — |

Cross-tool validation: `Keypad3` decodes to **18 wedges / 10 faces**, matching umodel's
`NumVertices=18 / NumPolys=10` ground truth recorded in Spike 2.

Skin resolution (mesh-side `Textures` array only): DeusExDeco 178/178, DeusExItems 150/158,
DeusExCharacters **32/100** — see below.

## Rendering: class defaults are the authority on skins

The mesh's own `Textures` array is only a fallback. For Deus Ex characters it is usually empty;
the real skins live in the **class's** `MultiSkins[i]` (per material index) or `Skin`, which uedcli
already resolves offline via `uprops.resolve_class_defaults`. ✅ So a class thumbnail is:

```
class defaults -> Mesh'Pkg.Name' + MultiSkins[i]  ->  decode mesh  ->  decode skins  ->  rasterize
```

`DeusEx.JCDentonMale` → mesh `DeusExCharacters.GM_Trench`, 603 triangles, 7 materials, **0**
mesh-side skins, **8** class `MultiSkins` overrides → a correct, recognizable JC Denton (trench
coat, sunglasses). Decorations resolve entirely mesh-side and need no class at all.

Renderer: z-buffered, affine-UV, Lambert-shaded, pure Python + Pillow (uedcli's only dependency).
Parse + skin-resolve for a whole package is ~3–4 s for 100–178 meshes.

## What this changes for the asset catalog

The class-screenshot arm was specced around a container render harness (temp level, one subtract
box per actor, materialize, deliver into the warm `preview --game` container, shoot). That harness
is **no longer required for a thumbnail**:

| | native render (this spike) | in-game render harness |
|---|---|---|
| cost | ~20 ms/mesh, offline | materialize + container boot per batch |
| shows | geometry + skins, synthetic light | real level lighting, sky, effects |
| deps | Pillow only | editor + game container |
| `DT_Sprite`/`DT_Brush` classes | N/A (no mesh) | N/A |

The **open `unlit`/fullbright spike is moot for thumbnails** — a native render controls its own
lighting by construction. The in-game path remains the better answer for "what the player actually
sees", so it stays available, but it is no longer a build blocker for the catalog.

## Deferred (with their board items)

- **Non-P8 skin formats.** Skins decode through the existing `utexture.py`, which is P8-only today;
  the non-P8 decoders are already a tracked build prerequisite of the catalog work.
- **`RemapAnimVerts` element layout** — every mesh in the corpus has it empty, so the element type
  is unverified; the decoder raises a named error rather than guessing if a non-empty one ever
  appears.
- **Multi-frame/animation selection.** Frame 0 is used for thumbnails; picking a *characteristic*
  frame (e.g. an `Idle` sequence's `StartFrame` rather than frame 0) is a catalog-quality question,
  not a decode question — the `AnimSeqs` table needed for it already decodes.
- **`Origin`/`RotOrigin` placement semantics** are applied as scale + auto-centering for thumbnails;
  exact actor-space placement matters only if native mesh rendering is later used inside
  `preview --native` for real scene composition.
