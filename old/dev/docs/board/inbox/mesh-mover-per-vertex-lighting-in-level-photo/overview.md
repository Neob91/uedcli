+++
priority = "p3"
kind = "unknown"
summary = "mesh/mover per-vertex lighting in level photo native"
+++

# mesh/mover per-vertex lighting in level photo native

Follow-on from `bake-lighting-into-level-photo-native` (world BSP surfaces), scoped out 2026-09-11
by owner ruling. Real UE1 lights mesh/mover actors by sampling nearby lights per-vertex at the
actor's position at runtime — a separate mechanism from world lightmapping, no lightmap involved.
Needs its own RE effort. Meshes/movers currently stay flat-shaded in `level photo --native` even
after the world-lighting work lands.
