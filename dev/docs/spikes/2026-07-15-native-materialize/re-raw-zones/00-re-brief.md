# Shared RE brief — UED22 Editor.dll TestVisibility decode (2026-07-16)

## Target binary + tools

- DLL: `/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl/uned/UED22/Editor.dll`
  (32-bit x86, MSVC 2022 SSE build of the UT-v469-lineage editor). ImageBase `0x10000000`.
  All RVAs below are file RVAs; VA = 0x10000000 + RVA.
- Disassembler harness (already exists, works):
  ```
  cd /home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl/dev/docs/spikes/2026-07-15-native-materialize/harness
  /home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl/.venv/bin/python adis.py Editor <rva-hex> <len-hex>
  ```
  `adis.py` annotates call targets with demangled export names, string literals and float
  constants. `pe.py` has `read_at_va`, `exports`, `disasm` if you need raw bytes. Wide strings:
  most literals are UTF-16.
- The functions are laid out back-to-back with `int3` padding; disassemble until the `ret` that
  precedes `int3` padding. MSVC EH prologues (`push -1; push <funcinfo>; fs:[0]` dance) and the
  trailing `call 0x100ac127` (security cookie check) are boilerplate — skip in analysis.
- Common library helpers you will see:
  - `call 0x100123e0` with `ecx = &TArray` and one pushed arg = **`TArray<INT>::AddItem(value)`**
    (grows the array, appends the 4-byte value). The TArray struct is `{Data(+0), Num(+4), Max(+8)}`.
  - `call 0x10031450` with args `(4, [0x100ce508], 1, count, 0x10)` = **FMemStack allocation** of
    `count` elements from the global editor mem pool `GMem` (`[0x100ce508]`); returns pointer.
  - `[0x100ce884]` = `GWarn` (vtable +0x8 BeginSlowTask, +0xc EndSlowTask, +0x10 StatusUpdatef).
  - `[0x100ce768]` = `debugf`-style varargs log; `[0x100ce788]` = appError-ish; `[0x100ce71c]`,
    `[0x100ce718]` = GLog/GNames-adjacent globals (not load-bearing).
  - `[0x101722f8]` = `GEditor` (UEditorEngine*). vtable: +0x1f8 bspNodeToFPoly, +0x1fc bspBuild,
    +0x200 bspRefresh, +0x204 bspCleanup, +0x208 bspBuildBounds, +0x20c bspBuildFPolys,
    +0x210 bspMergeCoplanars, +0x214 bspBrushCSG, +0x264 TestVisibility.
  - `Core.dll` imports appear as `call dword ptr [0x100ceXXX]` — adis annotates most.

## Known struct offsets (verified in prior spikes — cite, don't re-derive)

**UModel (in-memory):**
| off | field |
|---|---|
| +0x58/+0x5c | `Nodes.Data / Nodes.Num` (FBspNode, 0x40 each) |
| +0x68/+0x6c | `Verts.Data / Verts.Num` (FVert 8 B: iVertex @+0, iSide @+4) |
| +0x78/+0x7c | `Vectors.Data / Num` (FVector 12) |
| +0x88/+0x8c | `Points.Data / Num` (FVector 12) |
| +0x98/+0x9c | `Surfs.Data / Num` (FBspSurf, 0x40 each) |
| +0xc0 | `Bounds` TArray (FBox = 6×f32 + 1 byte valid; 28 B mem) |
| +0xcc | `LeafHulls` TArray<INT> |
| +0xd8/+0xdc | `Leaves.Data / Num` (FBspLeaf, 0x14 B mem: iZone +0, iPermeating +4, iVolumetric +8, iExclusive(u64) +0xc) |
| +0xe4/+0xe8 | `Lights.Data / Num` (TArray<AActor*>) |
| +0xf0 | (probably `RootOutside`) |
| +0xfc | `NumSharedSides` |
| ≥+0x100 | likely `NumZones` + `FZoneProperties Zones[64]` (ZoneActor ptr, Connectivity u64, Visibility u64) — CONFIRM offsets if touched |

**FBspNode (in-memory, 0x40):** Plane +0 (4×f32), ZoneMask +0x10 (u64), iVertPool +0x18,
iSurf +0x1c, iChild[0] +0x20, iChild[1] +0x24 (**engine convention: side=1 = FRONT/positive
PlaneDot**), iPlane +0x28 (coplanar chain), iCollisionBound +0x2c, iRenderBound +0x30,
iZone[0]/[1] +0x34/+0x35 (BYTES), NumVertices +0x36 (byte), NodeFlags +0x37 (byte),
iLeaf[0]/[1] +0x38/+0x3c (i32; iLeaf[k] pairs with iChild[k]).
NodeFlags bits known: NF_NotCsg 0x01, NF_ShootThrough? 0x02, NF_?, 0x04 (portal/invisible-derived),
NF_IsNew 0x20. Report every flag constant you see tested/set (e.g. 0x08, 0x10, 0x40, 0x80).

**FBspSurf (in-memory, 0x40):** Texture +0, iBrushPoly? ... — exact mem order NOT yet pinned;
report raw offsets you see. Known: portalize resets `surf+0x18 = -1` per surf (likely iLightMap).
PolyFlags is a u32 in the low fields — `PF_Portal = 0x04000000`, `PF_NotSolid = 0x08`,
`PF_Semisolid = 0x20`, `PF_Invisible = 0x01`.

