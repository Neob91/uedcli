# Spike: build a shipped-quality `.dx` with no UnrealEd at all (2026-08-26)

**Question.** `level materialize` builds a map by driving UnrealEd in a container: it assembles an
*unbuilt* package (actors + brush polys, empty world BSP), `MAP LOAD`s it, and lets the editor's
`MAP REBUILD` carve the world BSP and `LIGHT APPLY` bake lighting. The Rust CSG core
(`uedcli_native.build_geometry_bspcsg`) already reproduces the editor's BSP. Can we skip the editor
entirely — carve in-process, write the built Model into the package ourselves, and have the *game*
load it?

## TL;DR — yes, for geometry. The game loads and renders a fully natively built UNATCO.

`UEDCLI_NATIVE_MATERIALIZE=1 bin/uedcli … level materialize --tree level/unatco --out unatco.dx`
produces a 1.94 MB `.dx` in **20 s** with no container in the path at any point — no editor process,
no `MAP LOAD`, no `MAP REBUILD`, no `LIGHT APPLY`. `level preview --game` (the game client,
`DeusEx.exe`, a different binary from the editor) loads it and renders the real geometry with the
real textures: `evidence/unatco-pathnode213-in-game.png`.

Reproduce from the repo root:
`dev/docs/spikes/2026-08-26-editor-free-native-materialize/harness/build-and-preview.sh <project> unatco <out-dir>`.

## How the pieces join

1. `native.materialize.build_world_model(level, index)` — the trunk's world-CSG brushes (movers and
   the builder brush excluded, exactly as the editor's `csgRebuild` excludes them) go through
   `uedcli_native.build_geometry_bspcsg` → `serialize_model` → `umodel.parse_model_body`.
2. `native.unbuilt.assemble_unbuilt(…, world_model=, csg_brushes=, zone_actors=)` writes that Model
   into the package's world Model export instead of the empty one. Two things the CSG core cannot
   know are patched in during assembly: each surf's `iActor` (a raw brush index out of the build)
   becomes the owning brush actor's export ref, and its `texture_ref` (always 0 out of the build)
   resolves through the same texture resolver the brush polys use.
3. `apply._materialize_native` orchestrates it and post-verifies the written `.dx` offline with the
   same `verify_dx_matches` the editor path runs.

Measured on the 1437-actor UNATCO trunk: CSG build 3.5 s, assembly 2.1 s, 1.94 MB. The written
package's world Model reads back identical to what the build produced — 6314 nodes / 3616 surfs /
10758 points / 66037 verts / 762 leaves / 7 zones — and all 3616 surfs carry a resolved texture
import and an owning-brush export ref.

## The self-package rewrite is what made the difference between a map and an empty file

The first attempt produced a map the game refused: `Can't import private object Teleporter
03_NYC_UNATCOHQ.Teleporter0` → `Failed to load 'Level None.MyLevel'`. A trunk imported from a
shipped map keeps its intra-level refs qualified with the ORIGINAL package name, and assembly counts
a ref as internal only when it reads `MyLevel.`; anything else becomes a package import the engine
rejects, aborting the whole level load. That rewrite used to live in `apply._materialize`, so every
other caller of `assemble_unbuilt` silently produced an unloadable map. It now lives in
`assemble_unbuilt` itself (`rewrite_self_package_refs`), pinned by
`test_native_roundtrip.py::test_assemble_rewrites_the_levels_own_package_refs_to_mylevel`.

## What this path still cannot do

- **No lighting.** Nothing bakes lightmaps offline, so every surface renders fullbright.
- **No mover geometry.** Only `MAP REBUILD` builds a mover's private brush model
  (`csgPrepMovingBrush`); UNATCO's 28 `DeusExMover`s ship as actors with polys but no BSP. The build
  warns naming them and continues. Board: `native-geometry-path-leaves-mover-models-unbuilt`.
- **No mesh actors draw.** The native leaf/zone pass marks ~2× the solid leaf slots the editor does,
  so ~60 % of point actors `PointRegion`-resolve into solid space and the game's actor lighting
  faults. Board: `native-bsp-leaf-assignment-marks-2x-the-solid` (p1).

Those three are why `UEDCLI_NATIVE_MATERIALIZE=1` is an undocumented env gate rather than a CLI
flag. Board: `editor-free-native-world-bsp-map-assembly`.
