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
// The perspective pane draws a REAL 3D shape: an upright wire cylinder (matching preview.py's
// `_draw_cylinder` docstring -- "upright, world-axis-aligned regardless of actor rotation") and a
// wire sphere (a sphere is the only 3D shape whose silhouette is a circle from every angle, which is
// exactly what preview.py's `_draw_sphere` relies on for its 2D views). An ortho pane instead draws
// the exact 2D silhouette `radiiProjection.ts` computes for that axis (ported from preview.py, not
// re-derived): TOP sees the cylinder's own circular cap; FRONT/SIDE see it edge-on as a `2r x 2h`
// rect; the light/sound sphere is a circle of its own radius in EVERY ortho axis.
import { useEffect, useMemo } from 'react'
import * as THREE from 'three'

import type { SceneActor } from '../api'
import type { OrthoAxis } from './orthoCamera'
import { orthoBasis } from './orthoCamera'
import type { OrthoShape } from './radiiProjection'
import { collisionOrthoShape, selectedRadiiActors, sphereOrthoShape } from './radiiProjection'
import { toThreeColor } from './selectionColor'

// Colors and opacity below are read from THIS project's own `uned/UED22` binary + config, not from
// any third-party UE1 source (GUI-PARITY.md "Radii overlay colors", ✅ binary, 2026-09-18).
// `Editor.dll`'s per-actor radii block (VA 0x1003d45b..0x1003da5a, inside `UEditorEngine::Draw`)
// picks a DIFFERENT color per pane for the collision shape, and one shared color for light:
//
//   perspective collision -> `Render->DrawCylinder` with `C_BrushWire`   (UEditorEngine + 0x1ac)
//   ortho collision       -> `DrawCircle`/`DrawBox`  with `C_ActorArrow` (UEditorEngine + 0x1f8)
//   light radius, EVERY pane -> `DrawCircle`         with `C_ActorArrow`
//
// (Both collision branches pick that member only when the actor's `bCollideActors` is set, which is
// exactly the gate `serve/scene.py::_actor_radii` already applies before sending `collision_radius`
// at all -- so the binary's other branch, a hard-coded `FPlane(0.3, 0.6, 1.0, 1.0)` for a
// non-colliding actor, is unreachable from this data and is deliberately not implemented here.)
// The RGB values are our own substrate's `uned/UED22/unrealtournament.ini` `[Editor.EditorEngine]`.
const C_BRUSH_WIRE = toThreeColor([255, 63, 63])
const C_ACTOR_ARROW = toThreeColor([163, 0, 0])
// UED22 draws every one of these as plain `LINE_None` line draws with no blend stage at all, so
// these materials carry no `transparent`/`opacity` at all either. The 0.55 alpha that used to be
// here was an invention, and (with the too-dark perspective color above) what made the overlay
// "hardly visible" (owner report, 2026-09-18).
const CIRCLE_SEGMENTS = 32
// UT patch release notes (GUI-PARITY.md "Radii overlay colors"): "rendering the collision cylinder
// as an 8-sided wire cylinder" in the 3D window. preview.py's own `_ISO_CYL_SEGMENTS = 9` is a
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

// A classic "wire sphere" gizmo -- three orthogonal circles (XY/XZ/YZ planes through `center`), not
// a triangulated `SphereGeometry` in wireframe mode (same triangulation-diagonal problem as the
// cylinder above). preview.py's own `_draw_sphere` docstring already establishes the underlying
// fact this relies on -- a sphere's silhouette is a circle from every angle -- so three perpendicular
// silhouette-radius circles read as an unambiguous sphere outline without ever triangulating.
function LightSphere3D({ position, radius }: { position: [number, number, number]; radius: number }) {
  const geometry = useMemo(() => {
    const [cx, cy, cz] = position
    const positions: number[] = []
    const addRing = (at: (theta: number) => THREE.Vector3) => {
      for (let i = 0; i < CIRCLE_SEGMENTS; i++) {
        const a = (i / CIRCLE_SEGMENTS) * Math.PI * 2
        const b = ((i + 1) / CIRCLE_SEGMENTS) * Math.PI * 2
        positions.push(...at(a).toArray(), ...at(b).toArray())
      }
    }
    addRing((t) => new THREE.Vector3(cx + radius * Math.cos(t), cy + radius * Math.sin(t), cz)) // XY
    addRing((t) => new THREE.Vector3(cx + radius * Math.cos(t), cy, cz + radius * Math.sin(t))) // XZ
    addRing((t) => new THREE.Vector3(cx, cy + radius * Math.cos(t), cz + radius * Math.sin(t))) // YZ
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
    return geo
  }, [position, radius])
  useEffect(() => () => geometry.dispose(), [geometry])
  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color={C_ACTOR_ARROW} depthTest={false} />
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
}: {
  shape: OrthoShape
  center: [number, number, number]
  right: [number, number, number]
  up: [number, number, number]
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
      <lineBasicMaterial color={C_ACTOR_ARROW} depthTest={false} />
    </lineSegments>
  )
}

export function RadiiOverlays({ actors, view, selectedNames }: RadiiOverlaysProps) {
  const withRadii = useMemo(() => selectedRadiiActors(actors, selectedNames), [actors, selectedNames])
  if (withRadii.length === 0) return null

  if (view === 'perspective') {
    return (
      <group>
        {withRadii.map((actor) => {
          const radii = actor.radii!
          return (
            <group key={actor.name}>
              {radii.collision_radius != null && (
                <CollisionCylinder3D position={actor.location} radius={radii.collision_radius} halfHeight={radii.collision_height ?? 0} />
              )}
              {radii.light_radius != null && <LightSphere3D position={actor.location} radius={radii.light_radius} />}
            </group>
          )
        })}
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
              />
            )}
            {radii.light_radius != null && (
              <OrthoShapeLine shape={sphereOrthoShape(radii.light_radius)} center={actor.location} right={right} up={up} />
            )}
          </group>
        )
      })}
    </group>
  )
}
