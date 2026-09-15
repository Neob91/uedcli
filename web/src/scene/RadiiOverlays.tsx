// Collision-cylinder + light-radius overlays, in both the 3D perspective pane and the 2D ortho
// panes -- ports `actor diagram --show collision`/`--show light-range` (uedcli/preview.py,
// `dev/docs/unrealed/rendering.md` "Point-actor sprites + radii overlays"). That CLI flag is a
// GLOBAL render toggle (every actor carrying the property, never a per-actor selection filter) --
// this component mirrors that: it draws for every actor `SceneActor.radii` resolved (server-side,
// unconditionally -- see uedcli/serve/scene.py::ActorRadii), gated by this app's one "show radii"
// toggle (QuadLayout, mirroring the existing grid-toggle), never by selection.
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
import { collisionOrthoShape, sphereOrthoShape } from './radiiProjection'

// Matches preview.py's COL_COLLISION/COL_LIGHT hues (collision red, light deviated to orange so the
// two stay distinct -- see preview.py's module comment by those constants). preview.py's rasterizer
// has no alpha blend buffer so it paints these overlays SOLID; three.js does, so a modest opacity
// reads as "faint" the same way its comment intends.
const COLLISION_COLOR = new THREE.Color(235 / 255, 150 / 255, 150 / 255)
const LIGHT_COLOR = new THREE.Color(245 / 255, 175 / 255, 80 / 255)
const OVERLAY_OPACITY = 0.55
const CIRCLE_SEGMENTS = 32

export type RadiiView = 'perspective' | OrthoAxis

export interface RadiiOverlaysProps {
  actors: SceneActor[]
  view: RadiiView
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
  // three's CylinderGeometry runs along local +Y; a +90deg rotation about X maps +Y onto world +Z
  // (this app's up axis throughout -- Viewport3D's CameraRig does `camera.up.set(0,0,1)`), keeping
  // the cylinder upright regardless of the actor's own rotation, matching preview.py's rule. The
  // ODD-facet-count constraint preview.py's `_ISO_CYL_SEGMENTS` documents is specific to its 2D ISO
  // RASTER projection (an even count makes two edges land on the same screen column); it doesn't
  // apply to a real 3D perspective render, so a smoother segment count reads better as a cylinder.
  return (
    <mesh position={position} rotation={[Math.PI / 2, 0, 0]}>
      <cylinderGeometry args={[radius, radius, halfHeight * 2, 16, 1, true]} />
      <meshBasicMaterial color={COLLISION_COLOR} wireframe transparent opacity={OVERLAY_OPACITY} depthTest={false} />
    </mesh>
  )
}

function LightSphere3D({ position, radius }: { position: [number, number, number]; radius: number }) {
  return (
    <mesh position={position}>
      <sphereGeometry args={[radius, 16, 12]} />
      <meshBasicMaterial color={LIGHT_COLOR} wireframe transparent opacity={OVERLAY_OPACITY} depthTest={false} />
    </mesh>
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
      <lineBasicMaterial color={color} transparent opacity={OVERLAY_OPACITY} depthTest={false} />
    </lineSegments>
  )
}

export function RadiiOverlays({ actors, view }: RadiiOverlaysProps) {
  const withRadii = useMemo(
    () => actors.filter((a) => a.radii && (a.radii.collision_radius != null || a.radii.light_radius != null)),
    [actors],
  )
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
                color={COLLISION_COLOR}
              />
            )}
            {radii.light_radius != null && (
              <OrthoShapeLine shape={sphereOrthoShape(radii.light_radius)} center={actor.location} right={right} up={up} color={LIGHT_COLOR} />
            )}
          </group>
        )
      })}
    </group>
  )
}
