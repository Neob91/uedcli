// Plain (non-component) rendering helpers shared by Viewport3D.tsx and OrthoViewport.tsx, kept out
// of either component's own file so neither mixes a component export with a value export -- Vite's
// react-refresh plugin can't Fast Refresh a file that does both ("X export is incompatible"), which
// silently wedges the pane (a stale module graph crashes on the next re-render, e.g.
// "useSceneResourcesContext() called outside a <SceneResourcesProvider>") until a full page reload.
import * as THREE from 'three'

import type { CameraPose } from './camera'
import { cameraBasis } from './camera'
import type { OrthoAxis, OrthoPose } from './orthoCamera'
import { orthoBasis } from './orthoCamera'

// Far enough to enclose a whole UE1 level (+/-32768 UU) from any starting center -- matches the
// perspective pane's far=131072 reasoning.
const ORTHO_HALF_RANGE = 65536

/** `render.rs` (Viewport3D's parity target) shades by multiplying raw 0-255 texel bytes directly by
 * a flat/lightmap scalar -- no sRGB decode of the texture, no re-encode of the result
 * (`(rr * shade).clamp(0.0, 255.0)`). R3F's `<Canvas>` defaults do NOT match that: with neither
 * `linear` nor `legacy` set, it still applies a linear-to-sRGB ENCODE at output
 * (`gl.outputColorSpace = THREE.SRGBColorSpace`) even though nothing on the way in ever decodes
 * (every texture here defaults to `THREE.NoColorSpace` -- see `sceneResources.ts`'s
 * `useTextures`/`useMarkerTexture`), and `ColorManagement` auto-decodes hex/`THREE.Color` literals
 * (`UNTEXTURED_GREY`, `SELECTION_BOX_COLOR` -- constructed via `new THREE.Color(hex)`) as sRGB on
 * construction. (`MARKER_COLOR_THREE` is built via `setRGB(r,g,b)` instead, whose default
 * `colorSpace` is already the working linear space -- its on-screen correction comes entirely
 * from the output-encode half, not from `legacy`.) A decode-less-but-still-encoded pipeline does
 * not merely dim a FEW things -- traced against three's own `LinearToSRGB`/`SRGBToLinear`
 * (`ColorManagement.js`), it brightens EVERY texel (0.5 renders as ~0.735) and darkens every
 * auto-decoded hex literal, in both cases moving away from the exact source value. `flat` (no
 * tone mapping, already present) doesn't touch either effect. `linear` (`outputColorSpace =
 * LinearSRGBColorSpace`, skips the output encode) + `legacy` (`ColorManagement.enabled = false`,
 * skips the hex-literal auto-decode) together make the whole pipeline a pure passthrough --
 * matching render.rs's zero-color-management model, and the invariant that a fullbright sprite
 * (no vertex color, no lightmap, default-white material) must display its exact source pixel.
 *
 * IMPORTANT: `ColorManagement.enabled` is a process-wide singleton, not per-`<Canvas>` -- r3f's
 * `configure()` sets it unconditionally on EVERY render of every mounted Canvas. Any sibling
 * `<Canvas>` in the app (e.g. an ortho pane) that doesn't also spread `CANVAS_COLOR_MANAGEMENT`
 * will flip this flag back on its own next render, silently undoing this fix here too -- every
 * `<Canvas>` in this app MUST spread the same `CANVAS_COLOR_MANAGEMENT` constant (both
 * Viewport3D.tsx and OrthoViewport.tsx do). */
export const CANVAS_COLOR_MANAGEMENT = { flat: true, linear: true, legacy: true } as const

// `THREE.Raycaster.params.Line.threshold` for a wireframe brush-outline hit in the PERSPECTIVE pane,
// in WORLD units -- fixed rather than zoom-scaled (unlike `orthoCamera.ts`'s
// `orthoLineHitThresholdUU`) because the perspective pane's own dolly-zoom already keeps nearby
// geometry at a roughly stable screen size (`performTapSelect`'s own doc comment). Widened 4 -> 8
// (owner report, live testing: brush-outline selection needed near-pixel precision) -- a tuning
// judgment call, doubled alongside `orthoCamera.ts`'s `LINE_HIT_SCREEN_PX` widening (2 -> 6px) for
// the same complaint; no RE evidence pins an exact editor value here.
export const WIREFRAME_LINE_HIT_WORLD_UNITS = 8

