# De-containerize uedcli — eliminate Docker / wine / `.exe` dependencies

**Status: SPIKE PHASE COMPLETE (2026-06-27, autonomous run).** Feasibility is established
end-to-end (see Conclusion). 10 spikes + the `Model` serial-read completion + a reviewed
roadmap spec + 2 cold-reviewed Phase-A implementation specs (texture-sync, `.dx`-read).
**The entire native READ side is now reverse-engineered and validated** (textures, classes,
actor bodies, authored brush polys via `UPolys`/`FPoly`, the built `Model`) and the native
WRITE container is byte-exact. The remaining work is implementation, dominated by one long
pole (the offline CSG/BSP build, D2) — gated on Andrzej's scope decision (Q0 in the roadmap).

This is the umbrella record for an investigation into removing uedcli's entire
Docker + wine + Windows-`.exe` dependency stack, replacing each editor/UCC/umodel
operation with native pure-Python code. It is written for a reader with NO prior
context. Individual deep spikes live in sibling dated dirs and are linked from the
**Findings log** at the bottom; this file holds the thesis, the dependency map, and
the running progress so the effort survives a context reset.

---

## Conclusion (TL;DR)

De-containerization is **feasible**, and the investigation proved or de-risked everything
except one already-known long pole:

- **PROVEN native (no editor/UCC/umodel/wine):** texture decode (pixel-exact vs UCC, whole
  corpus), package-container write (byte-exact on real `.dx`), actor-body read+write
  (`StateFrame`+props, 3736/3736 objects), `.dx`→actor-list read, qualification, the
  built-`Model` serial read (byte-exact, 12/12 maps), AND authored brush polygons
  (`UPolys`/`FPoly`, 99% / 4 maps 100%). **The whole READ side is reverse-engineered;** Model
  write is the mechanical inverse of the proven read.
- **CONFIRMED hypothesis:** stubs exist for mesh-format (DeusEx `FMeshVert` = 8-byte int16
  vs Unreal 4-byte packed) + `Engine.u`/`Core.u` divergence, **not** v68/v69. Native write
  **deletes the entire stub pipeline** → `UCC.exe`, `umodel.exe`, ImageMagick all go.
- **THE ONE LONG POLE:** the offline CSG/BSP **build** (D2 — already specced in the repo)
  that *generates* the level `Model`. The game loads pre-built BSP and never CSG-rebuilds,
  so geometry must be built offline. *Second pole, downstream:* native lighting (a real
  lightmapper, ~1.7 MB lumels/map) — until then, an optional editor final-bake.
