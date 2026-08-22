# Is non-brush `DrawScale`/`DrawScale3D` in scope, or its own item?

## Context

"Render all the transforms" — but `DrawScale`/`DrawScale3D` (the scale on NON-brush actors: sprites,
meshes, point actors) is a different mechanism from brush `MainScale`/`PostScale`, and it is **not
modeled at all** today: no typed field in `model.py`, and the sprite footprint takes a bare
`draw_scale` scalar (`preview.py:339`) that nothing populates from the actor. Adding it means: parse/
store `DrawScale` (scalar) and `DrawScale3D` (vector) as typed fields, then scale the sprite billboard
and (eventually) mesh render by them.

- **Defer to its own item** (recommended): this item is the brush transform stack (`MainScale`/
  `PostScale`/`SheerRate`/`PrePivot`), which is a coherent, self-contained change. `DrawScale` is a
  separate modeling gap with its own tests and no overlap with the CSG-solve work.
- **Include here**: one "all transforms" change. Larger and mixes two unrelated mechanisms.

## Answer

<!-- Empty = open. -->
