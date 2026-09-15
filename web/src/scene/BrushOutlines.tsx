// CSG-colored brush wireframe rings (quad-layout Part 2, Task 10): the shared rendering piece both
// Perspective and ortho panes draw from buildBrushRings' pure logic (Task 9). Non-bold rings use the
// cheap LineLoop/LineBasicMaterial path (a 1px-only line is fine -- they don't need to stand out).
//
// Bold (selected) rings use Line2/LineMaterial (`three/examples/jsm/lines`, already inside the
// pinned `three` package -- a deeper import path, NOT a new npm dependency) instead of
// `LineBasicMaterial`'s own `linewidth`. Per the spec's own review finding: WebGL, via ANGLE/OpenGL
// Core Profile on virtually every desktop browser, ignores `LineBasicMaterial.linewidth` above 1px
// (matching three.js's own documented limitation almost verbatim) -- a straightforward
// `linewidth={3}` port would very likely render the "bolder" selected ring at the exact same 1px
// weight as every other ring, silently failing the "matches `actor diagram`" requirement's bolder-
// line half.
//
// Step A (a real-browser visual comparison confirming the selected ring is VISIBLY thicker) could
// NOT be run in this build environment -- no Chromium-family browser was available in this sandbox
// (confirmed: no chromium/chromium-browser/google-chrome binary, no committed headless-browser
// harness in this worktree). Given the underlying fact is well-established platform behavior, not a
// coin flip, Step B's fix is applied PREEMPTIVELY here rather than shipping a change whose "bolder"
// half is very likely a silent no-op. Flagged in the build report for a real-browser confirmation
// before merge -- Task 10's own Step A is not considered done, only its Step B fallback.
import { useEffect, useMemo } from 'react'
import { useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { Line2 } from 'three/examples/jsm/lines/Line2.js'
import { LineGeometry } from 'three/examples/jsm/lines/LineGeometry.js'
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js'

import type { SceneActor } from '../api'
import type { BrushRingMode } from './brushRings'
import { buildBrushRings } from './brushRings'

const BOLD_LINEWIDTH_PX = 3

/** `Line2`/`LineGeometry` draw an open polyline, not an automatically-closed loop (unlike
 * `THREE.LineLoop`) -- append the first vertex again at the end to close the ring. */
function closedLoopPositions(verts: number[]): number[] {
  if (verts.length < 3) return verts
  return [...verts, verts[0], verts[1], verts[2]]
}

/** The ordinary-weight ring path: cheap, depth-tested, one draw call per poly -- matches
 * `AllBrushWireframes`' pre-existing look exactly (default depthTest, so brushes properly occlude
 * each other in 3D). */
function ThinRing({ verts, color }: { verts: number[]; color: THREE.Color }) {
  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3))
    return geo
  }, [verts])
  useEffect(() => () => geometry.dispose(), [geometry])
  return (
    <lineLoop geometry={geometry}>
      <lineBasicMaterial color={color} />
    </lineLoop>
  )
}

/** The bold (selected) ring path: real pixel-width via `Line2`/`LineMaterial`'s `resolution`
 * uniform, which must track the canvas's own pixel size on resize -- the real added-complexity cost
 * this task's Step B warns about. `depthTest={false}` matches the pre-existing selection-highlight
 * look (always-on-top, matching `preview.py --highlight`'s "ignores facing/depth"). */
function BoldRing({ verts, color }: { verts: number[]; color: THREE.Color }) {
  const { size } = useThree()
  const geometry = useMemo(() => {
    const geo = new LineGeometry()
    geo.setPositions(closedLoopPositions(verts))
    return geo
  }, [verts])
  const material = useMemo(
    () => new LineMaterial({ color: color.getHex(), linewidth: BOLD_LINEWIDTH_PX, depthTest: false, transparent: false }),
    [color],
  )
  useEffect(() => {
    material.resolution.set(size.width, size.height)
  }, [material, size.width, size.height])
  useEffect(
    () => () => {
      geometry.dispose()
      material.dispose()
    },
    [geometry, material],
  )
  const line = useMemo(() => new Line2(geometry, material), [geometry, material])
  return <primitive object={line} />
}

export interface BrushOutlinesProps {
  actors: SceneActor[]
  selectedNames: ReadonlySet<string>
  mode: BrushRingMode
}

/** Renders every ring `buildBrushRings` selects for `mode` -- ordinary weight for every non-selected
 * brush (`'csg-all'`) or nothing (`'selected-only'` when unselected), bold for every SELECTED one
 * (Part 3, Task 14: one ring per selected actor, not just one overall). */
export function BrushOutlines({ actors, selectedNames, mode }: BrushOutlinesProps) {
  const rings = useMemo(() => buildBrushRings(actors, selectedNames, mode), [actors, selectedNames, mode])
  return (
    <group>
      {rings.map((ring, i) => {
        const color = new THREE.Color(ring.color[0] / 255, ring.color[1] / 255, ring.color[2] / 255)
        return ring.bold ? (
          <BoldRing key={`${ring.actorName}-${i}`} verts={ring.verts} color={color} />
        ) : (
          <ThinRing key={`${ring.actorName}-${i}`} verts={ring.verts} color={color} />
        )
      })}
    </group>
  )
}
