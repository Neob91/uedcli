// Collision-cylinder + light-radius overlays, in both the 3D perspective pane and the 2D ortho
// panes -- ports `actor diagram --show collision`/`--show light-range` (uedcli/preview.py,
// `dev/docs/unrealed/rendering.md` "Point-actor sprites + radii overlays"). That CLI flag is a
// GLOBAL render toggle (every actor carrying the property); this component's `Radii:` toggle
// (QuadLayout, mirroring the existing grid-toggle) instead gates a SELECTION filter -- when on, it
// draws only for the currently-SELECTED actor(s) among those `SceneActor.radii` resolved
// (server-side, unconditionally for every actor -- see uedcli/serve/scene.py::ActorRadii);
// nothing selected draws nothing (owner ruling 2026-09-15: scoping the toggle to the selection is
// the point -- "show everything" would defeat it). `selectedRadiiActors` (radiiProjection.ts) is
// the shared pure filter.
//
// The perspective pane draws a REAL 3D shape for collision: an upright wire cylinder (matching
// preview.py's `_draw_cylinder` docstring -- "upright, world-axis-aligned regardless of actor
// rotation"). The light radius is NOT a 3D shape at all -- GUI-PARITY.md "Radii overlay colors"
// divergence 1 (closed 2026-09-18, `dev/docs/board/done/gui-light-radius-is-a-camera-facing-circle-
// not/`): `Editor.dll`'s radii block calls `URender::DrawCircle` for it on EVERY branch including
// perspective (VA 0x1003d932), and `render.dll`'s `DrawCircle` (RVA 0x1c590) builds its ring from
// the scene node's own CAMERA axes (`FSceneNode+0x40..0x54`) -- a camera-facing circle (a
// billboard), not a world-plane-aligned sphere silhouette. An ortho pane draws the exact 2D
// silhouette `radiiProjection.ts` computes for that axis (ported from preview.py, not re-derived):
// TOP sees the collision cylinder's own circular cap; FRONT/SIDE see it edge-on as a `2r x 2h` rect;
// the light circle is drawn flat in the pane's own view plane in EVERY ortho axis -- already exactly
// what a camera-facing circle degenerates to under a fixed-axis orthographic camera, so `OrthoShapeLine`
// below needs no change for this divergence.
import { useEffect, useMemo } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'

import type { SceneActor } from '../api'
import type { OrthoAxis } from './orthoCamera'
import { orthoBasis } from './orthoCamera'
import type { OrthoShape } from './radiiProjection'
import { collisionOrthoShape, selectedRadiiActors, sphereOrthoShape } from './radiiProjection'
import { toThreeColor } from './selectionColor'

