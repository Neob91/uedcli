+++
priority = "p2"
kind = "investigate"
summary = "GUI click-detection algorithm not RE'd against UED22 hit-testing"
+++

# GUI click-detection algorithm not RE'd against UED22 hit-testing

`web/src/scene/tapSelect.ts`/`selection.ts` resolve a click via a three.js `Raycaster` against the
real drawn geometry (nearest-hit-wins), falling back to ray-vs-AABB. This is a reasonable web-editor
default, built from spec/convention — never confirmed against what UED22's own C++ hit-testing
actually does when candidates overlap (a surface behind another, a point-actor sprite over a brush
face, a thin brush edge near a face).

## Why this matters

`dev/docs/unrealed/quirks.md`'s "Selection" section already establishes a hard constraint: `PF_Selected`
does not round-trip, so per-polygon selection state can't be read back after a click — the accuracy
of a specific click resolution can only be confirmed by watching the real hit-test happen (disassembly
+ live capture), not by driving verbs and reading state back afterward.

## What this needs

Part of the `GUI-PARITY.md` root campaign (see there for the two RE tools — live screenshot probe vs.
disassembly — and when to use each). This specific question has no visual signature (a correct pick
looks identical to an incorrect one unless you already know which actor should have won), so it needs
the disassembly + live-capture path: find UED22's viewport mouse-click handler in `Editor.dll`/
`Render.dll` (candidate: a `HitProxy`-style render pass or a software pick-buffer, per common UE1
architecture — unconfirmed here), then live-verify the recovered algorithm against overlap test scenes.

Not started this session — filed so it's tracked, not attempted opportunistically alongside other
work (the same resource-risk note as `gui-texture-actor-click-select-modifier-rules` applies: a fresh
UED22 container boot is not cheap, and this needs several).
