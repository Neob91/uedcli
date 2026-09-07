# Mesh actor world-space vertex placement (UE1 `UMesh::GetFrame`)

How a `Mesh`/`LodMesh` actor's raw vertices become world-space geometry — the mesh's own `Scale`/
`Origin`/`RotOrigin` composed with the actor's `Location`/`Rotation`/`PrePivot`/`DrawScale`. Needed
by anything that places mesh geometry in world space outside the real renderer (a native mesh
rasterizer, a bbox/collision computation, a diagram overlay).

```
world = Location + PrePivot + R · Ro · diag(Scale · DrawScale) · (v − Origin)
```

- `v` — the raw mesh-local vertex (`FMeshVert`, `uedcli/umesh.py`)
- `Origin`, `Scale` — the MESH's own `UMesh` fields; `v` is shifted by `Origin` first, then scaled
- `RotOrigin` → `Ro` — the mesh's own rotation (3×3 via `uedcli/rotation.py`'s
  `euler_to_matrix_uu`), applied to the mesh in its own local frame
- `DrawScale` — the ACTOR's uniform scalar, multiplying all three `Scale` axes alike (not a
  separate `DrawScale3D` — UE1/Deus Ex has no such field)
- `Rotation` → `R` — the actor's own rotation, same `euler_to_matrix_uu` convention, applied
  OUTSIDE `Ro` (mesh reorients locally first, then the whole thing is placed in the world)
- `Location`, `PrePivot` — added last, as one combined UNROTATED world-space offset

✅ source: derived from `UMesh::GetFrame` (`Source/Engine/Src/UnMesh.cpp`, the `fgsfdsfgs/UE1` v200
retail mirror — same source already used for `unrealed/quirks.md`-adjacent sprite/radii facts, see
`dev/docs/spikes/2026-07-21-unrealed-sprite-radii-rendering.md`):

```cpp
Coords = Coords * (Owner->Location + Owner->PrePivot) * Owner->Rotation * RotOrigin
                 * FScale(Scale * DrawScale, 0.0, SHEER_None);
...
*ResultVerts = (CachedVerts[i] - Origin).TransformPointBy(Coords);
```

`R`/`Ro` use the identical FRotator→matrix convention as `rotation.py` (`Rz(yaw)·Ry(pitch)·Rx(roll)`,
pitch/roll sin-flipped, `spikes/2026-06-19-frotator-convention.md`) — re-deriving each of
`UnMath.h`'s three `FCoords::operator*=(FRotator)` step matrices as their inverse reproduces
`rotation._rx_uu`/`_ry_uu`/`_rz_uu` term for term. Full derivation (the `FCoords` composition
algebra, why it telescopes to a plain affine map, and the live-render cross-check):
`dev/docs/spikes/2026-09-07-mesh-origin-rotorigin-transform/`.

## PrePivot: a DIFFERENT convention from brushes for the same field

This is NOT `Location + R·(v − PrePivot)` — the brush/CSG convention (`architecture.md` "D8"),
where `PrePivot` sits INSIDE the rotation (the pivot the actor rotates about). For mesh rendering,
`PrePivot` is added to `Location` as a plain, UNROTATED world-space offset. `AActor::ToWorld()`
(`AActor.h`) has no `PrePivot` term at all (`GMath.UnitCoords * Location * Rotation`) — each
subsystem that needs `PrePivot` folds it in itself, and mesh rendering and brush/CSG disagree on
how. In practice a Mesh actor's `PrePivot` is `(0,0,0)` unless deliberately set, so this rarely
bites — but a native mesh transform that reuses the brush-transform helpers
(`rotation.actor_matrix`/`world_vertices`) for a mesh actor would apply the WRONG convention.

## `class show`/`class preview`'s existing mesh-local frame

`uedcli/meshfacts.py`/`meshrender.py` report extents and thumbnails in a frame with `Scale`
applied but `Origin`/`RotOrigin`/`DrawScale` NOT applied (mesh-local, single fixed frame — see
their own module docstrings). This doc's formula is what completes that into a real WORLD
placement; it does not change what `class show`/`class preview` report today.
