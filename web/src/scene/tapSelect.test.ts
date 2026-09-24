// Regression suite for `dev/docs/board/to-build/gui-pick-selection-regression-test-suite/` --
// deterministic, real-`resolveTapSelect` click-AT-vs-click-NEXT-TO coverage for the GUI pick/
// selection scenarios this campaign fixed (GUI-PARITY.md, `dev/docs/board/done/*`). Unlike
// `selection.test.ts` (which unit-tests the picking ALGORITHMS -- `pickHit`/`nearestScreenHit`/
// `isTransparentPixel` -- with hand-built candidate lists), these tests drive the REAL
// `tapSelect.ts` entry point with a real `THREE.Raycaster`/`THREE.Camera` against small synthetic
// scenes (no WebGL context needed -- raycasting is plain math), so a regression in how the pieces
// are WIRED TOGETHER (not just the algorithm itself) would be caught here too.
//
// All scenes use one shared convention: an orthographic camera at `(0, 0, 10)` looking straight
// down -Z with no roll, so world XY maps linearly to screen pixels -- `worldToClient` below is the
// exact inverse of `tapSelect.ts`'s own NDC conversion. This keeps "click at world point P" and
// "click 3 units to the side of P" simple, literal, and exactly what the board item asked for
// ("clicking AT a sprite and NEXT TO a sprite, and asserting what gets selected").
import { describe, expect, it } from 'vitest'
import * as THREE from 'three'

import type { BrushHighlight, SceneActor } from '../api'
import { resolveTapSelect } from './tapSelect'
import type { TapSelectParams } from './tapSelect'
import { toggleSelection } from './selectionSet'
import { surfaceKey } from './selectionSet'

const FAKE_BRUSH: BrushHighlight = { csg_class: 'add', color: [1, 1, 1], polys: [], local_origin: [0, 0, 0] }

function actor(name: string, overrides: Partial<SceneActor> = {}): SceneActor {
  return {
    name,
    cls: 'Engine.Brush',
    bbox_lo: [-1000, -1000, -1000],
    bbox_hi: [-999, -999, -999], // far away by default -- a test opts a specific actor INTO the AABB fallback explicitly
    location: [0, 0, 0],
    rotation: [0, 0, 0],
    folder: null,
    labels: [],
    order_value: 'm',
    csg_rank: 1,
    props: [],
    brush: FAKE_BRUSH,
    sprite: null,
    radii: null,
    is_mover: false,
    directional_arrow: null,
    ...overrides,
  }
}

// Half-extent 10 world units mapped onto a 200x200px viewport -- 10px per world unit, so a 5px
// screen distance (UED22's own ~5px hit box, `selection.ts`'s `MOVER_LINE_HIT_BOX_PX`) is exactly
// 0.5 world units. Chosen so every scenario below can reason in whole world units.
const HALF_EXTENT = 10
const VIEWPORT_PX = 200

function makeCamera(): THREE.OrthographicCamera {
  const camera = new THREE.OrthographicCamera(-HALF_EXTENT, HALF_EXTENT, HALF_EXTENT, -HALF_EXTENT, 0.1, 1000)
  camera.position.set(0, 0, 10)
  camera.lookAt(0, 0, 0)
  camera.updateProjectionMatrix()
  camera.updateMatrixWorld(true)
  return camera
}

const RECT = { left: 0, top: 0, width: VIEWPORT_PX, height: VIEWPORT_PX, right: VIEWPORT_PX, bottom: VIEWPORT_PX, x: 0, y: 0 } as DOMRect

/** Inverse of `tapSelect.ts`'s NDC conversion, for this file's fixed ortho camera/rect -- lets every
 * test say "click at world point (x, y)" instead of hand-computing NDC/pixel math per case. */
function worldToClient(x: number, y: number): { clientX: number; clientY: number } {
  const ndcX = x / HALF_EXTENT
  const ndcY = y / HALF_EXTENT
  return {
    clientX: RECT.left + ((ndcX + 1) / 2) * RECT.width,
    clientY: RECT.top + ((1 - ndcY) / 2) * RECT.height,
  }
}

/** A flat, double-sided quad (2 triangles) in the z=0-ish plane, all owned by one actor/poly --
 * `resolveHitSurface`'s `triangleOwners`/`trianglePolyIndex` need one entry per triangle. */
function quadMesh(x0: number, y0: number, x1: number, y1: number, z: number, owner: string, polyIndex: number) {
  const positions = new Float32Array([
    x0, y0, z, x1, y0, z, x1, y1, z,
    x0, y0, z, x1, y1, z, x0, y1, z,
  ])
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ side: THREE.DoubleSide }))
  return { mesh, triangleOwners: [owner, owner] as (string | null)[], trianglePolyIndex: [polyIndex, polyIndex] as (number | null)[] }
}

/** A square outline as 4 `LineSegments`, matching `brushRings.ts`'s `mergeThinRings` shape --
 * `userData.segmentOwners` is what `tapSelect.ts`/`resolveSegmentHitActor` key off of. */
