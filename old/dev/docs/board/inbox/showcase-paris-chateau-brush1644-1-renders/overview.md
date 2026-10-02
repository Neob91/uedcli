+++
priority = "p?"
kind = "unknown"
summary = "showcase_paris_chateau Brush1644:1 renders unlit in GUI, likely NumVertices=0 lightmap gate"
+++

# showcase_paris_chateau Brush1644:1 renders unlit in GUI, likely NumVertices=0 lightmap gate

`Brush1644:1` (`dev/games/trunks/showcase_paris_chateau/actors/Brush1644/actor.t3d`, poly index 1)
renders unlit in the uedcli GUI. Not a `PF_Unlit` flag — its `Flags=8388640` decode to
`PF_Semisolid | PF_HighShadowDetail` only. `PF_Semisolid` has no special-casing in the lighting code
(`uedcli-native/src/light.rs`, `bake_radiance`/`bake`).

GUI shows unlit because the server sent `poly.lightmap = null` (`uedcli/preview_native.py:1056`),
which `web/src/scene/geometry.ts:183` reads as `lit = lmUVs !== null`.

Likely cause: the editor's own lightmap-allocation gate — a BSP node with `NumVertices == 0` never
gets a `LightMap` record (`uedcli-native/src/light.rs:610-660`, ported from `Editor.dll 0x100a4a90`,
verified exact against 161/161 shipped Deus Ex map Models). `Brush1644` is a tiny (2x12x2 uu
pre-transform), sheared (`SheerAxis=SHEER_ZX`) sliver — plausible its solved BSP node ended up with
zero vertices or a degenerate lightmap basis (`light.rs:983`) after CSG.

If so, this is UED22-faithful behavior, not a GUI bug — real UnrealEd would likely also leave this
poly's surf unlit. Not confirmed: would need a debug dump of this level's solved `Model.Nodes[]`/
`Surfs[]` for the node owning this poly, to tell `NumVertices==0` apart from the degenerate-basis
path.

## Next step

Spike: build `showcase_paris_chateau` (native or editor) and inspect the solved BSP node/surf owning
`Brush1644:1` to confirm which path (or something else) excludes it from lightmapping.
