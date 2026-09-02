+++
priority = "p3"
kind = "debug"
summary = "REFUTED: level preview --native renders OG geometry fine; Entry.dx is just an all-black-textured menu map"
+++

# REFUTED — not a bug

Investigated "offline preview renders imported OG levels empty." Two independent subagents (empirical
+ code) refuted it. The offline renderer is NOT broken and world position is NOT the cause:

- `Entry.dx` (the DeusEx main-menu backdrop) is textured entirely with `DeusExItems.Skins.BlackMaskTex`
  — a 2×2 all-`(0,0,0)` texture. The `--native` render is pure black on ALL pixels (not the `[56,56,60]`
  background grey), i.e. geometry drew and was correctly textured black. "Empty" was a misread.
- Far-from-origin: translating the authored `anchor` to X+1500/+6000/+10000 → byte-for-byte identical
  renders. The rasterizer subtracts the camera eye before projecting (`render.rs:158`); absolute world
  magnitude is irrelevant. f32 is exact to 2^24, far above these coords.

Lesson: pick a texture-visible OG gameplay level, not the black-masked menu map, to compare
`--native` vs `--game`. Done.