// The colors below are read from THIS project's own `uned/UED22` binary + config, not from any
// third-party UE1 source (GUI-PARITY.md "Radii overlay colors", ✅ binary, 2026-09-18).
// `Editor.dll`'s per-actor radii block (VA 0x1003d45b..0x1003da5a, inside `UEditorEngine::Draw`)
// picks a DIFFERENT color per pane for the collision shape, and one shared color each for light
// and sound:
//
//   perspective collision -> `Render->DrawCylinder` with `C_BrushWire`        (UEditorEngine + 0x1ac)
//   ortho collision       -> `DrawCircle`/`DrawBox`  with `C_ActorArrow`      (UEditorEngine + 0x1f8)
//   light radius, EVERY pane -> `DrawCircle`         with `C_ActorArrow`
//   sound radius, EVERY pane -> `DrawCircle`         with `C_GroundHighlight` (UEditorEngine + 0x1a8)
//
// (Both collision branches pick that member only when the actor's `bCollideActors` is set; the
// binary's other branch draws the SAME shape in a hard-coded `FPlane(0.3, 0.6, 1.0, 1.0)` instead.
// That branch is unreachable HERE only because `serve/scene.py::_actor_radii` never sends a
// non-colliding actor's `collision_radius` at all -- a whole missing overlay, tracked separately as
// `gui-non-colliding-actors-get-no-collision`, not something this file can decide.)
// The RGB values are our own substrate's `uned/UED22/unrealtournament.ini` `[Editor.EditorEngine]`.
const C_BRUSH_WIRE = toThreeColor([255, 63, 63])
const C_ACTOR_ARROW = toThreeColor([163, 0, 0])
const C_GROUND_HIGHLIGHT = toThreeColor([0, 0, 127])
// UED22 draws every one of these as plain `LINE_None` line draws with no blend stage at all, so
// these materials carry no `transparent`/`opacity` at all either. The 0.55 alpha that used to be
// here was an invention, and (with the too-dark perspective color above) what made the overlay
// "hardly visible" (owner report, 2026-09-18).
const CIRCLE_SEGMENTS = 32
// UNCONFIRMED against our own binary: this 8 comes from a UT patch release note ("rendering the
// collision cylinder as an 8-sided wire cylinder" in the 3D window), not from `render.dll`'s real
// `URender::DrawCylinder`, whose body is not a plain N-gon loop and was not decoded (GUI-PARITY.md
// "Radii overlay colors"; tracked as `gui-drawcircle-segment-count-is-adaptive`).
// preview.py's own `_ISO_CYL_SEGMENTS = 9` is a
// DIFFERENT, deliberately-odd count for its own flat 2D raster (avoids two edges sharing a screen
// column) -- doesn't apply to a real WebGL mesh, so this uses the literal patch-note value instead.
const CYLINDER_SEGMENTS = 8

export type RadiiView = 'perspective' | OrthoAxis

export interface RadiiOverlaysProps {
  actors: SceneActor[]
  view: RadiiView
  selectedNames: ReadonlySet<string>
}

// Explicit line-segment positions for an upright wire cylinder (top ring, bottom ring, N vertical
// struts), built directly in WORLD-space X/Y (radius) + Z (height, this app's up axis) -- never a
// local-space `<mesh position=.../>` transform. Two reasons: (1) `MeshBasicMaterial`'s `wireframe:
// true` on a real `CylinderGeometry` draws EVERY triangle edge, including the diagonal seam each
// side quad is split into two triangles by -- visibly "triangular faces" (owner report), not a
// clean cage. Explicit top/bottom rings + struts, matching preview.py's `_draw_cylinder` ISO-view
// technique (`_line` calls, no filled geometry at all), has no triangulation to leak through. (2) A
// local-space transform bit us once already (`SelectionMarkers.tsx`'s pivot-marker bug: local
// marker position vs. world-space camera position, wrong specifically in the perspective pane's
// world-handedness mirror group) -- computing everything in world space up front, the same way
// `orthoShapeRing` below already does, sidesteps that whole class of bug by construction.
function cylinderLinePositions(center: [number, number, number], radius: number, halfHeight: number): number[] {
  const n = CYLINDER_SEGMENTS
  const top: THREE.Vector3[] = []
  const bot: THREE.Vector3[] = []
  for (let i = 0; i < n; i++) {
    const theta = (i / n) * Math.PI * 2
    const x = center[0] + radius * Math.cos(theta)
    const y = center[1] + radius * Math.sin(theta)
    top.push(new THREE.Vector3(x, y, center[2] + halfHeight))
    bot.push(new THREE.Vector3(x, y, center[2] - halfHeight))
  }
  const positions: number[] = []
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n
    positions.push(...top[i].toArray(), ...top[j].toArray()) // top ring
    positions.push(...bot[i].toArray(), ...bot[j].toArray()) // bottom ring
    positions.push(...top[i].toArray(), ...bot[i].toArray()) // vertical strut
  }
  return positions
}

