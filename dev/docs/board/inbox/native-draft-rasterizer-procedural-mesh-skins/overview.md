+++
priority = "p2"
kind = "feature"
summary = "native draft rasterizer: support procedural (bitmap-less) mesh skins"
+++

# native draft rasterizer: procedural mesh skins hard-fail

`level photo --native --faces textured` (and `class preview`) exit 2 on a mesh whose skin is a
**procedural** texture — one with no stored bitmap, generated per-frame by the engine (FireTexture,
WaterTexture, WetTexture, an FX/electricity skin, etc.). Example: `DeusEx.BioelectricCell`'s skin
`Effects.BioCell_SFX` (group `Electricity`, no bitmap). `resolve_skins` → `TextureResolver.resolve`
correctly refuses it (no bitmap to sample), and per the no-fallback convention the whole render
exits 2 naming it.

This blocks textured `--native` on most DX levels, since FX-skinned decos are common. Owner ruling
(2026-09-07): keep the hard-fail (RED) — NO flat-grey / DefaultTexture substitution — and track real
procedural-texture support here instead.

Scope: teach the native rasterizer to render procedural textures to a representative still (decode
the procedural class's source — palette / fill / a synthesized frame). Until then textured `--native`
stays unusable where such skins appear; `--faces wire` is the working `--native` photo there.

Related: `done/native-textured-photo-cannot-resolve-mesh-skin` (the package-path half, fixed);
`inbox/native-photo-renders-untextured-faces-flat-grey` (missing world texture → DefaultTexture, a
different case with a different owner ruling).