function outlineSquare(halfSize: number, z: number, owner: string, alwaysOnTop: boolean): THREE.LineSegments {
  const h = halfSize
  const positions = new Float32Array([
    -h, -h, z, h, -h, z,
    h, -h, z, h, h, z,
    h, h, z, -h, h, z,
    -h, h, z, -h, -h, z,
  ])
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  const line = new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({ depthTest: !alwaysOnTop }))
  line.userData.segmentOwners = [owner, owner, owner, owner]
  return line
}

/** Every `TapSelectParams` field defaults to "not present" -- a test overrides only what its scene
 * actually wires, mirroring how `Viewport3D.tsx` passes `null`/`[]` for whatever isn't mounted in
 * the current mode (e.g. `meshObject` is `null` in wireframe mode, since the `<mesh>` itself isn't
 * rendered then -- see `Viewport3D.tsx`'s `mode !== 'wireframe' && <mesh ref={meshRef} .../>`). */
function baseParams(overrides: Partial<TapSelectParams>): TapSelectParams {
  return {
    camera: makeCamera(),
    rect: RECT,
    clientX: 0,
    clientY: 0,
    additive: false,
    shiftKey: false,
    mode: 'lit',
    lineThreshold: 0.1,
    meshObject: null,
    moverMeshObject: null,
    moverTriangleOwners: [],
    moverTrianglePolyIndex: [],
    meshPickObject: null,
    meshTriangleOwners: [],
    meshTrianglePolyIndex: [],
    meshEdgePickObject: null,
    meshEdgeOwners: [],
    meshEdgePolyIndex: [],
    markerObjects: [],
    brushObjects: [],
    moverOutlineObjects: [],
    actors: [],
    triangleOwners: [],
    trianglePolyIndex: [],
    ...overrides,
  }
}

// ---------------------------------------------------------------------------------------------
// Scenario 4: wireframe-mode brush selection hit-tests LINES only, never the filled interior.
// Board `wireframe-brush-selection-should-hit-test-lines`.
// ---------------------------------------------------------------------------------------------
describe('resolveTapSelect -- wireframe mode selects a brush by its outline lines, not its silhouette interior', () => {
  // The bbox DELIBERATELY covers the outline's own interior (unlike this file's default far-away
  // bbox) -- proven reachable by the second test below, so the first test's "deselects" result is
  // known to come from the wireframe-mode AABB exclusion, not merely an unreachable box.
  const brush = actor('Brush1', { bbox_lo: [-3, -3, -3], bbox_hi: [3, 3, 3] })
  const outline = outlineSquare(2, 0, 'Brush1', false)

  it('clicking ON the outline (the bottom edge) selects the brush', () => {
    const { clientX, clientY } = worldToClient(0, -2) // midpoint of the bottom edge
    const action = resolveTapSelect(
      baseParams({ mode: 'wireframe', clientX, clientY, brushObjects: [outline], actors: [brush] }),
    )
    expect(action).toEqual({ kind: 'select-actor', name: 'Brush1', additive: false })
  })

  it('clicking in the OPEN INTERIOR, far from any line, does not select the brush -- it deselects', () => {
    const { clientX, clientY } = worldToClient(0, 0) // dead center, 2 world units from every edge
    const action = resolveTapSelect(
      baseParams({ mode: 'wireframe', clientX, clientY, brushObjects: [outline], actors: [brush] }),
    )
    // No meshObject is ever mounted in wireframe mode (Viewport3D.tsx), and the AABB fallback
    // explicitly excludes brush actors in wireframe mode -- so a genuine miss on the outline lines
    // must fall all the way through to "hit nothing," not silently select the brush by its bbox.
    expect(action).toEqual({ kind: 'deselect' })
  })

  it('the SAME click, SAME bbox, in a non-wireframe mode with Shift DOES hit the AABB fallback', () => {
    // Proves the bbox above is genuinely reachable -- so the wireframe test's 'deselect' result
    // really is the wireframe-mode brush exclusion doing its job, not an unreachable box that would
    // deselect either way.
    const { clientX, clientY } = worldToClient(0, 0)
    const action = resolveTapSelect(
      baseParams({ mode: 'lit', shiftKey: true, clientX, clientY, actors: [brush] }),
    )
    expect(action).toEqual({ kind: 'select-actor', name: 'Brush1', additive: true })
  })

  it('clicking just outside the square entirely (not near the brush at all) also deselects', () => {
    const { clientX, clientY } = worldToClient(8, 8)
    const action = resolveTapSelect(
      baseParams({ mode: 'wireframe', clientX, clientY, brushObjects: [outline], actors: [brush] }),
    )
    expect(action).toEqual({ kind: 'deselect' })
  })
})