function CollisionCylinder3D({
  position,
  radius,
  halfHeight,
}: {
  position: [number, number, number]
  radius: number
  halfHeight: number
}) {
  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(cylinderLinePositions(position, radius, halfHeight), 3))
    return geo
  }, [position, radius, halfHeight])
  useEffect(() => () => geometry.dispose(), [geometry])
  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color={C_BRUSH_WIRE} depthTest={false} />
    </lineSegments>
  )
}

// A camera-facing circle (a billboard) -- GUI-PARITY.md "Radii overlay colors" divergence 1: real
// UED22 builds the light-radius ring from the scene node's own CAMERA axes (`render.dll`'s
// `DrawCircle`, RVA 0x1c590), not a world-plane-aligned shape -- and the sound-radius ring is the
// SAME `DrawCircle` call, just with a different color member (`C_GroundHighlight` instead of
// `C_ActorArrow`), so this one component (parametrized on `color`) serves both. Recomputed every frame from the live
// camera orientation (`useFrame`), the same reason `SelectionMarkers.tsx`'s `PivotMarker`/`VertexDot`
// rescale every frame -- a camera-facing shape can't be baked once into a static `useMemo` geometry.
//
// Coordinate-space hazard, same class as `SelectionMarkers.tsx`'s pivot-marker bug (see that file's
// `PivotMarker` doc comment): this component's content sits inside the world-handedness mirror group
// (`<group scale={[1,-1,1]}>` in Viewport3D.tsx/OrthoViewport.tsx), a pure Y-flip with no rotation,
// while `camera` (from `useThree()`) is posed directly in the ALREADY-reflected render space
// (`viewportRender.ts`'s `applyCameraPose` sets `camera.position`/`lookAt` with Y already negated).
// So a camera-space direction vector needs the SAME flip applied to land back in this component's
// own (pre-reflection) local space -- negate Y. Since `R = diag(1,-1,1)` is self-inverse, this one
// negation is exactly `R^-1`, not an approximation. `PivotMarker`/`VertexDot` sidestep this by using
// `sprite.getWorldPosition()` (a real scene-graph transform); this component builds explicit line
// geometry instead (matching every other radii overlay's `<lineSegments>` convention, no texture/
// alpha), so the reflection is applied by hand here.
// One circle's world-space center + radius, batched into a `RadiusCircleGroup3D` below.
interface RadiusCircleItem {
  position: [number, number, number]
  radius: number
}

