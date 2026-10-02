/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'
import * as THREE from 'three'

import { applyOrthoCameraPose } from './viewportRender'
import { orthoBasis, orthoPan } from './orthoCamera'
import type { OrthoAxis, OrthoPose } from './orthoCamera'

// See Viewport3D.test.ts's identical top-of-file comment: this repo has no Canvas-in-test pattern,
// so wiring facts that can't be exercised without a real <Canvas> are pinned as source-text
// assertions instead.
const ORTHOVIEWPORT_SOURCE = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'OrthoViewport.tsx'), 'utf8')

// Ctrl/Cmd-drag actor translation (Task 9, ortho counterpart of Task 8's Viewport3D.tsx mechanism):
// the pure math (`moveInPlane`, `applyDelta`, `stagedLocationsFor`, `applyStagedOffsets`) is already
// unit-tested directly (`actorMove.test.ts`, `dragStage.test.ts`) -- these pin the WIRING facts
// specific to this pane: the move branch is checked and returns BEFORE the existing pan/zoom
// dispatch (an actor-move drag must never also move the camera), it uses `moveInPlane` (both of the
// pane's visible axes, via its own `axis` prop) rather than `moveAlongAxis`, `postStage` fires once
// from the existing onPointerUp boundary, and `effectiveActors` (not raw `actors`) reaches every
// position-driven overlay consumer -- mirroring the fix Task 8's review round landed, from the start.
describe('OrthoViewport -- Ctrl/Cmd-drag actor translation wiring', () => {
  it('resolves the actor-move branch and returns BEFORE the camera setPose dispatch in onDrag', () => {
    const onDragBody = /onDrag: \(dx, dy, buttons, _altKey, additive\) => \{([\s\S]*?)\n      \},/.exec(
      ORTHOVIEWPORT_SOURCE,
    )?.[1]
    expect(onDragBody).toBeDefined()
    const moveIdx = onDragBody!.indexOf('moveInPlane')
    const setPoseIdx = onDragBody!.indexOf('setPose((prev) => {')
    expect(moveIdx).toBeGreaterThanOrEqual(0)
    expect(setPoseIdx).toBeGreaterThan(moveIdx) // the move branch is checked, and returns, first
    const returnIdx = onDragBody!.indexOf('return', moveIdx)
    expect(returnIdx).toBeGreaterThan(moveIdx)
    expect(returnIdx).toBeLessThan(setPoseIdx)
  })

  it('gates the move branch on additive + a non-empty selection -- no buttons-keyed lookup (ortho has one combo)', () => {
    expect(ORTHOVIEWPORT_SOURCE).toContain('additive && selectedNames.size > 0')
    expect(ORTHOVIEWPORT_SOURCE).not.toContain('resolveActorMoveAxis')
  })

  it("uses moveInPlane with this pane's own axis and pose.worldUnitsPerPixel, not moveAlongAxis", () => {
    // `frame.dx`/`frame.dy` (not raw `dx`/`dy`): the tap-vs-drag threshold gate (Critical 1, final
    // review fix wave) -- see the describe block below.
    expect(ORTHOVIEWPORT_SOURCE).toContain('moveInPlane(frame.dx, frame.dy, axis, pose.worldUnitsPerPixel)')
    expect(ORTHOVIEWPORT_SOURCE).not.toContain('moveAlongAxis')
  })

  it('calls postStage exactly once, from the existing mouse onPointerUp boundary (no second pointerup listener)', () => {
    expect((ORTHOVIEWPORT_SOURCE.match(/postStage\(/g) ?? []).length).toBe(1)
    expect((ORTHOVIEWPORT_SOURCE.match(/onPointerUp = useCallback/g) ?? []).length).toBe(1)
    const onPointerUpBody = /const onPointerUp = useCallback\(\s*\(e: ReactPointerEvent<HTMLDivElement>\) => \{([\s\S]*?)\n    \},/.exec(
      ORTHOVIEWPORT_SOURCE,
    )?.[1]
    expect(onPointerUpBody).toBeDefined()
    expect(onPointerUpBody).toContain('postStage(sessionId, locations)')
  })

  // Review finding this task must NOT repeat (Task 8's own history): BrushOutlines/SelectionMarkers/
  // DirectionalArrows/RadiiOverlays fed raw actors directly would give a selected brush (or its
  // arrow/radii gizmos) no visual feedback during a Ctrl-drag, only the point-actor marker sprite.
  it('feeds effectiveActors (not the raw actors) to every position-driven overlay consumer', () => {
    expect(ORTHOVIEWPORT_SOURCE).toMatch(/<BrushOutlines\s+actors=\{effectiveActors\}/)
    expect(ORTHOVIEWPORT_SOURCE).toMatch(/<SelectionMarkers actors=\{effectiveActors\}/)
    expect(ORTHOVIEWPORT_SOURCE).toMatch(/<DirectionalArrows actors=\{effectiveActors\}/)
    expect(ORTHOVIEWPORT_SOURCE).toMatch(/<RadiiOverlays actors=\{effectiveActors\}/)
    // None of the four still reads directly off the raw (non-offset-aware) actors array.
    expect(ORTHOVIEWPORT_SOURCE).not.toMatch(/<BrushOutlines\s+actors=\{actors\}/)
    expect(ORTHOVIEWPORT_SOURCE).not.toMatch(/<SelectionMarkers actors=\{actors\}/)
    expect(ORTHOVIEWPORT_SOURCE).not.toMatch(/<DirectionalArrows actors=\{actors\}/)
    expect(ORTHOVIEWPORT_SOURCE).not.toMatch(/<RadiiOverlays actors=\{actors\}/)
  })

  it('derives effectiveActors from applyStagedOffsets(actors, stagedOffsets)', () => {
    expect(ORTHOVIEWPORT_SOURCE).toContain('applyStagedOffsets(actors, stagedOffsets)')
  })

  it('also moves the point-actor marker sprite position, mirroring Viewport3D.tsx', () => {
    expect((ORTHOVIEWPORT_SOURCE.match(/stagedOffsets\[actor\.name\] \?\? actor\.location/g) ?? []).length).toBe(1)
    expect((ORTHOVIEWPORT_SOURCE.match(/position=\{markerPosition\}/g) ?? []).length).toBe(2)
  })
})

// Final review fix wave, Critical 1: onDrag fired on every pointer-move unconditionally, with no
// tap-vs-drag threshold of its own -- a Ctrl+click with a few pixels of ordinary jitter both fired
// the (correctly-suppressed) multi-select tap AND staged an unintended tiny move. Fixed by gating
// the move branch on `moveDragThreshold.ts`'s `accumulateMoveDragFrame`, which mirrors
// `dragGesture.ts`'s own `isTap` threshold. The pure accumulator logic itself is unit-tested
// directly (`moveDragThreshold.test.ts`) -- these pin the WIRING fact that can't be exercised
// without a real <Canvas>: the branch is actually gated on it, not applying every frame's raw delta.
describe('OrthoViewport -- Ctrl/Cmd-drag tap-vs-drag threshold gating (Critical 1)', () => {
  it('gates the move branch on accumulateMoveDragFrame before applying any delta', () => {
    const onDragBody = /onDrag: \(dx, dy, buttons, _altKey, additive\) => \{([\s\S]*?)\n      \},/.exec(
      ORTHOVIEWPORT_SOURCE,
    )?.[1]
    expect(onDragBody).toBeDefined()
    const frameIdx = onDragBody!.indexOf('accumulateMoveDragFrame(moveDragAccRef.current, dx, dy)')
    const moveIdx = onDragBody!.indexOf('moveInPlane(')
    expect(frameIdx).toBeGreaterThanOrEqual(0)
    expect(moveIdx).toBeGreaterThan(frameIdx) // the threshold check happens BEFORE any move is applied
    // `dragMovedRef.current = true` only fires inside the `if (frame)` gate, never unconditionally.
    expect(ORTHOVIEWPORT_SOURCE).toMatch(/if \(frame\) \{[\s\S]*?dragMovedRef\.current = true[\s\S]*?\}/)
  })

  it('resets the threshold accumulator AND snapshots the pre-gesture offsets fresh at every pointerdown', () => {
    expect(ORTHOVIEWPORT_SOURCE).toContain('moveDragAccRef.current = freshMoveDragAccumulator()')
    expect(ORTHOVIEWPORT_SOURCE).toContain('preGestureOffsetsRef.current = stagedOffsetsRef.current')
  })
})

// Important 3, final review fix wave: postStage had no .catch() at all -- an unhandled promise
// rejection, no error surfaced, and (worse, given Critical 2) the client kept showing the move as
// staged even though nothing was staged server-side.
describe('OrthoViewport -- postStage error handling (Important 3)', () => {
  it('chains a .catch() off the SAME postStage call that reverts the offset and surfaces the error', () => {
    const postStageIdx = ORTHOVIEWPORT_SOURCE.indexOf('postStage(sessionId, locations)')
    expect(postStageIdx).toBeGreaterThanOrEqual(0)
    const catchIdx = ORTHOVIEWPORT_SOURCE.indexOf('.catch(', postStageIdx)
    expect(catchIdx).toBeGreaterThan(postStageIdx)
    // The revert + error-surface both happen inside THAT catch, not somewhere unrelated.
    const revertIdx = ORTHOVIEWPORT_SOURCE.indexOf('setStagedOffsets(preGestureOffsetsRef.current)', catchIdx)
    const errorIdx = ORTHOVIEWPORT_SOURCE.indexOf('onStageError?.(String(e2))', catchIdx)
    expect(revertIdx).toBeGreaterThan(catchIdx)
    expect(errorIdx).toBeGreaterThan(catchIdx)
  })
})

// Regression for the Front/Side blank-pane bug (owner report, live browser + headless repro):
// `OrthoCameraRig` used to build its rotation via `Matrix4.makeBasis(right, up, -forward)`, which
// is an IMPROPER matrix (determinant -1) for all three axes -- a consequence of this world being
// left-handed (see `Viewport3D.tsx`'s `applyCameraPose` doc comment, which already predicted this
// failure mode for this exact pattern). `THREE.Quaternion.setFromRotationMatrix` silently
// mis-decomposes an improper matrix; for `front`/`side` this pointed the camera along a completely
// wrong axis (nothing in the scene ever entered the frustum -- blank pane), while `top` happened to
// end up pointing the right way (just upside-down), which is why only front/side looked broken.
//
// The fix mirrors `Viewport3D.tsx`'s existing technique: build the rotation via `camera.up` +
// `lookAt` (always a proper, valid rotation), then mirror the projection matrix's NDC-x term to
// restore the intended screen-right (`lookAt` derives screen-right as `cross(up, forward)`, the
// exact negation of `orthoBasis.right` for all three axes here).
function projectRelative(pose: OrthoPose, axis: OrthoAxis, offset: [number, number, number]): THREE.Vector3 {
  const camera = new THREE.OrthographicCamera()
  applyOrthoCameraPose(camera, pose, axis, { width: 100, height: 100 })
  // Content is drawn inside a reflected `<group scale={[1,-1,1]}>` and the camera pose is reflected by
  // the same R = diag(1,-1,1), so a game-coord point appears at the projection of R*point (negate Y).
  const point = new THREE.Vector3(pose.center[0] + offset[0], -(pose.center[1] + offset[1]), pose.center[2] + offset[2])
  return point.project(camera)
}

const AXES: OrthoAxis[] = ['top', 'front', 'side']
const POSE: OrthoPose = { center: [10, -20, 30], worldUnitsPerPixel: 1 }

describe('applyOrthoCameraPose', () => {
  it('looks along orthoBasis(axis).forward for every axis (never a wrong axis entirely)', () => {
    for (const axis of AXES) {
      const camera = new THREE.OrthographicCamera()
      applyOrthoCameraPose(camera, POSE, axis, { width: 100, height: 100 })
      const { forward } = orthoBasis(axis)
      const lookDir = new THREE.Vector3(0, 0, -1).transformDirection(camera.matrixWorld)
      // Camera posed in reflected space: looks along R*forward = (fx, -fy, fz).
      expect(lookDir.x).toBeCloseTo(forward[0], 5)
      expect(lookDir.y).toBeCloseTo(-forward[1], 5)
      expect(lookDir.z).toBeCloseTo(forward[2], 5)
    }
  })

  it('renders a point offset toward orthoBasis(axis).right on the right of the screen (positive NDC.x)', () => {
    for (const axis of AXES) {
      const { right } = orthoBasis(axis)
      const ndc = projectRelative(POSE, axis, [right[0] * 10, right[1] * 10, right[2] * 10])
      expect(ndc.x).toBeGreaterThan(0)
    }
  })

  it('renders a point offset toward orthoBasis(axis).up higher on the screen (positive NDC.y)', () => {
    for (const axis of AXES) {
      const { up } = orthoBasis(axis)
      const ndc = projectRelative(POSE, axis, [up[0] * 10, up[1] * 10, up[2] * 10])
      expect(ndc.y).toBeGreaterThan(0)
    }
  })

  it('keeps the scene inside the frustum -- a point at pose.center always projects near NDC origin', () => {
    // The actual "blank pane" symptom: for front/side, the pre-fix camera pointed so far off-axis
    // that pose.center itself (dead-center of the intended view) could project way outside [-1, 1]
    // or behind the camera entirely.
    for (const axis of AXES) {
      const ndc = projectRelative(POSE, axis, [0, 0, 0])
      expect(Math.abs(ndc.x)).toBeLessThan(1e-6)
      expect(Math.abs(ndc.y)).toBeLessThan(1e-6)
    }
  })
})

// Regression for the owner-reported "ortho drag-pan is inverted" bug report: proves `orthoPan`'s
// "content follows the cursor" contract (its own doc comment, GUI.md's "Camera & projection") holds
// through the FULL render pipeline -- camera.lookAt + the NDC-x projection mirror above -- not just
// `orthoCamera.ts`'s pure math in isolation. A fixed world point's on-screen (canvas-pixel, y-down)
// position must move by exactly the same (dxPx, dyPx) the drag itself moved, for every axis, since a
// sign error in either `orthoPan` or the projection mirror they share would show up here even if
// `orthoCamera.test.ts`'s own `orthoPan` tests (which only check `pose.center`'s arithmetic, not the
// screen effect) still passed.
function screenPxOf(pose: OrthoPose, axis: OrthoAxis, worldPoint: [number, number, number], viewportPx: { width: number; height: number }) {
  const camera = new THREE.OrthographicCamera()
  applyOrthoCameraPose(camera, pose, axis, viewportPx)
  // Reflect the world point by R = diag(1,-1,1) (the content group's reflection) before projecting.
  const ndc = new THREE.Vector3(worldPoint[0], -worldPoint[1], worldPoint[2]).project(camera)
  return { x: ((ndc.x + 1) / 2) * viewportPx.width, y: ((1 - ndc.y) / 2) * viewportPx.height }
}

describe('orthoPan (rendered)', () => {
  it('a screen-space drag moves a fixed world point by the OPPOSITE screen delta (the view moves WITH the drag), for every axis', () => {
    const viewportPx = { width: 800, height: 600 }
    const worldPoint: [number, number, number] = [3, -4, 5]
    const dxPx = 10
    const dyPx = 6
    for (const axis of AXES) {
      const pose: OrthoPose = { center: [0, 0, 0], worldUnitsPerPixel: 2 }
      const before = screenPxOf(pose, axis, worldPoint, viewportPx)
      const after = screenPxOf(orthoPan(pose, axis, dxPx, dyPx), axis, worldPoint, viewportPx)
      expect(after.x - before.x).toBeCloseTo(-dxPx, 5)
      expect(after.y - before.y).toBeCloseTo(-dyPx, 5)
    }
  })
})

// Bug fix (see Viewport3D.test.ts's identical describe block): the AABB miss-fallback pick used to
// read raw `actors` -- a near-miss click near a staged-moved actor's NEW position could miss/hit the
// wrong actor, since `pickActor` tests `.bbox_lo`/`.bbox_hi` directly. Now derives from
// `effectiveActors`, the same staged-offset-applied array every position-driven overlay already uses.
describe('OrthoViewport -- AABB-fallback pick uses staged (effectiveActors), not raw actors', () => {
  it('performTapSelect passes effectiveActors (not raw actors) as the fallback-pick actors', () => {
    expect(ORTHOVIEWPORT_SOURCE).toMatch(/actors:\s*effectiveActors,\s*\n\s*triangleOwners,/)
  })
})

// Grid-increment movement (owner ruling) -- mirrors Viewport3D.test.ts's identical describe block.
describe('OrthoViewport -- grid-increment movement wiring', () => {
  it('gestureSnapRef is decided from the selection ONCE at pointerdown, via anySelectedIsBrush', () => {
    const onPointerDownBody = /const onPointerDown = useCallback\(\s*\(e: ReactPointerEvent<HTMLDivElement>\) => \{([\s\S]*?)\n    \},\n    \[/.exec(
      ORTHOVIEWPORT_SOURCE,
    )?.[1]
    expect(onPointerDownBody).toBeDefined()
    expect(onPointerDownBody).toMatch(/moveDeltaAccRef\.current = \[0, 0, 0\]/)
    expect(onPointerDownBody).toMatch(/gestureSnapRef\.current = anySelectedIsBrush\(selectedNames, actors\)/)
  })

  it('the move branch accumulates the RAW total, snaps only when gestureSnapRef says so, and recomputes from preGestureOffsetsRef (not stagedOffsetsRef)', () => {
    expect(ORTHOVIEWPORT_SOURCE).toMatch(/moveDeltaAccRef\.current = addVec3\(moveDeltaAccRef\.current, frameDelta\)/)
    expect(ORTHOVIEWPORT_SOURCE).toMatch(
      /const totalDelta = gestureSnapRef\.current\s*\n\s*\? snapVecToGrid\(moveDeltaAccRef\.current, baseGridSize\)\s*\n\s*: moveDeltaAccRef\.current/,
    )
    expect(ORTHOVIEWPORT_SOURCE).toMatch(
      /applyDelta\(preGestureOffsetsRef\.current, selectedNames, totalDelta, actors\)/,
    )
  })
})
