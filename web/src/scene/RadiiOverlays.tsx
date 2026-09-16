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

// UED22 draws the collision-radius circle AND the light-radius circle with the SAME color constant
// (`C_ActorArrow`, `UnEdCam.cpp:1547,1564`, GUI-PARITY.md "Radii overlay colors") -- preview.py's
// separate COL_COLLISION/COL_LIGHT (light deviated to orange) was its own 2D-diagram readability
// hack, not a real UED22 distinction, and was wrongly carried into this live 3D GUI. Both now share
// one constant. `C_ActorArrow`'s exact RGB wasn't recovered (binary disassembly located the code but
// not this specific data reference); this keeps the existing red-family value pending that. preview.py's
// rasterizer has no alpha blend buffer so it paints these overlays SOLID; three.js does, so a modest
// opacity reads as "faint" the same way its comment intends.
const RADII_COLOR = new THREE.Color(235 / 255, 150 / 255, 150 / 255)
const OVERLAY_OPACITY = 0.55
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
  // the cylinder upright regardless of the actor's own rotation, matching preview.py's rule.
  return (
    <mesh position={position} rotation={[Math.PI / 2, 0, 0]}>
      <cylinderGeometry args={[radius, radius, halfHeight * 2, CYLINDER_SEGMENTS, 1, true]} />
      <meshBasicMaterial color={RADII_COLOR} wireframe transparent opacity={OVERLAY_OPACITY} depthTest={false} />
    </mesh>
  )
}

function LightSphere3D({ position, radius }: { position: [number, number, number]; radius: number }) {
  return (
    <mesh position={position}>
      <sphereGeometry args={[radius, 16, 12]} />
      <meshBasicMaterial color={RADII_COLOR} wireframe transparent opacity={OVERLAY_OPACITY} depthTest={false} />
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
                color={RADII_COLOR}
              />
            )}
            {radii.light_radius != null && (
              <OrthoShapeLine shape={sphereOrthoShape(radii.light_radius)} center={actor.location} right={right} up={up} color={RADII_COLOR} />
            )}
          </group>
        )
      })}
    </group>
  )
}