- **Net:** the day-to-day authoring loop can be container-free with Phase A/B (native
  reads + writer) + D2; 100% editor elimination additionally needs native lighting/paths.
  **The pivotal decision for Andrzej (Q0 in the roadmap spec):** commit to D2 (promote it
  from the `decisions.md` 12:40 "optional" status to required — the editor-based D0/D1 path
  can't serve an editor-free pipeline), or adopt an editor-`MAP REBUILD`-only-geometry
  intermediate. Roadmap + open questions: board item `de-containerize-uedcli-drop-docker-wine-exe`.

## Why (the ask)

The directive: *stop needing Docker / containers overall*, and specifically
*reverse-engineer texture (and mesh) extraction natively so we minimize dependency
on any `.exe` file*. Plus a hypothesis to test: the reason DeusEx packages need
"stubbing" is **not** the Unreal package version (v68 vs v69) — UED22's `UCC.exe`
already reads v68 fine (proven, decisions.md 2026-06-22). The real reasons are
(a) DeusEx stores a **different mesh format** than stock Unreal, and (b) DeusEx
depends on a **different `Engine.u`/`Core.u`** than the UT-lineage editor.

## The four binary dependencies (what Docker exists to run)

Everything containerized traces to four Windows binaries run under wine:

| Binary | uedcli uses it for | Native replacement |
|---|---|---|
| `unrealed.exe` (the editor) | materialize (FULL RE-IMPORT → `MAP SAVE` = the only `.dx` *writer*), CSG/BSP build (`MAP REBUILD`), lighting (`LIGHT APPLY`), paths (`PATHS DEFINE`), texture/class qualification (`OBJ DEPENDENCIES`/`OBJ LIST`), preview | **native package writer + offline BSP engine (D2) + native qualify + native light/paths (or defer)** |
| `UCC.exe` | offline `batchexport` (`.dx`→T3D, class→`.uc`, texture→PCX), `make` (recompile stubs) | **native T3D from package read; native texture decode; stubbing dies if editor dies** |
| `umodel.exe` | actor-mesh extraction (`_a.3d`/`_d.3d`) for stubbing | **native mesh decode; or moot if stubbing dies** |
| ImageMagick `convert` | PPM→PNG (preview), PCX→PNG (texture) | already host-side Pillow in most paths; trivially fully native |

## The thesis

**If uedcli writes the `.dx` natively, the editor disappears — and with it the
entire reason stubs exist.** Stubs convert v68 DeusEx code so the *UT-lineage UED22
editor* can load it; nothing else consumes a stub. Remove the editor from the
materialize loop (native CSG build + native package serializer) and:

- We never load DeusEx code into UED22 → **no stubs** (decompile/umodel/make all die).
- We read DeusEx packages (classes, properties, textures, meshes, BSP) **natively**
  from the real v68 install — already the established direction for property schema
  (decisions.md 2026-06-26 14:10: "parse the game's real `.u`, never the stub").
- `UCC.exe` (offline export) and `umodel.exe` (mesh) are replaced by native readers.
- Docker/wine/X11/VNC vanish (they exist only to host the GUI editor).

What's left that is genuinely editor-shaped: **lighting** and **pathnode reachspecs**
are *build output* (regenerable, never authored, never in the level hash — see
`t3d.md` "What T3D cannot carry"). Options: bake natively, ship unlit and let the
game build at load, or keep an optional editor pass purely for final lighting.
**Preview** likewise becomes a native renderer or an optional convenience.

## Native-replacement dependency graph (build order)

```
native package READ  (dxpkg + export-table reader)         [~DONE in spikes]
        │
        ├── native TEXTURE decode (UTexture/UPalette → PNG)  ← explicit ask  [SPIKE 1]
        ├── native MESH decode (LodMesh/AniMesh → geometry)  ← explicit ask  [SPIKE 2]
        ├── native QUALIFY (resolve Texture/Class → package, no OBJ DEPENDENCIES) [SPIKE 4]
        │
offline BSP/CSG build engine (D2)  [partial; partition heuristic CLEARED]
        │
native package WRITE (serialize names/imports/exports + Level/Model/actors) [SPIKE 3 — KEYSTONE]
        │
        ├── lighting: bake | defer | optional editor   [SPIKE 5]
        └── paths:    bake | defer                      [SPIKE 5]
        │
   STUBS BECOME UNNECESSARY  [SPIKE 6 — analysis]
        │
   DOCKER REMOVED
```

## Spike plan (each ends with a writeup + harness committed here)

1. **Native texture decode** — reverse-engineer UTexture/UPalette on-disk, decode a
   real `.utx` to PNG natively, validate vs UCC PCX ground truth. (explicit ask)
2. **Native mesh decode** — reverse-engineer the DeusEx mesh object format; confirm
   *how* it differs from stock Unreal; decode a real mesh, validate vs umodel.
3. **Native `.dx` writer feasibility** — what a loadable/playable `.dx` needs; gate
   on the offline BSP engine; minimal-viable-writer assessment. (keystone)
4. **Native qualification** — resolve bare `Texture=`/`Class=` to packages purely
   from our own package parsing + manifest (replace `OBJ DEPENDENCIES`/`OBJ LIST`).
5. **Lighting & paths disposition** — bake vs defer vs optional editor.
6. **Stub-elimination analysis** — prove (or refute) that native write kills stubs.
7. **Synthesis + roadmap spec** — the sequenced plan, risks, irreducible minimum.

Constraint honored: work sequentially/deeply, NOT a parallel fleet to fill time.

---

## Findings log (append as each spike resolves)

- **Spike 1 — native texture decode: RESOLVED ✅** (`01-native-texture-decode.md`).
  Pure-Python `UTexture`+`UPalette` decoder is **pixel-EXACT vs `UCC batchexport`**
  on the whole install corpus (v61/v68/v69), every texture `P8`, body-to-EOF clean.
  Removes the wine/UCC/PCX/ImageMagick texture seam entirely. One version quirk: the
  `FMipmap` `WidthOffset` int exists in v68/69, absent in v61. **`UCC.exe batchexport
  Texture` is now replaceable.**
- **Spike 2 — DeusEx mesh format: RESOLVED ✅** (`02-native-mesh-format.md`).
  Hypothesis CONFIRMED: DeusEx `FMeshVert` = **8 bytes (4× int16 X,Y,Z,pad)** vs
  stock Unreal's **4-byte packed** dword; umodel down-converts (rescaling). Verified
  on 178/178 `DeusExDeco.u` meshes. This is the *mesh* half of "why stub" (the
  UT-lineage editor expects packed verts) — a content-format problem, NOT a v68/v69
  problem. Native decode feasible (HIGH) but OFF the critical path (umodel only feeds
  stubbing, which the native-write thesis kills); worth it only for an optional mesh
  catalog / native preview.
- **Spike 3 — native `.dx` writer: container PROVEN ✅, BSP is the long pole**
  (`03-native-package-write.md`). The package container writer (header + name/import/
  export tables) reconstructs **byte-exact** across v61/v68/v69 and real `.dx` maps
  (`DeusEx.u` = 18431 exports). Layout + offset computation are mechanical. Actor
  bodies = inverse of the Spike-1 property reader (easy). **The single gating
  dependency for a *playable* native `.dx` is the built level `Model` (CSG/BSP), since
  the game loads pre-built BSP and never rebuilds at load — i.e. the offline BSP engine
  D2.** Net: *de-containerization and the offline BSP engine are the same long pole*;
  everything else around it is proven or mechanical. `MAP SAVE` is replaceable.
- **Spike 4 — native qualification: RESOLVED ✅** (`04-native-qualification.md`).
  Replaces `OBJ DEPENDENCIES`/`OBJ LIST CLASS`. Reading a `.dx`: its import table IS
  the qualification (143 textures/112 classes on `00_Intro.dx`, no editor). Authored:
  a `name→package` manifest index — over the whole install only 75/4219 texture names
  (1.8%) collide, classes 0; per-level even rarer, parity with the editor's contract.
- **Spike 5 — lighting & paths: RESOLVED (analysis)** (`05-lighting-and-paths.md`).
  Both are build output (not authored, not hashed) and come AFTER the BSP build.
  Lighting can't be skipped (map renders black without lightmaps); native lighting is
  the **second long pole** after D2, native paths a moderate follow-on. Recommend:
  baseline for iteration, an OPTIONAL editor final-bake for ship, native bake long-term.
  So the day-to-day loop is container-free; 100%% editor elimination needs native
  lighting+paths.
- **Spike 6 — stub elimination: RESOLVED (analysis) ✅** (`06-stub-elimination.md`).
  Native write KILLS the entire stub pipeline (`stub.py`/`uscript_rewrite`/cache + UCC
  `batchexport class`/`make` + umodel + the build container) — stubs exist only to load
  DeusEx code into the UT-lineage editor, which the native path never does. Confirms
  Andrzej's hypothesis: stubs are about Engine/Core divergence + mesh format, NOT
  v68/v69. **Net: UCC.exe, umodel.exe, ImageMagick all ELIMINATED; unrealed.exe reduced
  to an OPTIONAL final-bake (Spike 5).**
- **Spike 7 — native actor bodies: RESOLVED ✅** (`07-native-actor-bodies.md`).
  Characterized the actor body: optional `StateFrame` (when `RF_HasStack` 0x02000000) +
  tagged property list + class trailing. Reader parses **3736/3736** real objects in
  `00_Intro.dx` with **0 errors**; the property WRITER round-trips Byte/Bool/Int/Float/
  Name/Object/Struct. Closes the review-flagged "actor bodies unproven" gap — point-actor
  writing is now proven/characterized, not asserted.
- **`Model` serial-read COMPLETED ✅** (extends `../2026-06-25-umodel-serialize-format.md`).
  Applied the `0xa8` one-line fix; the parser now reads the level `Model` **byte-exact to
  EOF on 12/12 real maps** (up to 7.1 MB / 13k nodes). Closes the reviewer-flagged "Model
  serialization is an incomplete hidden second port" risk — the read format is DONE, the
  write is its mechanical inverse, so **the long pole narrows to D2 (the CSG build) alone**.
- **Spike 8 — native `.dx` → actor list: RESOLVED ✅** (`08-native-dx-read.md`).
  Composes Spikes 1/3/4/7 into a `.dx` → `Level`-model reader: `00_Intro.dx` → 1837 actors,
  0 parse errors, classes resolved, Locations sane. Replaces `store_export`'s `UCC
  batchexport Level T3D`. With texture decode + qualification, the whole "read a `.dx` into
  the model" surface is natively covered (no editor/UCC/wine).
- **Spike 9 — native textured preview: RESOLVED (data pipeline) ✅** (`09-native-textured-preview.md`).
  Every render input is natively available: geometry (Model read), texture (import-resolve +
  native decode — 119/119 on UNATCOHQ, 137/138 on 00_Intro, residual = myLevel embedded),
  UV vectors (200/200 valid). Only a standard rasterizer remains. Removes the editor's
  `level preview`/display role at the data level.
- **Spike 10 — decode `UPolys`/`FPoly` (authored brush polygons): RESOLVED ✅**
  (`10-native-upolys-fpoly.md`). The native-read prerequisite. Format decoded (disassembly +
  EOF): `UPolys`=None+INT Num+INT Max+Num×FPoly; `FPoly`=ci NumVertices+4 FVectors+verts+INT
  flags+ci Actor/Texture/ItemName/iLink/iBrushPoly+u16 PanU/PanV. EOF-clean on **6566/6587
  (99%)** UPolys across 8 maps (4 at 100%). `FPoly.Texture` qualifies via the import table —
  resolving the dx-read review's "per-poly texture not intrinsic" blocker. Unblocks native read.
