+++
priority = "p1"
kind = "debug"
summary = "FIXED 2026-09-17: tapSelect.ts drops a marker-sprite raycast hit whose sampled alpha is below the masked-material cutoff, matching UED22's hit-proxy blit (source-confirmed, PushHit/PopHit + the masked blitter's skip-on-transparent-texel); live A/B (real clicks, with/without the fix) confirms it."
+++

# point-actor sprite picking ignores sprite alpha

FIXED. See `GUI-PARITY.md`'s "Sprite alpha picking" Findings for the full RE trail and live-click
transcript — summary here only.

UED22's own click hit-test needs no special sprite-alpha rule: it reads back a rendered hit-proxy
buffer for the cursor's pixel box, and the masked-sprite blit that buffer shares with the real render
(`SoftDrv/Src/DrawTile.cpp`'s `FlashSprite32Masked`) never writes a screen pixel for a transparent
texel — so a transparent click is invisible to the readback as a side effect of the shared rasterizer,
not a coded special case (📖 `fgsfdsfgs/UE1` source, cross-checked against this repo's `Editor.dll`/
`render.dll` exports).

Fix: `web/src/scene/tapSelect.ts`'s `isSpriteHitTransparent` samples the sprite's own `CanvasTexture`
alpha at the raycast hit's `uv` and drops the hit (falls through, like a genuine miss) below the
existing masked-material alphaTest cutoff (`selection.ts`'s new `isTransparentPixel`, 0.5).

🔬 Live-verified with real `page.mouse.click`s against `showcase_bar`: clicking a real Light actor's
marker (`HKMarketLight1`) selects it near the icon center and misses past ~18px out; re-clicking the
SAME pixels against the pre-fix code (`git stash`) selected it there every time, proving the miss is
the alpha filter, not a geometric miss of the sprite's quad.