// Perf note (board item gui-mouse-nav-jitter-ortho-radii-css, 2026-09-19): this used to be a
// PER-ACTOR component (`RadiusCircle3D`), each instance running its own `useFrame` -- recomputing
// the SAME camera-facing `right`/`up` basis independently (an identical `applyQuaternion` call per
// instance, wasted work past the first) and issuing its own separate draw call, every rendered
// frame, continuously, whether or not the camera has moved (react-three-fiber's default "always"
// frameloop re-renders every mounted `<Canvas>` every animation frame regardless). All FOUR
// quad-layout panes (perspective + 3 ortho) run this on the SAME single JS main thread, so this
// per-frame cost is paid continuously no matter which pane the user is actually dragging in.
// Landing the sound-radius overlay (this same component, reused for a second radius type) doubled
// the instance count for any actor carrying both a light and a sound radius -- but the underlying
// inefficiency (an O(N) redundant basis computation plus O(N) draw calls for what could be ONE)
// already existed for light radius alone. Since every circle of the SAME radius type always shares
// one fixed color (`C_ACTOR_ARROW` for light, `C_GROUND_HIGHLIGHT` for sound -- see the call sites
// below), there's no need for N materials either: one `<lineSegments>` batches every same-colored
// circle into a single geometry, one `useFrame` computes the camera basis ONCE per frame no matter
// how many actors are selected, and the renderer has one object to cull/draw instead of up to 2N.
function RadiusCircleGroup3D({ items, color }: { items: RadiusCircleItem[]; color: THREE.Color }) {
  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry()
    const positions = new Float32Array(items.length * CIRCLE_SEGMENTS * 2 * 3)
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    return geo
    // `items` is expected to be a stable array (memoized by the caller on the actual selection/
    // radii data, not recreated fresh every render) -- see RadiiOverlays' `useMemo` below. Sizing
    // only on `items.length`, not `items` itself, avoids rebuilding (and losing in-place mutation
    // continuity for) the buffer on every render when the length hasn't actually changed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items.length])
  useEffect(() => () => geometry.dispose(), [geometry])
  const { camera } = useThree()
  const right = useMemo(() => new THREE.Vector3(), [])
  const up = useMemo(() => new THREE.Vector3(), [])
  useFrame(() => {
    // See RadiusCircleGroup3D's own doc comment for the coordinate-space hazard this Y-flip fixes.
    right.set(1, 0, 0).applyQuaternion(camera.quaternion)
    up.set(0, 1, 0).applyQuaternion(camera.quaternion)
    right.y *= -1
    up.y *= -1
    const arr = geometry.attributes.position.array as Float32Array
    for (let n = 0; n < items.length; n++) {
      const { position, radius } = items[n]
      const [cx, cy, cz] = position
      const base = n * CIRCLE_SEGMENTS * 2 * 3
      for (let i = 0; i < CIRCLE_SEGMENTS; i++) {
        const a = (i / CIRCLE_SEGMENTS) * Math.PI * 2
        const b = ((i + 1) / CIRCLE_SEGMENTS) * Math.PI * 2
        const ca = Math.cos(a) * radius
        const sa = Math.sin(a) * radius
        const cb = Math.cos(b) * radius
        const sb = Math.sin(b) * radius
        const o = base + i * 6
        arr[o + 0] = cx + right.x * ca + up.x * sa
        arr[o + 1] = cy + right.y * ca + up.y * sa
        arr[o + 2] = cz + right.z * ca + up.z * sa
        arr[o + 3] = cx + right.x * cb + up.x * sb
        arr[o + 4] = cy + right.y * cb + up.y * sb
        arr[o + 5] = cz + right.z * cb + up.z * sb
      }
    }
    geometry.attributes.position.needsUpdate = true
  })
  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color={color} depthTest={false} />
    </lineSegments>
  )
}

// World-space points for one ortho-pane shape's closed outline, lying in the pane's own (right, up)
// screen plane through `center` -- the SAME basis GridOverlay/OrthoCameraRig use for this axis, so
// the shape always sits exactly in what that pane's orthographic camera sees edge-on-flat, at the
// actor's own true location (not the camera's). Returns a CLOSED ring (first point repeated last).
function orthoShapeRing(
  shape: OrthoShape,
  center: [number, number, number],
  right: [number, number, number],
  up: [number, number, number],
): THREE.Vector3[] {
  const at = (u: number, v: number) =>
    new THREE.Vector3(
      center[0] + right[0] * u + up[0] * v,
      center[1] + right[1] * u + up[1] * v,
      center[2] + right[2] * u + up[2] * v,
    )
  if (shape.kind === 'circle') {
    const pts: THREE.Vector3[] = []
    for (let i = 0; i <= CIRCLE_SEGMENTS; i++) {
      const theta = (i / CIRCLE_SEGMENTS) * Math.PI * 2
      pts.push(at(shape.radius * Math.cos(theta), shape.radius * Math.sin(theta)))
    }
    return pts
  }
  const { halfWidth, halfHeight } = shape
  return [
    at(-halfWidth, -halfHeight),
    at(halfWidth, -halfHeight),
    at(halfWidth, halfHeight),
    at(-halfWidth, halfHeight),
    at(-halfWidth, -halfHeight),
  ]
}

