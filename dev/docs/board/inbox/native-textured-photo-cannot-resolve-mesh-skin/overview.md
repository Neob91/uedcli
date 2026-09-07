+++
priority = "p2"
kind = "bug"
summary = "native textured photo cannot resolve mesh skin package though utx exists in substrate"
+++

# native textured photo cannot resolve mesh skin package though utx exists in substrate

`level photo --native --faces textured` on UNATCO exits 2:

```
cannot preview DeusEx.BioelectricCell: mesh skin Effects.BioCell_SFX did not
decode [unknown-package]: no package named 'Effects' on the composed search path
```

`--faces wire` works; the exit-2 (naming the value) is itself correct — the bug is
that `Effects` isn't on the mesh-skin search path though it exists:

- `dev/games/deusex/Textures/Effects.utx`
- `dev/games/substrate-deusex/Textures/Effects.utx`

The project is a bare `game = "deusex"` (no explicit package list). BSP world textures
resolve; mesh-skin resolution apparently doesn't reach the game's texture dir the same
way. Repro: any `deusex` project holding a `DeusEx.BioelectricCell` (or any mesh whose
skin lives in `Effects.utx`), `--faces textured`.

Fix toward: mesh-skin package resolution should use the same composed search path as
world-texture resolution (which finds `Effects.utx`). Distinct from the untextured-face
grey issue (`native-photo-renders-untextured-faces-flat-grey`): that's world faces with
no texture; this is a mesh skin whose package isn't found.
