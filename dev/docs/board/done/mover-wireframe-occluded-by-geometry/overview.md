+++
priority = "p1"
kind = "debug"
summary = "mover wireframe should always render, unoccluded by other geometry, even in non-wireframe mode"
+++

# Mover wireframe gets occluded by other geometry

Fixed: an unselected Mover's thin wireframe ring now renders `depthTest={false}` with an elevated
`renderOrder`, in its own split-out `MergedThinWireframe` draw call (`web/src/scene/BrushOutlines.tsx`,
`brushRings.ts`'s new `BrushRing.isMover`), so it always composites over solid geometry in every
shading mode. Non-Mover rings are unaffected. Verified live (headless Chromium, `showcase_bar`): with
the fix reverted, an unselected Mover's outline vanished behind a ceiling opening's archway geometry
from an elevated angle; with it applied, the same outline rendered on top at the identical camera pose.
Independently re-verified by a review subagent (own backend/browser session, same repro, pixel-level
before/after diff isolating the exact mover-door bbox).
