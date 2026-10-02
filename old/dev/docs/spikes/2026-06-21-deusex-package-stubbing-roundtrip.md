# Spike — Deus Ex `.u` → UED22-loadable "stub" round-trip (2026-06-21)

Goal: pin down, **live**, whether (and how) a Deus Ex code package (`.u`, package
version 68) can be converted into a UED22-loadable version-69 package **without losing
its mesh assets** — the mechanism behind the hacky `Tools/recompile_for_ued2` prototype,
which we want to integrate into uedcli. Confidence: ✅ = live-verified this session.

All runs were in an isolated ephemeral container (`uned-spike-recompile`, an override-
entrypoint `dx-lum-uned:latest` with `/sdk`, `/deusex`, `/umodel` bind-mounts), never the
standing `dx-lum-uned` or any session editor.

## TL;DR — the round-trip works; every leg is live-validated

```
v68 .u ──batchexport class uc──▶ Classes/*.uc  (UnrealScript source, with #exec import dirs)
       ──batchexport texture pcx─▶ Textures/*.pcx
       ──umodel -export -uc──────▶ VertMesh/*_a.3d + *_d.3d  +  per-mesh .uc (MESHMAP SCALE)
  rewrite #exec import paths (MESH→Models\X_a/_d.3d, TEXTURE→Textures\X.pcx, MESHMAP SCALE)
       ──UED22 UCC.exe make──────▶ v69 .u  (mesh + texture data re-imported, baked in)
```

Proven end-to-end: a real DeusEx mesh (`WineBottle` from `DeusExItems.u`) went
v68→decompile→umodel→`make`→**v69 package with the mesh present** (`Mesh LOD processing:
WineBottle` / `Success` / magic OK / `ver 69` / `b"WineBottle" in StubMesh.u`).

## The decisive finding: WHICH UCC decompiles

`recompile_for_ued2` calls `$system/UCC.exe batchexport`. Three UCCs were tested:

| UCC | `batchexport` available? | Loads v68 `.u`? | Verdict |
|---|---|---|---|
| **v68 Deus Ex SDK `UCC.exe`** (`DeusExSDK1112f`, Dec 2000) | ❌ "Commandlet batchexport not found" | n/a | The SDK ships **no `Editor.u`** — the editor is native, statically linked into `UnrealEd.exe` (`DXLibs.zip` → `Editor.lib`; `DxHeaders.zip` → `Editor/Inc/*`, `Core/Inc/UExporter.h`). The bare v68 toolset has **no script-export commandlet** (v68 `Core.u` carries only `HelloWorldCommandlet` + the base `Commandlet`; `BatchExport` appears in **no** DeusEx file — not the v68 `.u`, not `UCC.exe`/`UnrealEd.exe`/`Core.dll`/`Window.dll`, not any `.int`). |
| **v68 SDK `UnrealEd.exe`** | the GUI's "Export All" only | yes (native v68 engine) | Pure GUI app: `UnrealEd.exe batchexport …` exits 53 with no banner (ignores the commandlet arg); needs a display + menu driving. Not used. |
| **UED22 `UCC.exe`** (DeusEx-patched **v469** lineage; provides `Editor.BatchExportCommandlet`) | ✅ | ✅ **yes** — parses v68 format and resolves v68 imports **by name** against the loaded v69 packages | **This is the decompiler.** "DeusEx's UCC does it fine" = this DeusEx-patched v469 UCC, the one committed at `uned/UED22/UCC.exe`. |

So the decompiler is **UED22's UCC**, not the v68 SDK UCC. The reconciliation: `batchexport`
is a UT-era (v4xx) commandlet in `Editor.u`; Deus Ex (Unreal-1 era) predates it, so the
native v68 toolset can only export through the GUI editor — but the **v469 UCC reads the
older package format fine** and exports its source.

### What `batchexport` needs to succeed (the load-bearing constraints) ✅