// ---------------------------------------------------------------------------------------------
// Scenario 5: a Mover's always-on-top outline wins a click that ALSO lands a real precise hit on
// a poly directly behind/at it -- this is the mechanism that actually closed `mover-near-
// brush803-unclickable-in-wireframe-2d`'s "poly, not another line, sits right next to the Mover"
// shape (`selection.ts`'s `pickHit` doc comment, Bug A). It needs a real FILLED poly, so it
// exercises mode='lit' (a brush's own poly is never a raycast candidate in wireframe mode; see the
// previous describe block). Confirmed by mutation: reverting EITHER of `pickHit`'s two win rules
// for an always-on-top line (`moverBeatsPoly`'s absolute cutoff, or the ordinary alwaysOnTop
// relative rule -- here they overlap, since the click lands exactly on the line) fails this test.
// ---------------------------------------------------------------------------------------------
describe('resolveTapSelect -- a Mover outline beats a coincident poly within the hit box', () => {
  const wall = actor('Brush803')
  const mover = actor('DeusExMover4', { is_mover: true })
  const { mesh: wallMesh, triangleOwners, trianglePolyIndex } = quadMesh(-5, -5, 5, 5, 0, 'Brush803', 0)
  const moverOutline = outlineSquare(1, 0, 'DeusExMover4', true)

  it('clicking exactly on the Mover outline (which sits on top of the wall poly there) selects the Mover, not the wall behind it', () => {
    const { clientX, clientY } = worldToClient(0, 1) // the outline square's top edge, midpoint -- also inside the wall quad
    const action = resolveTapSelect(
      baseParams({
        mode: 'lit', // a real poly is only ever a raycast candidate outside wireframe mode
        clientX, clientY,
        meshObject: wallMesh, // the real competing precise hit -- without this the Mover line wins trivially either way
        triangleOwners, trianglePolyIndex,
        moverOutlineObjects: [moverOutline],
        actors: [wall, mover],
        lineThreshold: 0.1,
      }),
    )
    expect(action).toEqual({ kind: 'select-actor', name: 'DeusExMover4', additive: false })
  })

  it('clicking on the wall poly well away from the Mover outline selects the wall, not the Mover', () => {
    const { clientX, clientY } = worldToClient(4, -4) // far corner of the wall quad, nowhere near the 1-unit square
    const action = resolveTapSelect(
      baseParams({
        mode: 'lit',
        clientX, clientY,
        meshObject: wallMesh,
        triangleOwners, trianglePolyIndex,
        moverOutlineObjects: [moverOutline],
        actors: [wall, mover],
        lineThreshold: 1.0,
      }),
    )
    expect(action).toEqual({ kind: 'select-surface', actor: 'Brush803', polyIndex: 0, additive: false })
  })
})

// ---------------------------------------------------------------------------------------------
// Scenario 8b: a Mover's always-visible outline is selectable in PLAIN NON-WIREFRAME mode too
// (Movers:on off) -- not just in wireframe mode. Board `mover-not-selectable-via-wireframe-click`.
// ---------------------------------------------------------------------------------------------
describe('resolveTapSelect -- a Mover outline is a click target outside wireframe mode too', () => {
  it('clicking the Mover outline in mode=lit (no solid Mover mesh mounted) selects the Mover', () => {
    const mover = actor('DeusExMover4', { is_mover: true })
    const moverOutline = outlineSquare(1, 0, 'DeusExMover4', true)
    const { clientX, clientY } = worldToClient(1, 0) // the outline's right edge, midpoint
    const action = resolveTapSelect(
      baseParams({
        mode: 'lit',
        clientX, clientY,
        moverOutlineObjects: [moverOutline], // wired in every mode, per tapSelect.ts's own doc comment
        actors: [mover],
      }),
    )
    expect(action).toEqual({ kind: 'select-actor', name: 'DeusExMover4', additive: false })
  })

  it('the SAME outline is not a candidate at all when the caller omits it (old, unfixed wiring)', () => {
    const mover = actor('DeusExMover4', { is_mover: true })
    const { clientX, clientY } = worldToClient(1, 0)
    const action = resolveTapSelect(
      baseParams({ mode: 'lit', clientX, clientY, moverOutlineObjects: [], actors: [mover] }),
    )
    expect(action).toEqual({ kind: 'deselect' })
  })
})

// ---------------------------------------------------------------------------------------------
// Scenario 8a: a Mover's own solid mesh (Movers:on) is a real pick target, winning over whatever
// brush sits behind it. Board `mover-polys-unselectable-in-movers-on-mode`.
// ---------------------------------------------------------------------------------------------
describe('resolveTapSelect -- a Mover\'s Movers:on solid poly resolves to the Mover, not the brush behind it', () => {
  const wall = actor('Brush803')
  const mover = actor('DeusExMover4', { is_mover: true })
  // The wall sits FARTHER from the camera (z=-5); the Mover's own solid face sits at z=0, closer to
  // the camera (which is at z=+10 looking down -Z) -- so a real raycast hits the Mover face first,
  // exactly like the real door-in-a-wall-opening geometry this bug was about.
  const { mesh: wallMesh, triangleOwners, trianglePolyIndex } = quadMesh(-5, -5, 5, 5, -5, 'Brush803', 0)
  const { mesh: moverMesh, triangleOwners: moverOwners, trianglePolyIndex: moverPolyIndex } = quadMesh(-1, -1, 1, 1, 0, 'DeusExMover4', 2)

  it('clicking the Mover\'s own face (over the wall opening) resolves to the Mover\'s surface', () => {
    const { clientX, clientY } = worldToClient(0, 0)
    const action = resolveTapSelect(
      baseParams({
        mode: 'lit',
        clientX, clientY,
        meshObject: wallMesh, triangleOwners, trianglePolyIndex,
        moverMeshObject: moverMesh, moverTriangleOwners: moverOwners, moverTrianglePolyIndex: moverPolyIndex,
        actors: [wall, mover],
      }),
    )
    expect(action).toEqual({ kind: 'select-surface', actor: 'DeusExMover4', polyIndex: 2, additive: false })
  })

  it('clicking the wall OUTSIDE the Mover\'s footprint still resolves to the wall', () => {
    const { clientX, clientY } = worldToClient(4, 4) // outside the Mover's -1..1 square, still on the wall
    const action = resolveTapSelect(
      baseParams({
        mode: 'lit',
        clientX, clientY,
        meshObject: wallMesh, triangleOwners, trianglePolyIndex,
        moverMeshObject: moverMesh, moverTriangleOwners: moverOwners, moverTrianglePolyIndex: moverPolyIndex,
        actors: [wall, mover],
      }),
    )
    expect(action).toEqual({ kind: 'select-surface', actor: 'Brush803', polyIndex: 0, additive: false })
  })
})

