# class show

A class's own editable props grouped by editor category + super chain + placeable/abstract flags, then a Facts block, then any stored classification. Offline, reads the game `.u`.

```bash
uedcli class show <Package.Class> [--depth N|all] [--category NAME] [--json]
```

`class show` is the UnrealEd property-browser view (Movement/Display/Lighting/…): own editable
props by category, non-editable internals hidden, inherited props collapsed to per-category counts.
`--depth N|all` expands inherited props (tagged with their source class); `--category NAME`
(repeatable) shows only that category, expanded over the whole chain.
- After the property schema, `class show` prints a **Facts** block read from the class's package —
  the file-facts an agent needs to place a prop, nothing inferred:

  ```
  Facts:
    drawtype:  DT_Mesh
    mesh:      DeusExDeco.CrateUnbreakableLarge
    extents:   x -40..40  y -40..40  z -56..56   (mesh-local uu; Scale applied, pre-Origin/RotOrigin, DrawScale not)
    collision: radius 56.5  height 56
    prepivot:  0,0,0
    parent:    DeusEx.Containers
  ```

  - **`extents`** is the default `Mesh`'s bounding box as **signed lo..hi per axis** in integer
    Unreal units, in the mesh's own frame: the mesh's `Scale` is applied per-axis (each axis then
    re-sorted so `lo <= hi`), while `Origin`, `RotOrigin` and per-placement `DrawScale` are **not**.
    These are **seating/footprint** facts — the height and whether the mesh sits at `z=0`. They do
    **not** state which way the mesh faces in the world.
  - **`collision`** is the upright collision cylinder (`CollisionRadius`/`CollisionHeight`), which
    carries no facing; **`prepivot`** is `PrePivot`; **`parent`** is the direct super class.
  - A **non-mesh** class (`DrawType` `DT_Sprite`/`DT_Brush`/`DT_None`) has no mesh, so `mesh` and
    `extents` are `none` (`null` in `--json`) — not an error. A `DT_Mesh` class whose `Mesh` is
    missing or fails to decode **exits 2** naming the class and mesh.
- After the Facts block, `class show` prints the stored **Classification** (the `tags` and
  `description` an LLM recorded via `class classify`), or `(unclassified)` when there is none.
- **`--json`** prints only the facts as one JSON object — `{"ref", "drawtype", "mesh", "extents":
  {"x":[lo,hi],…}|null, "collision":{"radius","height"}, "prepivot":[x,y,z], "parent", "abstract",
  "placeable", "classification": {"tags":[…], "description":…}|null}` — instead of the property
  schema.
- Reading a class means reading its whole **super chain**, so if an ANCESTOR's package is missing
  from the search path (or unreadable), `class show` **fails with exit 2 naming that package** —
  `cannot read schema for DeusEx.Flare: package 'Engine' (needed for Engine.Actor) not found on the
  schema search path …` — instead of printing the class's own properties as if that were the full
  list. (A missing package for the class you NAMED is caught earlier, as `unknown class: …`.)

See also: [`class list`](list.md), [`class preview`](preview.md), [`class classify`](classify.md).
