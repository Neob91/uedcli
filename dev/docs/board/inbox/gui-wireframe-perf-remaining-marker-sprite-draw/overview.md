+++
priority = "p3"
kind = "implement"
summary = "GUI wireframe perf: remaining marker-sprite draw calls after brush-outline merge"
+++

# GUI wireframe perf: remaining marker-sprite draw calls after brush-outline merge

A live-QA report ("wireframe-mode navigation is slow/jittery") traced to `BrushOutlines.tsx`
issuing one WebGL draw call per brush POLY (`LineLoop`/`Line2`) -- measured ~11,000+ draw calls per
wireframe pane on WanChai (~2287 actors, 8235 brush polys), ~350ms/frame even sitting idle across
the quad's 4 panes. Fixed: non-selected rings now merge into ONE `THREE.LineSegments` draw call per
pane (`brushRings.ts`'s `mergeThinRings`), selected (bold) rings stay individual `Line2` objects
(there are only ever a handful). Measured with a real headless-Chromium profile (WebGL
`drawArrays`/`drawElements` call counter + `requestAnimationFrame` timing, `web/perf_test.cjs`,
not committed -- ad hoc harness):

| | before | after |
|---|---|---|
| idle draw calls / 2 rAF frames | 22,688 | 1,713 |
| idle frame time (avg) | 350ms | 110ms |
| idle frame time (max) | 724ms | 507ms |

~13x fewer draw calls, ~3x faster idle frame time -- but still not smooth (110ms avg ~= 9fps
idle). The remaining cost is very likely the ~956 non-brush actors (lights/triggers/sounds/etc,
WanChai), each drawn as its own individual `<sprite>` in `Viewport3D.tsx`/`OrthoViewport.tsx`
(`markerActors.map(...)`) -- one draw call per marker, times 4 quad panes, never merged. Not fixed
here: merging sprites needs a different approach (instancing, or a single point-cloud draw with a
custom shader for per-marker texture/tint) and wasn't part of this bug-bash pass's scope. Also
worth checking: every pane's `<Canvas>` re-renders every animation frame unconditionally
(`frameloop` left at R3F's default `"always"`) even with a fully static scene -- switching to
`frameloop="demand"` + explicit `invalidate()` calls on pose/selection changes would eliminate
wasted idle rendering entirely, but needs care since `OrthoCameraRig`/`CameraRig` derive the camera
transform every frame via `useFrame` and drag gestures update `pose` state continuously.

Root cause file: `web/src/scene/Viewport3D.tsx`, `web/src/scene/OrthoViewport.tsx` (`markerActors`
sprite rendering). Fix landed for the brush-outline half: `web/src/scene/BrushOutlines.tsx`,
`web/src/scene/brushRings.ts` (`mergeThinRings`), `web/src/scene/selection.ts`
(`resolveSegmentHitActor`).