// ---------------------------------------------------------------------------------------------
// Scenario 6: a point-actor sprite's click hit-test respects its icon's transparent padding --
// click AT the drawn icon selects it, click at the (transparent) edge of its square billboard does
// not. Board `point-actor-sprite-picking-ignores-sprite-alpha`.
// ---------------------------------------------------------------------------------------------
describe('resolveTapSelect -- sprite alpha-aware picking: click AT the icon vs. click NEXT TO it (transparent padding)', () => {
  // A minimal fake canvas: opaque disk in the middle (the "drawn icon"), transparent everywhere
  // else (the icon's square billboard padding) -- `isSpriteHitTransparent` only needs
  // `getContext('2d')` + `getImageData`, never a real `HTMLCanvasElement`.
  function fakeIconCanvas(size: number, radius: number) {
    return {
      width: size,
      height: size,
      getContext: () => ({
        getImageData: (x: number, y: number) => {
          const dx = x - size / 2
          const dy = y - size / 2
          const alpha = Math.hypot(dx, dy) < radius ? 255 : 0
          return { data: [0, 0, 0, alpha] }
        },
      }),
    }
  }

  function makeSprite(actorName: string): THREE.Sprite {
    const map = new THREE.Texture()
    // Real `HTMLCanvasElement` isn't available under jsdom's default (no `canvas` package) --
    // `isSpriteHitTransparent` only calls `getContext`/`getImageData`, so a plain object with
    // those two members is a faithful, minimal stand-in.
    ;(map as unknown as { image: unknown }).image = fakeIconCanvas(64, 20)
    const material = new THREE.SpriteMaterial({ map })
    const sprite = new THREE.Sprite(material)
    sprite.scale.set(2, 2, 1) // a 2x2-world-unit billboard, matching this file's whole-unit convention
    // `tapSelect.ts` resolves a marker-sprite hit via `userData.actorName`, exactly like
    // `PointActorMarker.tsx`'s real `<sprite userData={{ actorName: actor.name }}>` wiring
    // (`Viewport3D.tsx`/`OrthoViewport.tsx`) -- without it, the hit falls through unresolved.
    sprite.userData.actorName = actorName
    sprite.updateMatrixWorld(true)
    return sprite
  }

  it('clicking AT the sprite\'s center (the drawn, opaque icon) selects the actor', () => {
    const light = actor('HKMarketLight1', { brush: null })
    const sprite = makeSprite('HKMarketLight1')
    const { clientX, clientY } = worldToClient(0, 0)
    const action = resolveTapSelect(
      baseParams({ mode: 'lit', clientX, clientY, markerObjects: [sprite], actors: [light] }),
    )
    expect(action).toEqual({ kind: 'select-actor', name: 'HKMarketLight1', additive: false })
  })

  it('clicking NEXT TO the icon -- inside the sprite\'s square billboard, but in its transparent padding -- does not select it', () => {
    const light = actor('HKMarketLight1', { brush: null })
    const sprite = makeSprite('HKMarketLight1')
    const { clientX, clientY } = worldToClient(-0.95, -0.95) // corner of the 2x2 billboard, well outside the r=20/64 disk
    const action = resolveTapSelect(
      baseParams({ mode: 'lit', clientX, clientY, markerObjects: [sprite], actors: [light] }),
    )
    // The point actor's own AABB is a zero-size point at its Location (not near this click), so
    // this falls all the way through to a genuine miss -- always `'deselect'`, never a silent
    // no-op select of the sprite it just rejected.
    expect(action).toEqual({ kind: 'deselect' })
  })

  it('clicking well outside the sprite\'s billboard square entirely also does not select it', () => {
    const light = actor('HKMarketLight1', { brush: null })
    const sprite = makeSprite('HKMarketLight1')
    const { clientX, clientY } = worldToClient(5, 5)
    const action = resolveTapSelect(
      baseParams({ mode: 'lit', clientX, clientY, markerObjects: [sprite], actors: [light] }),
    )
    expect(action).toEqual({ kind: 'deselect' })
  })
})

