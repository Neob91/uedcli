+++
priority = "p2"
kind = "implement"
summary = "Meshes in solid space no longer render (photo + GUI)."
+++

# Meshes in solid space render in photo and GUI

DONE: `build_scene` skips a mesh actor whose Location resolves to a solid BSP leaf (`_model_point_region` i_leaf<0) — fixes `level photo --native` and the GUI. Regression `test_mesh_in_solid_space_is_not_rendered`. Merged `33ded5f3`.