// `<lineSegments>` (disjoint segment pairs), not `<line>`/`<lineLoop>` -- matches this codebase's
// existing ring-drawing convention (GridOverlay.tsx, BrushOutlines.tsx's ThinRing path) rather than
// a continuous polyline JSX element, which also collides with the DOM/SVG `<line>` intrinsic in this
// project's JSX typings.
function OrthoShapeLine({
  shape,
  center,
  right,
  up,
  color,
}: {
  shape: OrthoShape
  center: [number, number, number]
  right: [number, number, number]
  up: [number, number, number]
  color: THREE.Color
}) {
  const geometry = useMemo(() => {
    const ring = orthoShapeRing(shape, center, right, up)
    const positions: number[] = []
    for (let i = 0; i + 1 < ring.length; i++) positions.push(...ring[i].toArray(), ...ring[i + 1].toArray())
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
    return geo
  }, [shape, center, right, up])
  useEffect(() => () => geometry.dispose(), [geometry])
  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color={color} depthTest={false} />
    </lineSegments>
  )
}

export function RadiiOverlays({ actors, view, selectedNames }: RadiiOverlaysProps) {
  const withRadii = useMemo(() => selectedRadiiActors(actors, selectedNames), [actors, selectedNames])
  // The perspective pane's light/sound circles are camera-facing billboards, rebuilt every rendered
  // frame (RadiusCircleGroup3D's own doc comment) -- batched here into (at most) two arrays, one per
  // fixed color, so N selected actors cost ONE `useFrame`/ONE draw call per radius type instead of up
  // to 2N. Memoized on `withRadii` (itself only recomputed when the actual actor/selection data
  // changes) so this array keeps a stable identity across unrelated re-renders (a camera drag's own
  // `setPose`, e.g.) -- RadiusCircleGroup3D's geometry-sizing `useMemo` depends on `items.length`,
  // not `items` itself, so a stable reference isn't strictly required for correctness, but avoids
  // pointlessly re-deriving this array every frame during a drag.
  const lightItems = useMemo<RadiusCircleItem[]>(
    () => withRadii.filter((a) => a.radii!.light_radius != null).map((a) => ({ position: a.location, radius: a.radii!.light_radius! })),
    [withRadii],
  )
  const soundItems = useMemo<RadiusCircleItem[]>(
    () => withRadii.filter((a) => a.radii!.sound_radius != null).map((a) => ({ position: a.location, radius: a.radii!.sound_radius! })),
    [withRadii],
  )
  if (withRadii.length === 0) return null

  if (view === 'perspective') {
    return (
      <group>
        {withRadii.map((actor) => {
          const radii = actor.radii!
          return radii.collision_radius != null ? (
            <CollisionCylinder3D key={actor.name} position={actor.location} radius={radii.collision_radius} halfHeight={radii.collision_height ?? 0} />
          ) : null
        })}
        {lightItems.length > 0 && <RadiusCircleGroup3D items={lightItems} color={C_ACTOR_ARROW} />}
        {soundItems.length > 0 && <RadiusCircleGroup3D items={soundItems} color={C_GROUND_HIGHLIGHT} />}
      </group>
    )
  }

  const { right, up } = orthoBasis(view)
  return (
    <group>
      {withRadii.map((actor) => {
        const radii = actor.radii!
        return (
          <group key={actor.name}>
            {radii.collision_radius != null && (
              <OrthoShapeLine
                shape={collisionOrthoShape(view, radii.collision_radius, radii.collision_height ?? 0)}
                center={actor.location}
                right={right}
                up={up}
                color={C_ACTOR_ARROW}
              />
            )}
            {radii.light_radius != null && (
              <OrthoShapeLine
                shape={sphereOrthoShape(radii.light_radius)}
                center={actor.location}
                right={right}
                up={up}
                color={C_ACTOR_ARROW}
              />
            )}
            {radii.sound_radius != null && (
              <OrthoShapeLine
                shape={sphereOrthoShape(radii.sound_radius)}
                center={actor.location}
                right={right}
                up={up}
                color={C_GROUND_HIGHLIGHT}
              />
            )}
          </group>
        )
      })}
    </group>
  )
}
