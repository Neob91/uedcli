/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'
import * as THREE from 'three'

import { cameraBasis } from './camera'
import type { CameraPose } from './camera'
import { applyCameraPose, WIREFRAME_LINE_HIT_WORLD_UNITS } from './viewportRender'

// This repo has no Canvas-in-test pattern (see `QuadLayout.test.tsx`'s own comment) -- Viewport3D
// owns a real `<Canvas>` and can't be rendered here the way `SelectionHighlight.test.tsx` renders
// `SurfaceSelectionHighlight` directly. `SelectionHighlight.test.tsx` already proves the component
// itself is geometry-agnostic (any owner/polyIndex arrays highlight correctly); what's specific to
// board item `mover-poly-select-in-movers-on-mode-not` is that Viewport3D actually WIRES a second
// instance to the Movers:on solid mesh's own arrays, gated the same as that mesh. Pinned as a
// source-text assertion (`toolbarLayout.test.ts`'s established pattern for this kind of gap).
const VIEWPORT3D_SOURCE = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'Viewport3D.tsx'), 'utf8')

describe('Viewport3D -- mover-poly selection highlight (mover-poly-select-in-movers-on-mode-not)', () => {
  it('wires a SECOND SurfaceSelectionHighlight at the Movers:on solid mesh\'s own geometry/owner arrays', () => {
    // Two SurfaceSelectionHighlight instances: one on the world mesh, one on the mover mesh.
    const count = (VIEWPORT3D_SOURCE.match(/<SurfaceSelectionHighlight/g) ?? []).length
    expect(count).toBe(2)
    expect(VIEWPORT3D_SOURCE).toMatch(
      /<SurfaceSelectionHighlight\s+bufferGeometry=\{moverGeometry\}\s+triangleOwners=\{moverTriangleOwners\}\s+trianglePolyIndex=\{moverTrianglePolyIndex\}/,
    )
  })

  it('gates the mover highlight identically to the mover solid mesh itself (both `showMoverSolid`)', () => {
    // The mover mesh and its highlight must share the exact same JSX gate, or the highlight can
    // exist (or not) independent of the geometry it's supposed to overlay.
    const moverMeshGate = /\{mode !== 'wireframe' && showMoverSolid && \(\s*<mesh ref=\{moverMeshRef\}/
    const moverHighlightGate =
      /\{mode !== 'wireframe' && showMoverSolid && \(\s*<SurfaceSelectionHighlight\s+bufferGeometry=\{moverGeometry\}/
    expect(VIEWPORT3D_SOURCE).toMatch(moverMeshGate)
    expect(VIEWPORT3D_SOURCE).toMatch(moverHighlightGate)
  })

  it('the mover highlight uses the mover mesh\'s own materials, not the world mesh\'s', () => {
    const moverHighlightBlock = /<SurfaceSelectionHighlight\s+bufferGeometry=\{moverGeometry\}[\s\S]*?\/>/.exec(
      VIEWPORT3D_SOURCE,
    )?.[0]
    expect(moverHighlightBlock).toBeDefined()
    expect(moverHighlightBlock).toContain('materials={activeMoverMaterials}')
  })
})

// Ctrl/Cmd-drag actor translation (Task 8, spec "Interaction design"): the branch-selection logic
// itself (does an additive drag with a mapped button resolve to a move, and does the accumulator
// math work) is pure and unit-tested directly in `dragStage.test.ts` -- these two source-text checks
// pin the WIRING facts that can't be exercised without a real `<Canvas>` (this file's own established
// pattern, see the top-of-file comment): the actor-move branch runs and returns BEFORE the camera
// dispatch (never falls through to also move the camera), and `postStage` fires from the existing
// onPointerUp boundary, not a second pointerup listener.
describe('Viewport3D -- Ctrl/Cmd-drag actor translation wiring', () => {
  it('resolves the actor-move axis and returns BEFORE the camera setPose dispatch in onDrag', () => {
    const onDragBody = /onDrag: \(dx, dy, buttons, altKey, additive\) => \{([\s\S]*?)\n      \},/.exec(
      VIEWPORT3D_SOURCE,
    )?.[1]
    expect(onDragBody).toBeDefined()
    const axisIdx = onDragBody!.indexOf('resolveActorMoveAxis')
    const setPoseIdx = onDragBody!.indexOf('setPose((prev) => resolveDrag(')
    expect(axisIdx).toBeGreaterThanOrEqual(0)
    expect(setPoseIdx).toBeGreaterThan(axisIdx) // the move branch is checked, and returns, first
    // The move branch's own `if (axis) { ... return }` sits entirely before setPose is ever reached.
    const returnIdx = onDragBody!.indexOf('return', axisIdx)
    expect(returnIdx).toBeGreaterThan(axisIdx)
    expect(returnIdx).toBeLessThan(setPoseIdx)
  })

  it('calls postStage exactly once, from the existing mouse onPointerUp boundary (no second pointerup listener)', () => {
    expect((VIEWPORT3D_SOURCE.match(/postStage\(/g) ?? []).length).toBe(1)
    expect((VIEWPORT3D_SOURCE.match(/onPointerUp = useCallback/g) ?? []).length).toBe(1)
    const onPointerUpBody = /const onPointerUp = useCallback\(\s*\(e: ReactPointerEvent<HTMLDivElement>\) => \{([\s\S]*?)\n    \},/.exec(
      VIEWPORT3D_SOURCE,
    )?.[1]
    expect(onPointerUpBody).toBeDefined()
    expect(onPointerUpBody).toContain('postStage(sessionId, locations)')
  })

  // Review finding: BrushOutlines/SelectionMarkers/DirectionalArrows/RadiiOverlays were fed
  // `actors={scene.actors}` directly, so a selected BRUSH (or its arrow/radii gizmos) got no visual
  // feedback at all during a Ctrl-drag -- only the point-actor marker sprite (patched inline, a
  // separate `stagedOffsets[actor.name] ?? actor.location` lookup, tested by the "position-driven
  // overlays" check below) moved. `effectiveActors` (`dragStage.ts`'s `applyStagedOffsets`) is the
  // fix: the SAME derived, staged-offset-aware actor list must reach all four.
  it('feeds effectiveActors (not the raw scene.actors) to every position-driven overlay consumer', () => {
    expect(VIEWPORT3D_SOURCE).toMatch(/<BrushOutlines\s+actors=\{effectiveActors\}/)
    expect(VIEWPORT3D_SOURCE).toMatch(/<SelectionMarkers actors=\{effectiveActors\}/)
    expect(VIEWPORT3D_SOURCE).toMatch(/<DirectionalArrows actors=\{effectiveActors\}/)
    expect(VIEWPORT3D_SOURCE).toMatch(/<RadiiOverlays actors=\{effectiveActors\}/)
    // None of the four still reads directly off scene.actors.
    expect(VIEWPORT3D_SOURCE).not.toMatch(/<BrushOutlines\s+actors=\{scene\.actors\}/)
    expect(VIEWPORT3D_SOURCE).not.toMatch(/<SelectionMarkers actors=\{scene\.actors\}/)
    expect(VIEWPORT3D_SOURCE).not.toMatch(/<DirectionalArrows actors=\{scene\.actors\}/)
    expect(VIEWPORT3D_SOURCE).not.toMatch(/<RadiiOverlays actors=\{scene\.actors\}/)
  })

  it('derives effectiveActors from applyStagedOffsets(scene.actors, stagedOffsets)', () => {
    expect(VIEWPORT3D_SOURCE).toContain('applyStagedOffsets(scene.actors, stagedOffsets)')
  })

  // Critical 2, final review fix wave: `stagedOffsets` used to be a private `useState` INSIDE this
  // component, so Discard/Save-success/Load-accept (App.tsx) could never actually clear what was
  // rendered here, and a drag in this pane was invisible in the other three. Fixed by lifting
  // ownership to App.tsx and threading it down as props -- pinned here since a regression (a local
  // `useState<Record<string, Vec3>>` creeping back in) can't be caught by any prop-shape check alone.
  it('does not own a private useState for stagedOffsets any more -- it is a prop', () => {
    expect(VIEWPORT3D_SOURCE).not.toMatch(/const \[stagedOffsets, setStagedOffsets\] = useState/)
    expect(VIEWPORT3D_SOURCE).toMatch(/stagedOffsets,\s*\n\s*stagedOffsetsRef,\s*\n\s*setStagedOffsets,/)
  })
})

// Final review fix wave, Critical 1: onDrag fired on every pointer-move unconditionally, with no
// tap-vs-drag threshold of its own -- see OrthoViewport.test.ts's identical describe block for the
// full rationale (this pane's own move branch has the SAME bug/fix, just gated by
// `resolveActorMoveAxis`+a `buttons`-keyed combo instead of ortho's single `additive` gate).
describe('Viewport3D -- Ctrl/Cmd-drag tap-vs-drag threshold gating (Critical 1)', () => {
  it('gates the move branch on accumulateMoveDragFrame before applying any delta', () => {
    const onDragBody = /onDrag: \(dx, dy, buttons, altKey, additive\) => \{([\s\S]*?)\n      \},/.exec(
      VIEWPORT3D_SOURCE,
    )?.[1]
    expect(onDragBody).toBeDefined()
    const frameIdx = onDragBody!.indexOf('accumulateMoveDragFrame(moveDragAccRef.current, dx, dy)')
    const moveIdx = onDragBody!.indexOf('moveAlongAxis(')
    expect(frameIdx).toBeGreaterThanOrEqual(0)
    expect(moveIdx).toBeGreaterThan(frameIdx) // the threshold check happens BEFORE any move is applied
    expect(VIEWPORT3D_SOURCE).toMatch(/if \(camera && rect && primarySelectedActor\) \{[\s\S]*?dragMovedRef\.current = true[\s\S]*?\}/)
  })

  it('resets the threshold accumulator AND snapshots the pre-gesture offsets fresh at every pointerdown', () => {
    expect(VIEWPORT3D_SOURCE).toContain('moveDragAccRef.current = freshMoveDragAccumulator()')
    expect(VIEWPORT3D_SOURCE).toContain('preGestureOffsetsRef.current = stagedOffsetsRef.current')
  })
})

// Important 3, final review fix wave: postStage had no .catch() at all.
describe('Viewport3D -- postStage error handling (Important 3)', () => {
  it('chains a .catch() off the SAME postStage call that reverts the offset and surfaces the error', () => {
    const postStageIdx = VIEWPORT3D_SOURCE.indexOf('postStage(sessionId, locations)')
    expect(postStageIdx).toBeGreaterThanOrEqual(0)
    const catchIdx = VIEWPORT3D_SOURCE.indexOf('.catch(', postStageIdx)
    expect(catchIdx).toBeGreaterThan(postStageIdx)
    const revertIdx = VIEWPORT3D_SOURCE.indexOf('setStagedOffsets(preGestureOffsetsRef.current)', catchIdx)
    const errorIdx = VIEWPORT3D_SOURCE.indexOf('onStageError?.(String(e2))', catchIdx)
    expect(revertIdx).toBeGreaterThan(catchIdx)
    expect(errorIdx).toBeGreaterThan(catchIdx)
  })
})

// Widened hit-test tolerance (owner report, live testing: brush-outline selection in wireframe mode
// needed near-pixel-exact clicks) -- pins the value so a future edit can't silently narrow it back.
describe('WIREFRAME_LINE_HIT_WORLD_UNITS', () => {
  it('is wider than the original 4-world-unit threshold', () => {
    expect(WIREFRAME_LINE_HIT_WORLD_UNITS).toBe(8)
  })
})

// Pins the left-handed-world orientation fix (owner bug report: "meshes render reverted (mirror
// image)") against real three.js math -- no WebGL context needed, `Vector3.project` is pure matrix
// arithmetic. The world is left-handed (X forward, Y right, Z up); all content is drawn inside a
// reflected `<group scale={[1,-1,1]}>` (R = diag(1,-1,1)) and `applyCameraPose` reflects the camera
// pose by the same R. A correct camera must render a point offset toward `cameraBasis.right` on the
// RIGHT of the screen (positive NDC.x) and toward `up` at the TOP (positive NDC.y) -- verified
// against a fresh `level photo --native` (render.rs) of the same poses. Because the content is
// reflected, the on-screen position of a game-coord point is the projection of R*point, so the test
// reflects the point by R (negate Y) before projecting.
function projectRelative(pose: CameraPose, sideOffset: [number, number, number]): THREE.Vector3 {
  const camera = new THREE.PerspectiveCamera(75, 1, 1, 131072)
  applyCameraPose(camera, pose)
  const { forward } = cameraBasis(pose.pitch, pose.yaw)
  const depthAlongForward = 500
  const point = new THREE.Vector3(
    pose.position[0] + forward[0] * depthAlongForward + sideOffset[0],
    -(pose.position[1] + forward[1] * depthAlongForward + sideOffset[1]), // R = diag(1,-1,1): the group reflects Y
    pose.position[2] + forward[2] * depthAlongForward + sideOffset[2],
  )
  return point.project(camera)
}

describe('applyCameraPose', () => {
  it('renders a point offset toward cameraBasis.right on the right of the screen (positive NDC.x)', () => {
    const poses: CameraPose[] = [
      { position: [0, 0, 0], pitch: 0, yaw: 0 },
      { position: [0, -500, 200], pitch: -10, yaw: 90 },
      { position: [-300, 50, 700], pitch: -75, yaw: 0 }, // the near-top-down pose the bug/fix was pinned against
    ]
    for (const pose of poses) {
      const { right } = cameraBasis(pose.pitch, pose.yaw)
      const ndc = projectRelative(pose, [right[0] * 350, right[1] * 350, right[2] * 350])
      expect(ndc.x).toBeGreaterThan(0)
    }
  })

  it('renders a point offset toward cameraBasis.up higher on the screen (positive NDC.y)', () => {
    const poses: CameraPose[] = [
      { position: [0, 0, 0], pitch: 0, yaw: 0 },
      { position: [0, -500, 200], pitch: -10, yaw: 90 },
    ]
    for (const pose of poses) {
      const { up } = cameraBasis(pose.pitch, pose.yaw)
      const ndc = projectRelative(pose, [up[0] * 350, up[1] * 350, up[2] * 350])
      expect(ndc.y).toBeGreaterThan(0)
    }
  })

  it('looks along R*cameraBasis.forward (the pose is reflected into the content group space)', () => {
    const pose: CameraPose = { position: [-300, 50, 700], pitch: -75, yaw: 0 }
    const camera = new THREE.PerspectiveCamera(75, 1, 1, 131072)
    applyCameraPose(camera, pose)
    const { forward } = cameraBasis(pose.pitch, pose.yaw)
    const lookDir = new THREE.Vector3(0, 0, -1).transformDirection(camera.matrixWorld)
    // Camera posed in reflected space: it looks along R*forward = (fx, -fy, fz).
    expect(lookDir.x).toBeCloseTo(forward[0], 5)
    expect(lookDir.y).toBeCloseTo(-forward[1], 5)
    expect(lookDir.z).toBeCloseTo(forward[2], 5)
  })
})

// Bug fix (reported live, post-merge; found auditing for more of the same Inspector/mesh-body
// divergence class the Ctrl/Cmd-drag feature already had two fixes for): `primarySelectedActor` (the
// Alt-drag orbit pivot's target) and the AABB miss-fallback pick both used to read raw `scene.actors`
// -- a staged-moved actor's Alt-drag orbit pivoted around its PRE-move position, and a near-miss
// click near its NEW position could miss/hit the wrong actor, since `pickActor` tests
// `.bbox_lo`/`.bbox_hi` directly. Both now derive from `effectiveActors` (the same staged-offset-
// applied array every position-driven overlay already uses) -- pinned as source-text, the same
// no-Canvas-in-test pattern this file's other wiring tests already use.
describe('Viewport3D -- orbit pivot and AABB-fallback pick use staged (effectiveActors), not raw scene.actors', () => {
  it('primarySelectedActor searches effectiveActors, not scene.actors', () => {
    const match = /const primarySelectedActor = useMemo\(\s*\(\) => (\w+)\.find/.exec(VIEWPORT3D_SOURCE)
    expect(match).toBeDefined()
    expect(match![1]).toBe('effectiveActors')
  })

  it('effectiveActors is declared BEFORE primarySelectedActor (so it can depend on it)', () => {
    const effIdx = VIEWPORT3D_SOURCE.indexOf('const effectiveActors = useMemo(')
    const primaryIdx = VIEWPORT3D_SOURCE.indexOf('const primarySelectedActor = useMemo(')
    expect(effIdx).toBeGreaterThan(0)
    expect(primaryIdx).toBeGreaterThan(effIdx)
  })

  it('performTapSelect passes effectiveActors (not scene.actors) as the fallback-pick actors', () => {
    expect(VIEWPORT3D_SOURCE).toMatch(/actors:\s*effectiveActors,\s*\n\s*triangleOwners,/)
  })
})

// Grid-increment movement (owner ruling): "brush movement should move in grid-size increments, not
// continuously. Non-brush actors are fine to move continuously... When multiple actors are selected,
// and some of them are brush actors, they should always move in grid-size increments." The pure
// mechanism (`anySelectedIsBrush`, `snapVecToGrid`, `addVec3`) is unit-tested directly in
// dragStage.test.ts -- these pin the WIRING facts specific to this pane, the same no-Canvas-in-test
// pattern this file's other wiring tests already use.
describe('Viewport3D -- grid-increment movement wiring', () => {
  it('gestureSnapRef is decided from the selection ONCE at pointerdown, via anySelectedIsBrush', () => {
    const onPointerDownBody = /const onPointerDown = useCallback\(\s*\(e: ReactPointerEvent<HTMLDivElement>\) => \{([\s\S]*?)\n    \},\n    \[/.exec(
      VIEWPORT3D_SOURCE,
    )?.[1]
    expect(onPointerDownBody).toBeDefined()
    expect(onPointerDownBody).toMatch(/moveDeltaAccRef\.current = \[0, 0, 0\]/)
    expect(onPointerDownBody).toMatch(/gestureSnapRef\.current = anySelectedIsBrush\(selectedNames, scene\.actors\)/)
  })

  it('the move branch accumulates the RAW total, snaps only when gestureSnapRef says so, and recomputes from preGestureOffsetsRef (not stagedOffsetsRef)', () => {
    expect(VIEWPORT3D_SOURCE).toMatch(/moveDeltaAccRef\.current = addVec3\(moveDeltaAccRef\.current, frameDelta\)/)
    expect(VIEWPORT3D_SOURCE).toMatch(
      /const totalDelta = gestureSnapRef\.current\s*\n\s*\? snapVecToGrid\(moveDeltaAccRef\.current, baseGridSize\)\s*\n\s*: moveDeltaAccRef\.current/,
    )
    expect(VIEWPORT3D_SOURCE).toMatch(
      /applyDelta\(preGestureOffsetsRef\.current, selectedNames, totalDelta, scene\.actors\)/,
    )
  })

  it('baseGridSize defaults to DEFAULT_GRID_SIZE (the same value the ortho grid dropdown defaults to)', () => {
    expect(VIEWPORT3D_SOURCE).toMatch(/baseGridSize = DEFAULT_GRID_SIZE,/)
  })
})

describe('Viewport3D -- move-mode-aware camera dispatch and ControlCluster wiring (viewport-control-redesign-icon-cluster-replaces)', () => {
  it('no longer imports or renders the deleted MoveJoystick/TouchFlyInput', () => {
    expect(VIEWPORT3D_SOURCE).not.toContain('MoveJoystick')
    expect(VIEWPORT3D_SOURCE).not.toContain('TouchFlyInput')
    expect(VIEWPORT3D_SOURCE).not.toContain("from './joystick'")
  })

  it('renders ControlCluster with the move-mode/shading-mode/activeTray wiring', () => {
    expect(VIEWPORT3D_SOURCE).toMatch(/<ControlCluster\b/)
    expect(VIEWPORT3D_SOURCE).toContain('moveMode={moveMode}')
    expect(VIEWPORT3D_SOURCE).toContain('onCycleMoveMode={() => setMoveMode(cycleMoveMode)}')
    expect(VIEWPORT3D_SOURCE).toContain('shadingMode={mode}')
    expect(VIEWPORT3D_SOURCE).toContain('buildSolved={buildSolved}')
    expect(VIEWPORT3D_SOURCE).toContain('onSelectShadingMode={onSelectMode}')
    expect(VIEWPORT3D_SOURCE).toContain('activeTray={activeTray}')
    expect(VIEWPORT3D_SOURCE).toContain('onActiveTrayChange={onActiveTrayChange}')
  })

  it('moveMode is Viewport3D\'s own local state, not a prop', () => {
    expect(VIEWPORT3D_SOURCE).toMatch(/const \[moveMode, setMoveMode\] = useState<MoveMode>\('fly'\)/)
  })

  it('the desktop drag dispatch delegates to resolveDrag, passing moveMode and orbitPivot', () => {
    expect(VIEWPORT3D_SOURCE).toContain(
      'setPose((prev) => resolveDrag(prev, dx, dy, buttons, altKey, moveMode, orbitPivot))',
    )
  })

  it('the two-finger touch dispatch delegates to resolveTwoFingerDrag, passing moveMode', () => {
    expect(VIEWPORT3D_SOURCE).toContain(
      'setPose((prevPose) => zoom(resolveTwoFingerDrag(prevPose, panDx, panDy, moveMode), zoomDelta))',
    )
  })

  it('single-finger touch still calls look directly, unaffected by moveMode', () => {
    expect(VIEWPORT3D_SOURCE).toContain('setPose((prevPose) => look(prevPose, dx, dy))')
  })
})

// Re-verify the Ctrl/Cmd-drag actor-move priority ordering still holds after the dispatch change --
// same intent as the pre-existing 'Ctrl/Cmd-drag actor translation wiring' describe block above,
// updated for resolveDrag's call shape (it no longer contains a literal `setPose((prev) => {` -- see
// this task's own note on why that pre-existing assertion had to change, not just gain new ones).
//
// Both tests below locate the REAL `return` statement (line ~472 in the current source: a bare
// `return` on its own line, unconditionally exiting the `if (axis) { ... }` block) via a regex
// anchored to the start of a line -- `/^\s*return\b/m` -- rather than a plain `.indexOf('return', ...)`.
// The actor-move branch's own leading comment literally contains the word `return` in backticks
// ("... still `return` unconditionally either way ..."), mid-line inside a `//` comment; a plain
// indexOf match lands there instead, well before the real return statement, and silently truncates
// everything after it out of the slice these tests inspect.
describe('Viewport3D -- Ctrl/Cmd-drag priority survives the move-mode dispatch change', () => {
  it('resolves the actor-move axis and returns BEFORE the camera setPose dispatch in onDrag', () => {
    const onDragBody = /onDrag: \(dx, dy, buttons, altKey, additive\) => \{([\s\S]*?)\n      \},/.exec(
      VIEWPORT3D_SOURCE,
    )?.[1]
    expect(onDragBody).toBeDefined()
    const axisIdx = onDragBody!.indexOf('resolveActorMoveAxis')
    const setPoseIdx = onDragBody!.indexOf('setPose((prev) => resolveDrag(')
    expect(axisIdx).toBeGreaterThanOrEqual(0)
    expect(setPoseIdx).toBeGreaterThan(axisIdx)
    const returnMatch = /^\s*return\b/m.exec(onDragBody!.slice(axisIdx))
    expect(returnMatch).not.toBeNull()
    const returnIdx = axisIdx + returnMatch!.index
    expect(returnIdx).toBeGreaterThan(axisIdx)
    expect(returnIdx).toBeLessThan(setPoseIdx)
  })

  // Spec ("Two movement mechanisms this redesign does not touch"): Ctrl/Cmd-drag actor-move must
  // behave identically in both move-modes. The ordering test above already proves it always runs
  // and returns BEFORE moveMode is even consulted (resolveDrag isn't reached) -- this test pins
  // that structurally, by asserting the actor-move branch itself never references moveMode at all,
  // so there is no code path by which it COULD vary with the mode.
  it('the actor-move branch never reads moveMode -- its behavior cannot vary by move-mode', () => {
    const onDragBody = /onDrag: \(dx, dy, buttons, altKey, additive\) => \{([\s\S]*?)\n      \},/.exec(
      VIEWPORT3D_SOURCE,
    )?.[1]
    expect(onDragBody).toBeDefined()
    const axisIdx = onDragBody!.indexOf('resolveActorMoveAxis')
    const returnMatch = /^\s*return\b/m.exec(onDragBody!.slice(axisIdx))
    expect(returnMatch).not.toBeNull()
    const returnIdx = axisIdx + returnMatch!.index
    const actorMoveBranch = onDragBody!.slice(axisIdx, returnIdx)
    // Sanity check that the slice actually reaches the real logic this test means to cover, not
    // just the leading comment -- guards against this test silently degrading back to the bug above.
    expect(actorMoveBranch).toContain('accumulateMoveDragFrame')
    expect(actorMoveBranch).toContain('worldUnitsPerPixelAt')
    expect(actorMoveBranch).toContain('applyDelta')
    expect(actorMoveBranch).not.toContain('moveMode')
  })
})