1. **The target's full transitive dependency closure must be LOADABLE.** `batchexport class
   uc` fully loads the package, which means resolving every superclass and referenced object.
   - *Code* deps must be present as **v69** packages on `EditPackages` (UED22 already ships
     v69 `Core`/`Engine`/`DeusEx`/`DeusExItems`/`DeusExDeco`/…, so the recursion bottoms out
     on the committed substrate). `DeusExUI.u` (v68) → `Exported Class DeusExUI.AllUI …
     Success` once `DeusEx` etc. were on `EditPackages`.
   - *Content* deps (textures) must be on `[Core.System] Paths`. `DeusExItems`/`DeusExDeco`
     first failed `Can't find file for package 'Effects'` — **`Effects` is `Effects.utx` (a
     texture package), not code** — and decompiled cleanly once `/deusex/Textures/*.utx` was
     added to `Paths` (6 classes, full `#exec MESH IMPORT`/`MESHMAP SCALE`/`TEXTURE IMPORT`).
2. **Stripped-symbol failures are real and package-specific.** `Extension.u` (v68) failed
   `Can't find Function 'Engine.PlayerPawn.PostRenderFlash'` — that function was **stripped
   from UED22's recompiled v69 `Engine.u`**. So a package that references a symbol absent from
   the (stripped) v69 deps cannot be batchexported until those deps are un-stripped. This is
   the **chicken-and-egg**: you can't un-strip `Engine` without first decompiling it, and you
   can't decompile a package needing an un-stripped `Engine`. Bootstrap escape: the major
   packages already exist as v69 in the committed substrate, so most targets resolve; the
   genuinely-blocked ones (needing un-stripped engine symbols) are a separate, flagged class.

## Leg evidence

- **Decompile (class):** `wine UED22/UCC.exe batchexport DeusExItems.u class uc Z:\… -ini=…`
  → 6 classes, e.g. `AllPickups.uc` with
  `#exec MESH IMPORT MESH=GEPAmmo ANIVFILE=Models\gep_ammo_a.3d DATAFILE=Models\gep_ammo_d.3d`.
- **Decompile (texture):** `batchexport DeusExItems.u texture pcx …` → 185 `.pcx`. NOTE: names
  carry the **group prefix** (`Skins.GEPAmmoTex1.pcx`) whereas `#exec TEXTURE IMPORT
  NAME=GEPAmmoTex1` wants `Textures\GEPAmmoTex1.pcx` — a filename-normalization step the
  pipeline must handle (the prototype's `update_texture_imports` rewrites FILE to
  `Textures\<NAME>.pcx`).
- **Why meshes need umodel, NOT UCC (re-verified live 2026-06-22):** `UCC has NO mesh
  exporter` — `UED22/UCC.exe batchexport DeusExItems mesh 3d` (and `_3d`/`uc`) returns
  `No 3d exporter found for LodMesh DeusExItems.<Mesh>` for every mesh and writes zero files
  (`Success`, but nothing exported). This is not a v68 quirk — UCC simply ships no
  mesh→file exporter, so meshes can only come out via umodel (or the GUI editor). The class and
  texture legs, by contrast, DO export from the v68 file via UED22 UCC: re-confirmed by
  temporarily hiding the v69 substrate `DeusExItems.u` and re-running — `batchexport class uc`
  still produced all 6 classes and `batchexport texture pcx` still produced 185 `.pcx`
  (`Success`), proving UED22 UCC genuinely loads+exports the **version-68** package (`Ver: 68`),
  not the hidden v69 copy.
- **Meshes (umodel):** `wine umodel.exe -path=Z:\…\dxsys -export -uc -out=Z:\… DeusExItems`
  → 314 VertMesh `.3d` (`<Mesh>_a.3d`/`<Mesh>_d.3d`) + 157 per-mesh `.uc` carrying the
  **authoritative** `#exec MESHMAP SCALE` (e.g. `WineBottle X=0.0316704 …`). umodel has
  explicit **DeusEx VertMesh support** and reads the v68 package directly (no editor). For
  `DeusExDeco`: 356 meshes + 323 textures in 0.3 s.
