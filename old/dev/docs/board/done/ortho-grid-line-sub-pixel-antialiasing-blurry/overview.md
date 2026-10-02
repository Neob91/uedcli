+++
priority = "p3"
kind = "implement"
summary = "Ortho grid lines blur to 2px sub-pixel-off-boundary, and which lines blur shifts on pan -- fixed by snapping each line to the nearest device pixel"
+++

# Ortho grid line sub-pixel antialiasing (blurry, alternates on pan)

Owner report: "some lines render wider than other ones... And when I move, they alternate."
`web/src/scene/GridOverlay.tsx`/`grid.ts`, the escalating ortho grid.

Separate bug from `dev/docs/board/done/ortho-grid-density-no-reproducible-bug-found/` (that
investigation verified the escalation/color math is correct and matches UED22 -- not touched here).

## Real evidence (live pixel measurement, not reasoning)

Got a real browser working in this sandbox (headless Chromium via SwiftShader; this host's stock
Chromium/Firefox installs were missing dozens of shared libraries -- built a local, non-root library
prefix via `apt-get download` + `dpkg-deb -x` for `glib`/`gtk`/`atk`/`dbus`/X11-extension/`asound`/
`gbm`/Mesa-software-GL). Measured actual pixel rows of the live app's ortho panes:

- At a single static pose, several grid lines were exactly 1 device pixel wide at full color
  strength; neighboring lines were split evenly across 2 pixels at half color strength -- a real
  antialiasing coverage split (`LineBasicMaterial`'s 1px `GL_LINE`), not a color/contrast illusion.
- Panning by a few CSS pixels changed WHICH lines were crisp vs. blurred, reproducing "when I move,
  they alternate" directly.
- Root cause: a grid line's continuous world coordinate maps to a continuous (non-integer) device
  pixel position; WebGL's line rasterizer blurs a line across 2 pixels whenever it lands off a
  device-pixel boundary, and this happens independently per line since escalated line spacing is
  essentially never a whole number of device pixels.

## Fix

`GridOverlay.tsx`: snap each line's coordinate to the nearest device-pixel CENTER before building
its geometry (`snapToDevicePixel`) -- the standard fix for crisp grid/ruler rendering. Verified by
trying the alternative (snap to a pixel BOUNDARY) and measuring it uniformly WORSE.

One non-obvious wrinkle, found only by live measurement across multiple zoom levels (an initial fix
looked "half-working" -- crisp near one edge, still blurred toward the other): the device-pixel
denominator must be `Math.round(size.width * dpr)`/`Math.round(size.height * dpr)` (three.js's own
internal viewport-rounding, `WebGLRenderer.setViewport`), NOT `gl.domElement.width`/`.height` (the
backing-buffer size, which three.js *floors*). This app's quad panes have fractional CSS sizes (e.g.
360.5px), so the two differ by a small amount that compounds to over half a device pixel of drift by
the pane's far edge if you use the wrong one.

`grid.ts`'s escalation/color math is untouched.

## Verification

- Live pixel measurement (headless Chromium, real WebGL2/SwiftShader), filtering scan-line pixels to
  near-grayscale only (excludes real colored scene geometry -- walls, NPC sprites, CSG wire colors --
  from contaminating the grid-line read): TOP and FRONT panes both uniformly crisp (0 blurred lines)
  across multiple zoom levels, both tested grid-size settings, and multiple scan lines per pane,
  whenever the scan line doesn't cross real scene content. (Scan lines that DID cross real content --
  visually confirmed via screenshots showing an NPC sprite and colored CSG wires -- produced wide
  "runs" that are provably scene geometry, not grid; two earlier, cruder pixel-scan passes had
  mistaken this contamination for a real per-pane bug before this was caught.)
- One recurring, low-severity residual: a single ~3px run appears at a consistent position across
  several different scans (independent of zoom/pane), against a background of dozens of otherwise
  perfectly crisp lines each time. Not chased further (small, consistent, more likely a fixed UI/pane
  border artifact than a grid bug) -- flagged honestly rather than smoothed over.
- New regression tests, `web/src/scene/GridOverlay.test.tsx`: read the actual rendered
  `BufferGeometry` position buffer back (via `@react-three/test-renderer`, not a screenshot) and
  assert every line's computed device-pixel coordinate lands within float32 rounding of a
  half-integer -- integer pane width, fractional pane width, a panned `pose.center`, `dpr=2` with a
  fractional width, the 'v'-axis (front pane) at three zoom levels.
- Full frontend suite (456 tests, 50 files) green.

## Two follow-up reports, both measurement artifacts, not code bugs

Re-verified live after the fix: "top pane blurry at the default zoom" and "front pane's v-axis
anomalous at every zoom." Both traced to the same crude verification method -- a single fixed
scan row/column -- crossing real scene geometry (an NPC sprite, colored CSG wire edges) that a loose
near-gray color filter let through, producing "bad" runs that looked like a pane-specific bug.
Rewriting the scan to sample 5 different row/column fractions per pane, computed the row's own most
common pixel value as background instead of assuming one, and confirmed: any scan line that does not
cross real content reads 0 blurred lines, at the default zoom and at every other zoom tested, in
both panes. No code change was needed for either report.

One low-severity residual (see Verification above) was not chased further.

Reviewed with `superpowers:requesting-code-review`: no code defect found; three test-coverage gaps
(no panned-camera test, no `dpr!=1` test, front pane tested at only one zoom level) -- all three
addressed with the tests listed above.
