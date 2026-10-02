+++
priority = "p1"
kind = "implement"
summary = "native photo scene cache: geometry/lighting split, landed"
+++

# native photo scene cache: geometry/lighting split, landed

`level photo --native`'s `build_scene` now caches under `.uedcli/preview/`: an unchanged level
reuses the fully-lit scene outright, a light-only edit reuses the CSG solve (`uedcli_native.
load_model`/`leaf_portals`) and only reruns the lighting bake. Went through spec review (found +
fixed a `leaf_portals`-staleness lighting bug and a brush/light-actor hash-split misclassification),
plan review (added a missing regression test for the misclassification fix), and a final diff
review (converted a `load_model` cache-incompatibility crash into a clean rebuild-as-miss). Follow-
up (out of scope): board item `csg-checkpoint-resume-in-native-bsp-core-for`.