- **Recompile (mesh import):** a minimal `class StubWine extends Decoration` with the
  `WineBottle` mesh `#exec` + the umodel `.3d` pair in `../StubMesh/Models/`, `EditPackages =
  Core,Engine,StubMesh`, `UCC.exe make` →
  `Mesh LOD processing: WineBottle` / `Compiling StubWine` / `Success - 0 error(s)` →
  `StubMesh.u`, magic OK, **ver 69**, `b"WineBottle" in StubMesh.u`. Mesh preserved.
- **Recompile (sanity):** `class SpikeThing extends Decoration` (no assets) → `SpikeTest.u`
  ver 69. `UCC make` resolves a package's source from `../<Package>/Classes` (sibling of the
  exe dir); **`EditPackages` order is load-bearing** — a package must follow every dep
  (`Superclass Decoration … not found` when `StubMesh`/`SpikeTest` preceded `Engine`).

## Inputs needed (and where they came from)

- **v68 install** = `uned/DeusExAssets/` (gitignored). Its `System/*.u` are the v68 **code**
  inputs (and the umodel source); `Textures/*.utx` are the **content** deps for `Paths`.
  This copy was **incomplete** (17 `.u`, missing e.g. `Effects.utx` from `System` — but
  `Effects.utx` IS in `DeusExAssets/Textures`). A real/full install has the complete set.
- **v68 SDK** = `DeusExSDK1112f.exe` (free; `dev.dxgalaxy.org/downloads/DeusExSDK1112f.exe`,
  6,541,824 bytes, `sha256
  a54e16632820353725c59c70de5d32323c27a232ecc4b681290bce0b51a3eb28`; a **WinZip
  self-extractor** PE — a `_winzip_` zip section, NOT a "trailing 7z payload" as first written —
  `7z x` extracts it regardless → `ReleaseSDK1112f/`). Provides the v68 `UCC.exe`/`UnrealEd.exe`
  + `Editor.lib`/headers — **but turned out NOT to be the decompiler** (no `batchexport`);
  its value is documentary (it proves the v68 toolset has no export commandlet). **Re-fetched
  and re-verified 2026-06-22:** the entire SDK ships exactly two `.u` (`System/Core.u` +
  `System/test/Core.u`) and **no `Editor.*` at all** (not even an `Editor.dll` — the v68 editor
  is native, statically linked into `UnrealEd.exe`); `batchexport` occurs in **zero** SDK files
  (ASCII or wide); the SDK `Core.u`/`UCC.exe` know only `HelloWorldCommandlet` + the base
  `Core.Commandlet`. So the SDK definitively cannot decompile — settling the user's "the SDK
  should contain UCC" expectation: it does contain a UCC, but one with no export commandlet. The
  retail **installer** `deusex.ace` (multi-volume; `unace` extracts, the unregistered build's
  *listing* truncates but *extraction* works) holds the full install incl. `Effects.utx`.
- **umodel** = `Tools/umodel_win32/umodel.exe`.
- **recompiler** = `uned/UED22/UCC.exe` (the committed substrate; v469, v69 `Editor.u`).

## Implications for the spec

1. The decompiler is **UED22's own `UCC.exe`** — already in the substrate. No new external
   binary needed for decompile/recompile; only **umodel** must be added to the stub-build
   environment, and the **v68 install** must be present (gitignored, user-supplied — same
   rule as `DeusExAssets`).
2. Stubbing is **closure-ordered**: to stub `P`, first ensure every code dep of `P` is
   available as a v69 stub (recurse; bottoms out on the committed v69 substrate) and every
   content dep is on `Paths`. Reuses `dxpkg.transitive_closure`.
3. Mesh/texture preservation is via **umodel `.3d` + `batchexport` PCX**, re-imported by
   `#exec` during `make`. The `#exec` paths and (group-prefixed) texture filenames must be
   normalized — the `unrclsprs` regex munger's job, to be ported into uedcli proper.
4. A package that references **symbols stripped from the v69 deps** can't be stubbed yet —
   fail loudly and name the missing symbol; don't emit a broken stub.
5. Outputs are copyright-derived → cache **gitignored**, never committed.
