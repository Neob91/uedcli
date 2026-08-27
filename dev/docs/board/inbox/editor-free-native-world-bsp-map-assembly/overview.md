+++
priority = "p2"
kind = "implement"
summary = "level materialize can build a whole .dx with no UnrealEd, behind the temporary UEDCLI_NATIVE_MATERIALIZE=1 gate. It needs a real home (a CLI flag) once lighting and mover geometry exist."
spikes = ["dev/docs/spikes/2026-08-26-editor-free-native-materialize/"]
+++

# Editor-free map assembly — actors + a natively built world BSP, no UnrealEd

Demonstrated end to end on the real UNATCO map: a complete `.dx` written from the T3D trunk with
**no UnrealEd process of any kind** — no `MAP LOAD`, no `MAP REBUILD`, no `LIGHT APPLY`, no editor
container. The game client (`DeusEx.exe`) loads and renders it. Spike:
`dev/docs/spikes/2026-08-26-editor-free-native-materialize/`.

## What landed

- `native/materialize.build_world_model(level, index)` — CSG-ordered brushes (movers and the
  builder brush excluded, as `csgRebuild` excludes them) → `uedcli_native.build_geometry_bspcsg`
  → `serialize_model` → `umodel.parse_model_body`. Plus `resolve_zone_actors`.
- `native/unbuilt.assemble_unbuilt(..., world_model=, csg_brushes=, zone_actors=)` — writes that
  Model into the package's world Model export instead of the empty one, rewriting each surf's
  `iActor` to the owning brush's export ref and its `texture_ref` through the same texture resolver
  the brush polys use.
- `native/unbuilt.rewrite_self_package_refs` — the self-package rewrite, moved out of
  `apply._materialize` so EVERY caller of `assemble_unbuilt` gets it (see below).
- `apply._materialize_native` — the whole editor-free build, gated on `UEDCLI_NATIVE_MATERIALIZE=1`.
  It post-verifies the written `.dx` with the same offline `verify_dx_matches` the editor path runs,
  prints exactly what that did and did not cover, and runs the offline half of the advisory BSP
  health check (`bsp.checks.run_offline_bsp_checks`; the editor-rebuild-warning half cannot apply,
  since no editor ran). Movers WARN and continue.
- Regressions in `test_native_roundtrip.py` (world model written with real refs; empty without it;
  the self-package rewrite) and `test_materialize_verb.py` (the gate routes around the editor
  entirely; without it the editor path still runs).

## The gate is temporary and deliberately not a flag

`UEDCLI_NATIVE_MATERIALIZE=1` is an env var, absent from `--help` and `docs/usage.md` (owner,
2026-08-26). The maps it produces are incomplete by construction — no lighting, no mover geometry,
no mesh actors — so it is scaffolding for the native-engine work, not something to offer a user. It
graduates to a real CLI flag once `native-geometry-path-leaves-mover-models-unbuilt` is closed and
something bakes lighting offline (`native-build-has-no-lighting-so-no-mesh-actor`). That flag has
not been designed.

## Measured on UNATCO (1437-actor trunk)

Native CSG build 3.5 s, assembly 2.1 s, 1.94 MB `.dx`, ~20 s wall for the whole verb, no container
anywhere. The written package's world Model, read back: 6314 nodes / 3616 surfs / 10758 points /
66037 verts / 762 leaves / 7 zones — identical to what `build_geometry_bspcsg` produced. All 3616
surfs carry a resolved texture import and an owning-brush export ref.

## The self-package rewrite is NOT optional

The first attempt produced a map the game refused: `Can't import private object Teleporter
03_NYC_UNATCOHQ.Teleporter0` → `Failed to load 'Level None.MyLevel'`. A trunk imported from a
retail map keeps intra-level refs qualified with the ORIGINAL package name, and `assemble_unbuilt`
treats a ref as internal only when it reads `MyLevel.`; anything else becomes a package import the
engine rejects, aborting the whole level load. It lived in `apply._materialize`, so every
non-`apply` caller of `assemble_unbuilt` silently produced an unloadable map. It now lives in
`assemble_unbuilt`.

## Still open

- **No lighting.** Nothing bakes lightmaps offline (the Rust `light.rs` port was deleted with
  `fbccd70`), and the owner ruled the editor out for this too. Surfaces render fullbright.
- **Mesh actors do not draw**, and that is the missing lighting, proved by experiment — see
  `native-build-has-no-lighting-so-no-mesh-actor`.
- **Movers ship unbuilt** — see `native-geometry-path-leaves-mover-models-unbuilt`.
- **What the final interface is.** A `level materialize` flag, a separate verb, or library-only —
  the owner's call, once the three above are closed.