// ---------------------------------------------------------------------------------------------
// Scenario 2 (click-reliability half): a masked decal poly sitting in front of another actor's
// wall resolves DETERMINISTICALLY to the decal across repeated clicks and several points across
// its own area -- never flaky, never the wall behind it. (The highlight-VISIBILITY half of this
// scenario is covered by `SelectionHighlight.test.tsx`'s masked-geometry `alphaTest` tests; the
// "flaky pick" half was found to be already fixed, not a new bug --
// `dev/docs/board/done/flaky-masked-surface-and-sprite-picking-30pct/overview.md`.)
// ---------------------------------------------------------------------------------------------
describe('resolveTapSelect -- a masked decal in front of a wall resolves deterministically, never the wall behind it', () => {
  const wall = actor('Brush98')
  const decal = actor('Brush100')
  const { mesh: wallMesh, triangleOwners: wallOwners, trianglePolyIndex: wallPolyIndex } = quadMesh(-5, -5, 5, 5, -0.5, 'Brush98', 0)
  const { mesh: decalMesh, triangleOwners: decalOwners, trianglePolyIndex: decalPolyIndex } = quadMesh(-1, -1, 1, 1, 0, 'Brush100', 0)

  // `resolveTapSelect` only raycasts ONE `meshObject` -- the real scene merges every poly (wall and
  // decal alike) into one buffer geometry, so this test merges the two quads into one mesh with a
  // combined owner array too, matching `geometry.ts`'s real "one big merged mesh" shape.
  function mergedScene() {
    const positions = new Float32Array([...decalMesh.geometry.getAttribute('position').array, ...wallMesh.geometry.getAttribute('position').array])
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ side: THREE.DoubleSide }))
    const triangleOwners = [...decalOwners, ...wallOwners]
    const trianglePolyIndex = [...decalPolyIndex, ...wallPolyIndex]
    return { mesh, triangleOwners, trianglePolyIndex }
  }

  it('repeated identical clicks on the decal always resolve to the same actor', () => {
    const { mesh, triangleOwners, trianglePolyIndex } = mergedScene()
    const { clientX, clientY } = worldToClient(0, 0)
    const results = Array.from({ length: 5 }, () =>
      resolveTapSelect(baseParams({ mode: 'lit', clientX, clientY, meshObject: mesh, triangleOwners, trianglePolyIndex, actors: [wall, decal] })),
    )
    for (const action of results) expect(action).toEqual({ kind: 'select-surface', actor: 'Brush100', polyIndex: 0, additive: false })
  })

  it('a grid of points across the decal\'s own area always resolves to the decal, never the wall', () => {
    const { mesh, triangleOwners, trianglePolyIndex } = mergedScene()
    for (const x of [-0.8, -0.3, 0, 0.4, 0.9]) {
      for (const y of [-0.8, -0.3, 0, 0.4, 0.9]) {
        const { clientX, clientY } = worldToClient(x, y)
        const action = resolveTapSelect(
          baseParams({ mode: 'lit', clientX, clientY, meshObject: mesh, triangleOwners, trianglePolyIndex, actors: [wall, decal] }),
        )
        expect(action).toEqual({ kind: 'select-surface', actor: 'Brush100', polyIndex: 0, additive: false })
      }
    }
  })

  it('a click outside the decal, still on the wall, resolves to the wall -- the decal never over-grabs', () => {
    const { mesh, triangleOwners, trianglePolyIndex } = mergedScene()
    const { clientX, clientY } = worldToClient(4, 4)
    const action = resolveTapSelect(
      baseParams({ mode: 'lit', clientX, clientY, meshObject: mesh, triangleOwners, trianglePolyIndex, actors: [wall, decal] }),
    )
    expect(action).toEqual({ kind: 'select-surface', actor: 'Brush98', polyIndex: 0, additive: false })
  })
})

// ---------------------------------------------------------------------------------------------
// Scenario 1: clicking an already-selected poly deselects it instead of doing nothing -- the full
// round trip from a real `resolveTapSelect` hit through `selectionSet.ts`'s `toggleSelection`,
// exactly as `App.tsx`'s `onSelectSurface` wires them together. Board
// `click-on-a-selected-poly-does-not-deselect-it`.
// ---------------------------------------------------------------------------------------------
describe('click-on-a-selected-poly-does-not-deselect-it -- full resolveTapSelect -> toggleSelection round trip', () => {
  const decal = actor('Brush100')
  const { mesh, triangleOwners, trianglePolyIndex } = quadMesh(-1, -1, 1, 1, 0, 'Brush100', 0)

  /** Mirrors `App.tsx`'s `onSelectSurface`: `toggleSelection(current, surfaceKey(actor, polyIndex),
   * additive, /* deselectSole *​/ true)`. */
  function applySurfaceSelect(current: ReadonlySet<string>, actorName: string, polyIndex: number, additive: boolean): Set<string> {
    return toggleSelection(current, surfaceKey(actorName, polyIndex), additive, true)
  }

  it('clicking the poly once selects it; clicking it again (re-tap) deselects it', () => {
    const { clientX, clientY } = worldToClient(0, 0)
    const params = baseParams({ mode: 'lit', clientX, clientY, meshObject: mesh, triangleOwners, trianglePolyIndex, actors: [decal] })
    const action = resolveTapSelect(params)
    expect(action).toEqual({ kind: 'select-surface', actor: 'Brush100', polyIndex: 0, additive: false })
    if (action.kind !== 'select-surface') throw new Error('expected a select-surface action')
    const afterFirstClick = applySurfaceSelect(new Set(), action.actor, action.polyIndex, action.additive)
    expect([...afterFirstClick]).toEqual([surfaceKey('Brush100', 0)])

    // Re-resolve the SAME click against the app's now-current selection state -- the real flow:
    // the second tap on the same poly runs through `resolveTapSelect` again (unchanged: it still
    // reports `select-surface` for the same poly -- the raycast doesn't know about selection state)
    // and it's `toggleSelection`'s `deselectSole` that turns a re-tap of the sole selection into a
    // clear, not a no-op replace.
    const action2 = resolveTapSelect(params)
    if (action2.kind !== 'select-surface') throw new Error('expected a select-surface action')
    const afterSecondClick = applySurfaceSelect(afterFirstClick, action2.actor, action2.polyIndex, false)
    expect(afterSecondClick.size).toBe(0)
  })
})

