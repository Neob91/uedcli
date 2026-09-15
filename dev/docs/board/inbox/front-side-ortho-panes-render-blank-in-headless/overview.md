+++
priority = "p3"
kind = "finding"
summary = "Front/Side ortho panes render blank in headless Chromium (WebGL never draws)"
+++

# Front/Side ortho panes render blank in headless Chromium (WebGL never draws)

Found while visually verifying the grid-color/z-layering fix (ortho-layering-fix branch). Not
investigated further — out of scope for that change, and not confirmed to reproduce in a real
browser (see caveat below).

## Observation

Loaded a 4-actor test level (`TestLevel`: a Room brush, a Room2 coincident brush, Lamp, Start0) in
the quad-layout GUI under headless Chromium (`chromium-1243`, `--no-sandbox --disable-gpu
--disable-dev-shm-usage`, extracted-`.deb` shared libs, SwiftShader software GL). Screenshotted all
four panes:

- **Perspective** and **Top**: render correctly — grid, brush wireframes, markers all visible.
- **Front** and **Side**: totally blank `#404040`-looking fill, but a `gl.readPixels` probe at
  canvas center returns `(0,0,0,0)` — not even the explicit `<color attach="background">` (`#404040`,
  which would read back as `(64,64,64,255)`). This means the WebGL framebuffer was never drawn to at
  all for these two canvases, not just "nothing at this world position."
- The surrounding React UI (toolbar, pane labels, org panel, cursor-coordinate readout computed from
  `screenToWorld`) all work correctly for Front/Side — only the `<Canvas>`'s own render output is
  empty. No console error, no `pageerror`, no lost WebGL context (`gl.isContextLost()` false on all
  four canvases).
- Maximizing the Front pane alone (hiding the other three via the `hidden` attribute, all four
  `<Canvas>`es stay mounted) does not change anything — still `(0,0,0,0)` at center. Rules out a
  simple "too many concurrent WebGL contexts" resource-contention theory.
- `OrthoCameraRig`'s `orthoBasis`/`makeBasis` math looks fine on inspection — Top/Front/Side all
  produce a `det = -1` (improper/mirrored) rotation matrix by the same construction, so that alone
  doesn't distinguish working Top from broken Front/Side.

## Caveat — may be a test-environment artifact, not a real bug

This host was under extreme concurrent load during the observation (dozens of other agents running
cargo builds, pytest, and multiple `vite`/vitest processes at once), and the browser was a
`--disable-gpu` SwiftShare software-rendering Chromium reached via manually-extracted `.deb` libs
(playwright's cached Chromium build, no sandbox). Not confirmed against a real GPU-accelerated
browser. Whoever picks this up should first re-check in an ordinary browser (or a quieter headless
run) before spending time on the app code — this may be purely a software-renderer/resource
limitation of this specific sandbox, not a shippable bug.

## Next step if it reproduces cleanly

Instrument `OrthoCameraRig`/`OrthoViewport`'s `<Canvas>` `onCreated` to confirm `gl.render` is
actually being invoked for the Front/Side panes, and diff against Top's working path.
