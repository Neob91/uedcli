+++
priority = "p1"
kind = "implement"
summary = "Proved by a controlled experiment: an empty Model.LightMap/LightBits/Lights is the sole reason the editor-free build draws no mesh actors. Nothing short of baking lighting fixes it."
spikes = ["dev/docs/spikes/2026-08-26-editor-free-native-materialize/"]
+++

# The editor-free build draws no mesh actors because it bakes no lighting

`UEDCLI_NATIVE_MATERIALIZE=1` maps render their BSP surfaces correctly but no mesh actor at all —
no plants, chairs or NPCs — and `DeusEx.log` fills with a per-frame critical stack:

```
Log: Anomalous singularity in URender::DrawWorld
Critical: FLightManager::SetupForActor
Critical: URender::DrawLodMesh
Critical: (LodMesh DeusExItems.WeaponMod)
Critical: DrawMesh
Critical: URender::DrawActorSprite
Critical: URender::DrawFrame
```

Two candidate causes were confounded: the (now fixed, exact-parity)
`native-bsp-leaf-assignment-marks-2x-the-solid` leaf/zone defect, and the total absence of lighting.
The leaf fix changed nothing about this symptom, and a controlled experiment settles it.

## The experiment

`harness/strip_lighting.py` parses a built `.dx`, empties `Model.LightMap` / `Model.LightBits` /
`Model.Lights`, sets every `FBspSurf.iLightMap = -1`, and repacks the package — nothing else
touched. `--keep-lighting` runs the identical parse/re-serialize/repack with the lighting left
alone, as the control. Three UNATCO maps, ONE camera (`at:200,620,340;rot:0,16384`), the same warm
game container in one boot, distinguished in the log by their content-hash package names:

| map | leaves | lighting | meshes draw | `SetupForActor` criticals |
|-------------------------------|---------|----------|-------------|---------------------------|
| editor `MAP REBUILD` + round trip (control) | correct | present | yes | 0 |
| editor build, lighting stripped | correct | absent | **no** | yes, from the frame it loads |
| native build (post leaf fix) | correct | absent | **no** | yes |

The control and the stripped map differ in nothing but the lighting arrays, and the stripped map
reproduces the native symptom exactly, critical stack included. So: absent lighting alone is
sufficient, and the leaf/zone assignment is not involved.

## What that means

There is no workaround. `FLightManager::SetupForActor` is reached for any actor whose
`Region.iLeaf != -1` (`Render.dll 0x10b08e51` skips the whole lighting path when it IS -1), so
FIXING the leaves *increases* the number of actors that take the faulting path. The editor-free
path cannot draw mesh actors until something bakes `Model.LightMap`/`LightBits`/`Lights` offline —
the Rust `light.rs` port deleted with `fbccd70`, and the owner ruled the editor out for this too.

Not established, and not needed for the conclusion: which exact dereference inside
`SetupForActor` faults. Only two `appFailAssert` sites exist in the function, both
`Actors(0)`-related and near the entry, so the fault is a memory access, not a checked assert.

Blocks the `UEDCLI_NATIVE_MATERIALIZE=1` gate becoming a real CLI flag
(`editor-free-native-world-bsp-map-assembly`).
