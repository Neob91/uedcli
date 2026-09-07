+++
priority = "p2"
kind = "feature"
summary = "native draft rasterizer: support procedural (bitmap-less) mesh skins"
+++

# native draft rasterizer: procedural mesh skins hard-fail

A **procedural** mesh skin — no stored bitmap, generated per-frame by the engine (FireTexture,
WaterTexture, WetTexture, an FX/electricity skin, etc.) — has nothing for the draft rasterizer to
sample. Example: `DeusEx.BioelectricCell`'s skin `Effects.BioCell_SFX` (group `Electricity`).

Current behaviour (owner ruling 2026-09-07): such a skin renders as solid **RED**
(`meshrender.PROCEDURAL_RED`) — a visible "not-rendered-yet" marker — NOT a hard-fail and NOT a
silent grey. `resolve_skins` substitutes red only on the `no-mip-data` case (needs the widened
`class_index` resolver so a procedural `Engine.Texture` descendant reaches that case); every other
undecodable ref still exits 2 naming it.

Scope of THIS item: replace the red placeholder with a representative still — decode the procedural
class's source (palette / fill / a synthesized frame) so FX skins render approximately, not as red.

Related: `done/native-textured-photo-cannot-resolve-mesh-skin` (the package-path half, fixed);
`inbox/native-photo-renders-untextured-faces-flat-grey` (missing world texture → DefaultTexture, a
different case with a different owner ruling).