**FPoly (in-memory, 0x1d8; editor working polygon, up to 32 verts):** Base +0, Normal +0xc,
TextureU +0x18, TextureV +0x24, Vertex[0..31] +0x30 (12 B each, ends +0x1b0),
PolyFlags +0x1b0, then Actor/Texture/ItemName/iLink/iLinkSurf/NumVertices/iBrushPoly in
+0x1b4..+0x1d4 — exact slots per `sections/10-bsp-csg-build.md` §0.1: NumVertices observed at
+0x1c0, a link/plane-index field at +0x1c8. Report raw offsets.

**FEditorVisibility (`this` = esi in the passes; ~0x10060 bytes, stack-allocated):**
| off | meaning (from TestVisibility/portalize top-level decode) |
|---|---|
| +0xc | `ULevel* Level` (Level: Actors.Data +0x2c, Actors.Num +0x30) |
| +0x10 | `UModel* Model` |
| +0x10014 | portal count (the "%i portals" of the Portalized log) |
| +0x10034 / +0x10038 | zone-portal count / fragment count (the "%i zone portals (%i fragments)") |
| +0x1004c | FMemStack array, `Nodes.Num*2 + 0x100` × 4-byte entries |
| +0x10050 / +0x10054 | FMemStack arrays, one 4-byte entry PER LEAF (`Leaves.Num`) |
| middle ~0x10000 bytes | unknown big scratch (probably portal/poly pool) — map what you can |

## The decoded portalize skeleton (context — already established)

`UEditorEngine::TestVisibility(Level, Model, A, B)` @0xaa940: if `Nodes.Num`, constructs
FEditorVisibility (ctor 0xa6970(Level, Model, A)), calls portalize 0xaa370, dtor 0xa6c70.

`portalize` @0xaa370 (esi = this):
1. BeginSlowTask(L"Zoning").
2. For every node: `iLeaf[0..1] = -1`, `iZone[0..1] = 0`.
3. For every surf: `surf+0x18 = -1`.
4. Empty `Model.Leaves` and `Model.Lights`.
5. `0xa7760(this, 0, Model->+0xf0)`  ← pass A
6. Alloc this+0x10050 and this+0x10054 (one INT per leaf → leaves EXIST after pass A),
   this+0x1004c (2×Nodes.Num+0x100).
7. `0xa9750(this, 0)`  ← pass B
8. `0xa93c0(this)`  ← pass C — logs "Found %i zones"
9. `0xa7400(this, 0, Model->+0xf0)`  ← pass D
10. `GEditor->bspCleanup(Model)`; `bspRefresh(Model, 1)`; `bspBuildBounds(Model)`.
11. `0xa8850(Model, 0)`  ← pass E (cdecl, 2 args)
12. `0xa7960(this)`  ← pass F
13. `0xa7e60(this)`  ← pass G
14. debugf(L"Portalized: %i portals, %i zone portals (%i fragments), %i leaves, %i nodes",
    this+0x10014, this+0x10034, this+0x10038, Leaves.Num, Nodes.Num).
15. Per-LIGHT visibility: for each Level actor with `actor+0x19c != 0` AND `actor+0x28 & 5`:
    `0xa6d00(this, actor, -1, 0)` (pass 1 logs L"Lightsource %s: %i leaves"; slow-task
    L"Illumination occluding"). Then for each leaf: if `this+0x10054[iLeaf]` non-null,
    `leaf.iPermeating = Lights.Num` then append the linked-list values + a 0 terminator to
    `Model.Lights`.
16. Volumetric: reset this+0x10054 to 0; for each actor with `actor+0x88 != 0` (its +0x27c & 2),
    `+0x19c != 0`, `+0x1a6 != 0`, `+0x1a5 != 0`, `+0x28 & 5`: `0xa9290(this, actor, 0, 0, 0)`;
    then same per-leaf fill into `leaf.iVolumetric`.
17. EndSlowTask.

Function extents (next-function boundaries): 0xa6970(ctor)→0xa6c70(dtor)→0xa6d00→0xa7400→
0xa7760→0xa7960→0xa7e60→0xa8850→0xa9290→0xa93c0→0xa9750→0xaa370. Helpers below 0xa6970 (e.g.
0x31450, 0x3xxxx) and any callee you encounter: chase it if it's load-bearing for semantics.

## Cross-reference (READ THESE FIRST)

- `dev/docs/spikes/2026-07-15-native-materialize/sections/10-bsp-csg-build.md` §8 (the old
  skeleton — some inferences there are now corrected by the skeleton above), §0 (FPoly layout).
- `sections/50-model-ondisk-layout-and-render.md` §1 (FBspNode serial layout).
- `sections/60-leaf-solidity-collision.md` §2 (front/back convention, IsCsg).
- UE1 background: this is the classic `FEditorVisibility` zoning pass (UnVisi.cpp lineage —
  portals from BSP, leaf enumeration, zone flood, zone masks, per-light leaf visibility). Public
  source for it is NOT available; the binary is ground truth. Do NOT invent semantics from
  training memory — every claim must be anchored to instructions you quote.

## Required output format (write to your assigned file)

For EACH function: (1) its role in one sentence; (2) faithful pseudo-C with real struct field
names where the offset table above names them, raw `+0xNN` otherwise; (3) every constant/
threshold with the raw instruction quoted; (4) every write to Model/node/leaf/surf/zone state
(THE key deliverable — what does this pass PRODUCE); (5) callees with RVAs and what they do;
(6) open questions / low-confidence spots clearly marked. Quote key instruction runs (address +
asm) as evidence for each load-bearing claim. Be exhaustive; this feeds a native Rust port that
must match membership-for-membership on real maps.
