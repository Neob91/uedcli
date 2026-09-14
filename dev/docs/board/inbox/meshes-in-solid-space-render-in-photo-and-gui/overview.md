+++
priority = "p2"
kind = "implement"
summary = "Mesh actors sitting in solid (non-zone) space are drawn by build_scene — wrong in both photo and the GUI."
+++

# Meshes in solid space render in photo and GUI

Owner finding (2026-09-14): a mesh actor whose location is inside SOLID space (carved out of no
subtract — a non-zone leaf) should not render at all. `preview_native.build_scene` currently emits
every mesh actor's triangles regardless of whether the actor sits in solid or open space, so a mesh
buried in solid geometry shows through in `level photo --native` AND in the GUI viewport (which draws
`build_scene`'s polys). The real engine does not draw actors in solid leaves.

Fix in the native path (`build_scene`/mesh emission), so BOTH photo and GUI are corrected by one
change (the GUI consumes `build_scene`'s output). Use the existing point-region / leaf descent (the
same `pointRegion`/`FPlane::PlaneDot` machinery `resolve_zone`/the region code already have) to test
each mesh actor's location (or bounds) against the solved world BSP; skip emitting the mesh when it
resolves to a solid leaf.

Scope check: confirm the exact rule against the engine — is it the actor's Location point-region, or
bounds overlap, and does UnrealEd cull the whole actor or clip per-poly? Read `dev/docs/unrealed/`
(BSP/zone/region) before deciding the test. Pin with a regression (a mesh placed in solid space is
absent from `build_scene`'s polys; one in open space is present).