// ---------------------------------------------------------------------------------------------
// Owner correction 2026-09-19 (`ctrl-poly-deselect-should-be-wireframe-only-not`), reverting the
// same-day `ctrl-click-on-selected-brush-poly-should-deselect` fix: Ctrl+LMB on a POLY must never
// deselect the owning brush, even when it's already actor-selected -- select-surface only, in every
// mode. Ctrl-deselect of a brush is reached ONLY by clicking the brush's own wireframe outline LINE
// (the second describe block below), which `resolveTapAction`'s pre-existing `isLineHit` branch
// already handles and neither the reverted fix nor this revert ever touched.
// ---------------------------------------------------------------------------------------------
describe('resolveTapSelect -- Ctrl+click on a poly never deselects the owning brush', () => {
  const brush = actor('Brush1')
  const { mesh, triangleOwners, trianglePolyIndex } = quadMesh(-1, -1, 1, 1, 0, 'Brush1', 0)

  it('Ctrl (no Shift) on a poly resolves to select-surface, regardless of the brush\'s current selection state', () => {
    const { clientX, clientY } = worldToClient(0, 0)
    const action = resolveTapSelect(
      baseParams({
        mode: 'lit', clientX, clientY, additive: true, meshObject: mesh,
        triangleOwners, trianglePolyIndex, actors: [brush],
      }),
    )
    // `resolveTapSelect`/`resolveTapAction` no longer take a selection-set argument at all -- a
    // poly click can never fork on whether the actor happens to be selected already.
    expect(action).toEqual({ kind: 'select-surface', actor: 'Brush1', polyIndex: 0, additive: true })
  })
})

// ---------------------------------------------------------------------------------------------
// Ctrl+click on an already-selected brush's own WIREFRAME outline line DOES deselect it -- this is
// the one real path the owner wants, and it was never broken by either the deselect-via-poly fix or
// this revert (`resolveTapAction`'s `isLineHit` branch, untouched). Pinned as a full
// resolveTapSelect -> toggleSelection round trip (mirrors `App.tsx`'s `onSelectActor` wiring) so a
// future change can't accidentally couple the two decisions again.
// ---------------------------------------------------------------------------------------------
describe('resolveTapSelect -- wireframe-mode Ctrl+click on an already-selected brush outline deselects it', () => {
  const brush = actor('Brush1', { bbox_lo: [-3, -3, -3], bbox_hi: [3, 3, 3] })
  const outline = outlineSquare(2, 0, 'Brush1', false)

  it('clicking the outline with Ctrl held toggles the already-selected actor off', () => {
    const { clientX, clientY } = worldToClient(0, -2) // midpoint of the bottom edge
    const action = resolveTapSelect(
      baseParams({ mode: 'wireframe', clientX, clientY, additive: true, brushObjects: [outline], actors: [brush] }),
    )
    expect(action).toEqual({ kind: 'select-actor', name: 'Brush1', additive: true })
    if (action.kind !== 'select-actor') throw new Error('expected a select-actor action')
    const alreadySelected = new Set(['Brush1'])
    const afterCtrlClick = toggleSelection(alreadySelected, action.name, action.additive)
    expect(afterCtrlClick.size).toBe(0)
  })
})

