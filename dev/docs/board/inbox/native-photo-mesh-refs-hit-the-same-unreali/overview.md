+++
priority = "p3"
kind = "debug"
summary = "level photo --native aborts on NaliC.unr: a Mesh ref names the stale UnrealI package (NaliHead) the same way class and texture refs did"
+++

# native photo mesh refs hit the same UnrealI/UnrealShare stale-package gap

`level photo --native` on the retail Unreal Gold map `NaliC.unr` aborts with:

```
cannot read mesh facts for UnrealShare.Liver: mesh UnrealI.NaliHead is not a mesh export in package UnrealI
```

Same root fact as `dev/docs/board/done/unreal1-ut99-map-import-stale-class-package/` (classes) and
the texture-ref fix landed alongside this item (`utexture.TextureResolver._locate_texture`): an
original (1998/Gold) Unreal `.unr`'s own tables can name an object's home package as `UnrealI` when
the shipped System files actually define it in `UnrealShare.u`. Not checked whether `NaliHead`
actually exists under `UnrealShare` — only that the map states `UnrealI.NaliHead` and decode fails
outright (whole-shot abort, per spec).

Likely fix location: `uedcli/meshfacts.py` (`decode_mesh`/whatever resolves a `Mesh=` prop to a
package + export), mirroring `mapimport._resolve_actor_class`'s and `utexture.TextureResolver
._locate_texture`'s "exact-package miss falls back to a whole-path name search, ambiguous
collision prefers UnrealShare" pattern.

Repro: `dev/games/unreal/Maps/NaliC.unr`, `level photo --native` from `PlayerStart2`
(-129.1, -6713.5, 3143.5). Out of scope for the texture-resolver fix this item's sibling landed —
filed separately since it's a different subsystem (`meshfacts.py`, not `utexture.py`).
