+++
priority = "p3"
kind = "debug"
summary = "hanging mesh actors render low: PrePivot class default not applied"
+++

# hanging mesh actors render low: PrePivot class default not applied

`DeusEx.HKHangingPig`/`HangingChicken` (and other `Hanging*` decoration classes) rendered 16-32uu
too low in the GUI. `Origin`/`RotOrigin` were suspected (a per-mesh-asset offset) but were already
correctly wired (`uedcli/meshworld.py`). Real cause: these classes ship a non-zero class-default
`PrePivot.Z` (47/31.68/13/11/39.45uu across the `Hanging*` family) that no placed instance states
explicitly — UnrealEd's T3D export omits a property equal to its class default. `rotation.
actor_prepivot` only ever scanned the actor's OWN instance props, never the class-default chain, so
it silently read PrePivot as zero for every actor relying on a class default.

Fixed: `actor_prepivot` takes an optional `class_defaults` map and falls back to `("prepivot", 0)`
when the instance is silent; threaded through `meshworld.mesh_actor_translation`/
`mesh_vertex_to_world` and `preview_native._mesh_actor_polys`/`build_scene` (the GUI/native-preview
mesh path). Confirmed against the real committed `uned/UED22` corpus (`class show
DeusEx.HKHangingPig`/`HangingChicken` before the fix already showed the non-zero class default;
their placed T3D instances in `showcase_wanchai_market` state no `PrePivot` at all). Regression:
`uedcli/tests/test_rotation.py::test_actor_prepivot_falls_back_to_class_default_when_instance_is_silent`,
`uedcli/tests/test_meshworld.py::test_prepivot_falls_back_to_class_default_for_hanging_meshes`.

Other `actor_prepivot` call sites (brush/mover CSG measurement, texture alignment, query/writes) are
UNCHANGED — brush `PrePivot` is always explicit per-instance in practice, so this gap doesn't reach
them; not audited further here.