// ---------------------------------------------------------------------------------------------
// Board `masked-poly-transparent-area-click-should-fall`: a click landing on a masked/alpha poly's
// fully-transparent texel must act as though that poly wasn't there -- falling through to whatever
// real geometry is behind it, or a genuine miss. Mirrors Scenario 6's sprite-alpha coverage above,
// generalized to the merged scene mesh's own atlas-backed multi-material groups
// (`isMeshHitTransparent`, `tapSelect.ts`).
// ---------------------------------------------------------------------------------------------
describe('resolveTapSelect -- masked-poly alpha-aware picking on the merged mesh', () => {
  // A minimal fake canvas: transparent for x < splitX, opaque everywhere else -- same convention as
  // Scenario 6's `fakeIconCanvas` (`getContext`/`getImageData` only, no real `HTMLCanvasElement`
  // needed under jsdom).
  function fakeSplitCanvas(size: number, splitX: number) {
    return {
      width: size,
      height: size,
      getContext: () => ({
        getImageData: (x: number) => ({ data: [0, 0, 0, x < splitX ? 0 : 255] }),
      }),
    }
  }

  function maskedMaterial(canvas: unknown): THREE.MeshBasicMaterial {
    const map = new THREE.Texture()
    ;(map as unknown as { image: unknown }).image = canvas
    return new THREE.MeshBasicMaterial({ map, alphaTest: 0.5, side: THREE.DoubleSide })
  }

  function unmaskedMaterial(): THREE.MeshBasicMaterial {
    return new THREE.MeshBasicMaterial({ side: THREE.DoubleSide })
  }

  // A masked decal quad (owner `Brush100`, in front, at `frontZ`) merged with an unmasked wall quad
  // (owner `Brush98`, behind, at `backZ`) into ONE mesh with an array `material` + explicit
  // `bufferGeometry.groups` -- the real shape `sceneResources.ts`/`geometry.ts` always produce (a
  // single non-array material, as `quadMesh` above builds, never carries a resolvable
  // `face.materialIndex` against an array, so `isMeshHitTransparent` always bails false on it --
  // this is why none of this file's other scenarios needed any change).
  // `decalUvOffset` shifts the decal's U coordinate (the only one the opaque/transparent split
  // below depends on) by a constant (e.g. +1 or -1) to exercise the mod-1 wrap `polyUVs`'
  // un-normalized tile-space UVs need -- the SAME world click still must resolve the same way
  // regardless of the offset.
  function maskedScene(decalUvOffset = 0, frontZ = 0, backZ = -0.5) {
    const decalPositions = [
      -1, -1, frontZ, 1, -1, frontZ, 1, 1, frontZ,
      -1, -1, frontZ, 1, 1, frontZ, -1, 1, frontZ,
    ]
    // u = (x+1)/2 -- 0 at the decal's left edge, 1 at its right edge -- offset by `decalUvOffset`.
    const decalUvs = [0, 0, 1, 0, 1, 1, 0, 0, 1, 1, 0, 1].map((v, i) => (i % 2 === 0 ? v + decalUvOffset : v))
    const wallPositions = [
      -5, -5, backZ, 5, -5, backZ, 5, 5, backZ,
      -5, -5, backZ, 5, 5, backZ, -5, 5, backZ,
    ]
    const wallUvs = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0] // unused -- Brush98's material is unmasked

    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array([...decalPositions, ...wallPositions]), 3))
    geometry.setAttribute('uv', new THREE.BufferAttribute(new Float32Array([...decalUvs, ...wallUvs]), 2))
    geometry.addGroup(0, 6, 0) // decal triangles -> material 0 (masked)
    geometry.addGroup(6, 6, 1) // wall triangles -> material 1 (unmasked)

    const materials = [maskedMaterial(fakeSplitCanvas(10, 5)), unmaskedMaterial()]
    const mesh = new THREE.Mesh(geometry, materials)
    const triangleOwners: (string | null)[] = ['Brush100', 'Brush100', 'Brush98', 'Brush98']
    const trianglePolyIndex: (number | null)[] = [0, 0, 0, 0]
    return { mesh, triangleOwners, trianglePolyIndex }
  }

  const wall = actor('Brush98')
  const decal = actor('Brush100')

  it('clicking the OPAQUE half of the masked decal selects it', () => {
    const { mesh, triangleOwners, trianglePolyIndex } = maskedScene()
    const { clientX, clientY } = worldToClient(0.9, 0) // u = 0.95 -> canvas x=9 -> opaque
    const action = resolveTapSelect(
      baseParams({ mode: 'lit', clientX, clientY, meshObject: mesh, triangleOwners, trianglePolyIndex, actors: [wall, decal] }),
    )
    expect(action).toEqual({ kind: 'select-surface', actor: 'Brush100', polyIndex: 0, additive: false })
  })

  it('clicking the TRANSPARENT half of the masked decal falls through to the wall behind it', () => {
    const { mesh, triangleOwners, trianglePolyIndex } = maskedScene()
    const { clientX, clientY } = worldToClient(-0.9, 0) // u = 0.05 -> canvas x=0 -> transparent
    const action = resolveTapSelect(
      baseParams({ mode: 'lit', clientX, clientY, meshObject: mesh, triangleOwners, trianglePolyIndex, actors: [wall, decal] }),
    )
    expect(action).toEqual({ kind: 'select-surface', actor: 'Brush98', polyIndex: 0, additive: false })
  })

  it('clicking the transparent half where NOTHING resolvable is behind it is a genuine miss, not a silent select', () => {
    const { mesh, triangleOwners, trianglePolyIndex } = maskedScene()
    // Same transparent click, but `Brush98` (the wall) isn't in `actors` at all -- the raycast still
    // geometrically hits the wall's real triangle behind the rejected decal hit, but `resolveHitSurface`
    // can't resolve it to an actor, so this falls all the way to the AABB fallback (also a miss, since
    // the only actor present, `decal`, keeps its default far-away bbox) -- a genuine `deselect`, not a
    // silent re-select of whatever the rejected hit happened to reveal.
    const { clientX, clientY } = worldToClient(-0.9, 0)
    const action = resolveTapSelect(
      baseParams({ mode: 'lit', clientX, clientY, meshObject: mesh, triangleOwners, trianglePolyIndex, actors: [decal] }),
    )
    expect(action).toEqual({ kind: 'deselect' })
  })

  it('a click well outside both quads is a genuine miss', () => {
    const { mesh, triangleOwners, trianglePolyIndex } = maskedScene()
    const { clientX, clientY } = worldToClient(8, 8)
    const action = resolveTapSelect(
      baseParams({ mode: 'lit', clientX, clientY, meshObject: mesh, triangleOwners, trianglePolyIndex, actors: [wall, decal] }),
    )
    expect(action).toEqual({ kind: 'deselect' })
  })

  it('an UNMASKED poly (no map, alphaTest 0) is never sampled -- clicking the wall always selects it', () => {
    const { mesh, triangleOwners, trianglePolyIndex } = maskedScene()
    const { clientX, clientY } = worldToClient(4, 4) // on the wall, off the decal entirely
    const action = resolveTapSelect(
      baseParams({ mode: 'lit', clientX, clientY, meshObject: mesh, triangleOwners, trianglePolyIndex, actors: [wall, decal] }),
    )
    expect(action).toEqual({ kind: 'select-surface', actor: 'Brush98', polyIndex: 0, additive: false })
  })

  it('a UV shifted by +1 (tile-space wrap, positive direction) resolves identically to the unshifted case', () => {
    const { mesh, triangleOwners, trianglePolyIndex } = maskedScene(1)
    const opaqueClick = worldToClient(0.9, 0)
    const opaqueAction = resolveTapSelect(
      baseParams({ mode: 'lit', clientX: opaqueClick.clientX, clientY: opaqueClick.clientY, meshObject: mesh, triangleOwners, trianglePolyIndex, actors: [wall, decal] }),
    )
    expect(opaqueAction).toEqual({ kind: 'select-surface', actor: 'Brush100', polyIndex: 0, additive: false })

    const transparentClick = worldToClient(-0.9, 0)
    const transparentAction = resolveTapSelect(
      baseParams({ mode: 'lit', clientX: transparentClick.clientX, clientY: transparentClick.clientY, meshObject: mesh, triangleOwners, trianglePolyIndex, actors: [wall, decal] }),
    )
    expect(transparentAction).toEqual({ kind: 'select-surface', actor: 'Brush98', polyIndex: 0, additive: false })
  })

  it('a UV shifted by -1 (tile-space wrap, negative direction) resolves identically to the unshifted case', () => {
    const { mesh, triangleOwners, trianglePolyIndex } = maskedScene(-1)
    const opaqueClick = worldToClient(0.9, 0)
    const opaqueAction = resolveTapSelect(
      baseParams({ mode: 'lit', clientX: opaqueClick.clientX, clientY: opaqueClick.clientY, meshObject: mesh, triangleOwners, trianglePolyIndex, actors: [wall, decal] }),
    )
    expect(opaqueAction).toEqual({ kind: 'select-surface', actor: 'Brush100', polyIndex: 0, additive: false })

    const transparentClick = worldToClient(-0.9, 0)
    const transparentAction = resolveTapSelect(
      baseParams({ mode: 'lit', clientX: transparentClick.clientX, clientY: transparentClick.clientY, meshObject: mesh, triangleOwners, trianglePolyIndex, actors: [wall, decal] }),
    )
    expect(transparentAction).toEqual({ kind: 'select-surface', actor: 'Brush98', polyIndex: 0, additive: false })
  })

  it('the SAME masked mechanism applies to `moverMeshObject` (a Mover\'s own solid geometry)', () => {
    // A standalone single-quad masked mesh owned by the Mover -- NOT `maskedScene()`'s decal+wall
    // pair (whose owner arrays name `Brush100`/`Brush98`, not a Mover) -- so a rejected transparent
    // hit here has nothing else drawn behind it and falls all the way through to a genuine miss.
    const positions = [-1, -1, 0, 1, -1, 0, 1, 1, 0, -1, -1, 0, 1, 1, 0, -1, 1, 0]
    const uvs = [0, 0, 1, 0, 1, 1, 0, 0, 1, 1, 0, 1]
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(positions), 3))
    geometry.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(uvs), 2))
    geometry.addGroup(0, 6, 0)
    const mesh = new THREE.Mesh(geometry, [maskedMaterial(fakeSplitCanvas(10, 5))])
    const triangleOwners: (string | null)[] = ['DeusExMover4', 'DeusExMover4']
    const trianglePolyIndex: (number | null)[] = [2, 2]
    const mover = actor('DeusExMover4', { is_mover: true })

    const opaqueClick = worldToClient(0.9, 0)
    const opaqueAction = resolveTapSelect(
      baseParams({
        mode: 'lit', clientX: opaqueClick.clientX, clientY: opaqueClick.clientY,
        moverMeshObject: mesh, moverTriangleOwners: triangleOwners, moverTrianglePolyIndex: trianglePolyIndex,
        actors: [mover],
      }),
    )
    expect(opaqueAction).toEqual({ kind: 'select-surface', actor: 'DeusExMover4', polyIndex: 2, additive: false })

    const transparentClick = worldToClient(-0.9, 0)
    const transparentAction = resolveTapSelect(
      baseParams({
        mode: 'lit', clientX: transparentClick.clientX, clientY: transparentClick.clientY,
        moverMeshObject: mesh, moverTriangleOwners: triangleOwners, moverTrianglePolyIndex: trianglePolyIndex,
        actors: [mover],
      }),
    )
    // Nothing else is mounted behind the Mover's own mesh in this scene -- a genuine miss.
    expect(transparentAction).toEqual({ kind: 'deselect' })
  })
})