/** Applies `pose` to a `THREE.PerspectiveCamera` -- Z-up (`camera.up`), aimed via `lookAt` (a
 * proper, always-valid rotation -- keeps roll disambiguation simple for a Z-up world with no roll
 * of its own), THEN mirrors the projection horizontally (`projectionMatrix`'s NDC-x scale term
 * negated). The world is left-handed (X forward, Y right, Z up) but its raw coordinates feed
 * three.js's right-handed renderer verbatim (`geometry.ts` applies no axis flip), so a plain
 * (proper-rotation) camera necessarily renders this world's `right` on the wrong screen side --
 * confirmed live: a world-space arrow pointing toward +Y (`cameraBasis.right`) rendered on the LEFT
 * of this pane, matching the reported "meshes render reverted (mirror image)" bug, and matching a
 * fresh `level photo --native` (render.rs, this pane's own calibration target) of the identical
 * camera pose, which renders the SAME arrow on the RIGHT.
 *
 * This mirror has to happen at the PROJECTION step, not the view/rotation step: the "obvious"
 * alternative -- build the camera's local axes directly from `(right, up, -forward)` via
 * `Matrix4.makeBasis` (matching `OrthoViewport.tsx`'s `OrthoCameraRig`) -- produces an IMPROPER
 * matrix (determinant -1: `cross(right, up) == forward`, not `-forward`, a direct consequence of
 * the world being left-handed), and an improper matrix breaks BOTH obvious ways to apply it: (1)
 * `camera.quaternion.setFromRotationMatrix` assumes a proper rotation and silently produces a
 * camera looking in a WRONG direction (confirmed live: intended look direction `[1,0,0]`, actual
 * `[0,-1,0]`) -- not merely mirrored, pointed somewhere else entirely, so the scene vanishes at most
 * poses; (2) writing `camera.matrix`/`matrixWorld` directly (bypassing quaternion) DOES look the
 * right way and DOES carry the intended `right`/`up`/`forward` (confirmed live via
 * `transformDirection`), yet still projects every point through the mirror (confirmed live via
 * `Vector3.project`) -- an improper view matrix mirrors the render regardless of how "correct" its
 * individual axis vectors look, because a determinant-(-1) transform IS a reflection, full stop.
 * Negating the projection matrix's NDC-x term instead keeps the view/rotation step fully proper
 * (three.js's own well-tested `lookAt`, no custom matrix plumbing) and applies the one needed
 * mirror at a single, well-understood, easily-inverted spot.
 *
 * `projectionMatrixInverse` is kept in sync (the same element, negated the same way) because
 * `THREE.Raycaster.setFromCamera` (click-to-select, `performTapSelect`) unprojects screen points
 * through it -- left stale, clicks would target the PRE-mirror screen position.
 *
 * Pure THREE.js math -- no WebGL context needed, so it's unit-tested directly (`Viewport3D.test.ts`)
 * without mounting a `<Canvas>`. */
export function applyCameraPose(camera: THREE.PerspectiveCamera, pose: CameraPose): void {
  camera.up.set(0, 0, 1)
  camera.position.set(pose.position[0], pose.position[1], pose.position[2])
  const { forward } = cameraBasis(pose.pitch, pose.yaw)
  camera.lookAt(
    pose.position[0] + forward[0],
    pose.position[1] + forward[1],
    pose.position[2] + forward[2],
  )
  camera.updateMatrixWorld(true) // r3f does this too before rendering; explicit here so this
  // function is self-contained for direct (non-r3f) callers, e.g. Viewport3D.test.ts's
  // Vector3.project(camera), which reads matrixWorldInverse without updating it itself.
  camera.updateProjectionMatrix()
  camera.projectionMatrix.elements[0] *= -1
  camera.projectionMatrixInverse.elements[0] *= -1
}

/** Applies `pose`/`axis` to an ortho pane's `THREE.OrthographicCamera` every frame: axis-locked
 * position/orientation (looking along `orthoBasis(axis).forward` through `pose.center`), and a
 * frustum sized from `worldUnitsPerPixel` x the container's own pixel size so the pane's on-screen
 * scale matches `pose` exactly regardless of the pane's CSS size. Mirrors `applyCameraPose`'s
 * projection-NDC-x-negation technique (above) for the identical reason: the world is left-handed,
 * so a plain proper-rotation camera renders `right` on the wrong screen side; see that function's
 * doc comment for why the mirror must happen at the projection step, not the view/rotation step.
 *
 * `lookAt` derives local +X (screen-right) as `cross(up, eye-target)`, which for every one of this
 * module's three axis bases works out to the NEGATION of `orthoBasis`'s own `right`. Negating
 * `projectionMatrix`'s NDC-x term restores the intended screen-right without touching the
 * already-correct look direction/up, so pan direction stays correct too. `projectionMatrixInverse`
 * is kept in sync for the same reason `applyCameraPose` keeps it in sync: `performTapSelect`'s
 * `THREE.Raycaster.setFromCamera` unprojects screen points through it.
 *
 * Pure THREE.js math -- no WebGL context needed, so it's unit-tested directly
 * (`OrthoViewport.test.ts`) without mounting a `<Canvas>`. */
export function applyOrthoCameraPose(
  cam: THREE.OrthographicCamera,
  pose: OrthoPose,
  axis: OrthoAxis,
  viewportPx: { width: number; height: number },
): void {
  const { forward, up } = orthoBasis(axis)
  const x = pose.center[0] - forward[0] * ORTHO_HALF_RANGE
  const y = pose.center[1] - forward[1] * ORTHO_HALF_RANGE
  const z = pose.center[2] - forward[2] * ORTHO_HALF_RANGE
  cam.position.set(x, y, z)
  cam.up.set(up[0], up[1], up[2])
  cam.lookAt(x + forward[0], y + forward[1], z + forward[2])
  cam.updateMatrixWorld(true) // r3f does this before rendering; explicit here so this function is
  // self-contained for direct (non-r3f) callers, e.g. OrthoViewport.test.ts's Vector3.project(cam),
  // which reads matrixWorldInverse without updating it itself (applyCameraPose has the identical
  // call for the identical reason).
  const halfW = (viewportPx.width / 2) * pose.worldUnitsPerPixel
  const halfH = (viewportPx.height / 2) * pose.worldUnitsPerPixel
  cam.left = -halfW
  cam.right = halfW
  cam.top = halfH
  cam.bottom = -halfH
  cam.near = 0.1
  cam.far = ORTHO_HALF_RANGE * 2
  cam.updateProjectionMatrix()
  cam.projectionMatrix.elements[0] *= -1
  cam.projectionMatrixInverse.elements[0] *= -1
}
