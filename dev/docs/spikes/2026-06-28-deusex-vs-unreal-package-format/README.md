# Spike: is the Deus Ex package format different from Unreal's? Is v68/v69 a compatibility gate?

**Date:** 2026-06-28 · **Status:** RESOLVED · **Confidence:** ✅ (offline byte-level
verification against the real install + the UT-lineage editor substrate)

## The question (Andrzej)

> Are Deus Ex packages fully compatible with Unreal packages? AFAIK they are — the
> DeusEx packages just depend on Deus Ex's `Engine.u`/`Core.u`, which makes them not
> work with the Unreal equivalent. The v68/v69 version number is a red herring. Verify.

## Verdict: the hypothesis is CONFIRMED

The package **binary format is the same** across stock Unreal/UT (UnrealEngine 1) and
Deus Ex; **the v68-vs-v69 version number gates nothing at the format level.** The actual
reason a Deus Ex *code* package won't load into the UT-lineage UED22 editor is
**class-graph divergence** (it links against a DeusEx-flavored `Engine`/`Core` whose
classes, properties, and native functions differ from UT's) plus a **mesh-format
difference** — not the version field.

This is not a new discovery; it was already established piecemeal (see "Prior evidence"
below). This spike's contribution is a **single consolidated, independently re-verified
answer** with a committed harness, because the fact was scattered and hard to find.

## What was verified (`verify.py`, offline, reads bytes directly)

Run from `Tools/uedcli` with `.venv-uedcli/bin/python`. Inputs: the real Deus Ex install
(`uned/DeusExAssets/System/*.u`, v68 game code) and the committed UT-lineage UED22 editor
substrate (`uned/UED22/*.u`, the v69 editor).

1. **Same magic, every version.** Every `.u`/`.dx`/`.utx` package — v61, v68, v69 alike —
   begins with the identical UnrealEngine-1 magic `0x9E2A83C1`. There is no "Deus Ex
   magic" vs "Unreal magic".

2. **v68 and v69 are byte-identically structured.** `dxpkg.parse_header` reads both the
   v68 `DeusEx.u` (11293 names, 3151 imports) and the v69 `DeusEx.u` (7017 names, 1952
   imports) through the **same `ver>=64` code path** with no version-specific branch. Only
   v61 (five old content packages) uses a different name-table encoding. So 68→69 is a
   minor bump that does not change the header, name-table, or import-table layout uedcli
   parses.

3. **The decisive fact — the v69 editor ships and loads v68 packages directly.** The
   UED22 substrate (the UT-lineage **v69** editor's own committed code) contains
   **7 version-68 packages** alongside 25 version-69 ones. `ConSys.u` in `uned/UED22/` is
   itself version 68. A "v69 editor can't load v68" rule is therefore false by the
   editor's own substrate.

   ```
   UED22 (UT-lineage v69 editor substrate):  version 68: 7 packages   version 69: 25 packages
   Deus Ex install (real game):              version 68: 17 packages
   ```

4. **The real load blocker is the class graph.** `DeusEx.u`'s import table names `Core`
   and `Engine` as the packages its classes inherit from / call into. Those symbols are
   resolved by NAME against whatever `Engine.u`/`Core.u` the editor has loaded. UT's
   `Engine`/`Core` differ from Deus Ex's, so a Deus Ex class referencing a DeusEx-only
   engine symbol fails to link — regardless of the version number on either file.

## The asymmetry worth stating

The version number is a red herring in **both** directions, but for different artifacts:

- **Code packages (`DeusEx.u`, `DeusExItems.u`, …):** won't load into the UT-lineage
  UED22 editor — but because of Engine/Core class-graph divergence + the mesh format
  (`FMeshVert` is 8-byte int16 in Deus Ex vs 4-byte packed in stock Unreal), **not** the
  version. This is the entire reason the "stubbing" pipeline exists (it strips DeusEx code
  bodies so the v469 UCC can link them against UT's DLLs). Native read/write deletes that
  pipeline; it never needed a version conversion.

- **Map/level packages (`.dx`):** a map authored and saved by the **v69** UED22 editor
  loads fine in the **v68** Deus Ex game. A `.dx` carries geometry + actor references by
  name; it does not re-link the engine class graph. When a UED22-authored `.dx` *did* fail
  to spawn in the game, the cause was 100% missing CSG/BSP (the brush had entered via
  `MAP IMPORTADD`, which skips CSG, leaving the world solid), confirmed by rebuilding via
  `EDIT PASTE` (68 BSP nodes) → loaded → spawned in-game first try. Nothing to do with
  v68 vs v69. (See `quirks.md` "How brushes enter the level".)

## Prior evidence this consolidates

- `spikes/2026-06-27-decontainerize-uedcli/06-stub-elimination.md` — "the two real
  reasons — neither is v68/v69": Engine/Core divergence + mesh format.
- `decisions.md` 2026-06-22 — UED22's v469 UCC was forced to a genuine `Ver: 68` load
  (by hiding the v69 substrate copy) and exported v68 classes + textures fine.
- `decisions.md` 2026-06-27 — "The stub rationale is mesh-format + `Engine.u`/`Core.u`
  divergence, NOT package version v68-vs-v69."
- `unrealed/quirks.md` "How brushes enter the level" — the v69 `.dx` loaded in the v68
  game; the spawn failure was missing CSG, "the v68/v69 version gap is a red herring".

## Durable home

The consolidated, findable answer now lives at
[`../../unrealed/package-format.md`](../../unrealed/package-format.md). This spike is the
evidence + the re-runnable harness (`verify.py`).
