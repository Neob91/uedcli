// CSG-colored brush wireframe rings (quad-layout Part 2): the shared rendering piece both the
// perspective and ortho panes draw from buildBrushRings' pure logic. Every ring is a 1px
// LineBasicMaterial/LineLoop; the SELECTED brush's ring is the same 1px line but in the brush's
// plain, undimmed WireColor (UNselected rings are the ones dimmed, not this one brightened -- real
// UED22's actual mechanism, `selectionColor.ts`), drawn depthTest-off + high-renderOrder so it shows over the solid mesh and
// through walls (see BoldRing). WebGL ignores LineBasicMaterial.linewidth > 1px, so a wider
// "bold" line is not attempted here -- the Line2/LineMaterial pixel-width path that used to try it
// rendered nothing at all (silent no-op, confirmed live 2026-09-16); selection reads via the
// brighter colour + the vertex/pivot markers instead.
import { useEffect, useMemo } from 'react'
import type { MutableRefObject } from 'react'
import * as THREE from 'three'

import type { SceneActor } from '../api'
import type { BrushRing, BrushRingMode } from './brushRings'
import { buildBrushRings, mergeThinRings } from './brushRings'
import { resolveWireColor, toThreeColor } from './selectionColor'

// The selected brush's ring draws above everything (markers are at 10) so it shows in solid shading
// modes and through walls -- see BoldRing.
const SELECTED_RING_RENDER_ORDER = 20
// A Mover's (unselected) ring draws depthTest-off too, same reason -- see MergedThinWireframe's
// `alwaysOnTop` doc. Below the selected-ring order so a selected Mover's BoldRing still wins.
const MOVER_RING_RENDER_ORDER = 15

/** Every ordinary-weight (non-selected) ring, merged into ONE `LineSegments` draw call (bug report
 * item 4 -- see `mergeThinRings`' docstring for the measured cost this replaces). Per-vertex color
 * reproduces each ring's own CSG hue; `userData.segmentOwners` lets the outer viewport's raycast
 * resolve a hit segment back to its owning actor (Viewport3D/OrthoViewport's `performTapSelect`),
 * the same role `userData.actorName` plays on a single-actor object like `BoldRing`.
 *
 * `alwaysOnTop` (board item `mover-wireframe-occluded-by-geometry`): a Mover's wireframe outline is
 * its only visible representation in every shading mode (its solid geometry is hidden by default,
 * `Viewport3D.tsx`'s `showMoverSolid` toggle), so it must always composite on top like the selected
 * ring above -- `depthTest={false}` + a renderOrder over the solid mesh. Ordinary (non-Mover) thin
 * rings keep normal depth-testing, unaffected -- this only applies to the caller's Mover-only rings. */
function MergedThinWireframe({ rings, alwaysOnTop = false }: { rings: BrushRing[]; alwaysOnTop?: boolean }) {
  const merged = useMemo(() => mergeThinRings(rings), [rings])
  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(merged.positions, 3))
    geo.setAttribute('color', new THREE.BufferAttribute(merged.colors, 3))
    return geo
  }, [merged])
  useEffect(() => () => geometry.dispose(), [geometry])
  if (merged.segmentOwners.length === 0) return null
  return (
    <lineSegments
      geometry={geometry}
      userData={{ segmentOwners: merged.segmentOwners }}
      renderOrder={alwaysOnTop ? MOVER_RING_RENDER_ORDER : 0}
    >
      <lineBasicMaterial vertexColors depthTest={!alwaysOnTop} />
    </lineSegments>
  )
}

/** The selected brush's ring. Drawn with the same reliable `LineBasicMaterial`/`LineLoop` path the
 * thin rings use -- the `Line2`/`LineMaterial` pixel-width path that used to live here rendered
 * NOTHING (a long-suspected silent no-op, confirmed live 2026-09-16: forcing its colour to pure
 * white left the selected ring unchanged, because only the thin merged ring was ever drawing). It's
 * drawn in the brush's plain, undimmed CSG `WireColor` (`resolveWireColor`), with `depthTest={false}` and a high
 * `renderOrder` so it draws OVER the solid mesh and through walls -- a selected brush must always
 * show its outline, brighter, in every pane and shading mode (owner ruling). `<lineLoop>` auto-closes
 * the ring. `userData.actorName` lets the viewport raycast resolve a hit back to this actor. */
function BoldRing({ verts, color, actorName }: { verts: number[]; color: THREE.Color; actorName: string }) {
  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3))
    return geo
  }, [verts])
  useEffect(() => () => geometry.dispose(), [geometry])
  return (
    <lineLoop geometry={geometry} userData={{ actorName }} renderOrder={SELECTED_RING_RENDER_ORDER}>
      <lineBasicMaterial color={color} depthTest={false} transparent={false} />
    </lineLoop>
  )
}

export interface BrushOutlinesProps {
  actors: SceneActor[]
  selectedNames: ReadonlySet<string>
  mode: BrushRingMode
  // Exposes the rendered ring objects for the outer viewport's click-to-select raycast (bug report
  // item 6: in wireframe/ortho views, a click must only hit a brush's own outline LINES, never
  // anywhere inside its silhouette) -- mirrors Viewport3D/OrthoViewport's existing `markerGroupRef`
  // pattern for marker sprites.
  groupRef?: MutableRefObject<THREE.Group | null>
}

// `'csg-all'` mode's ring SET (every brush actor's own rings) never actually depends on
// `selectedNames` -- only which of those same rings ALSO gets a bold overlay does. A fixed empty
// selection here lets `csgAllRings` below memoize on `[actors]` alone, so selecting a brush in an
// ortho pane (always `'csg-all'` -- GUI.md "the ortho panes can never change mode") never forces
// `MergedThinWireframe` to rebuild the WHOLE level's merged wireframe buffer. It used to: measured
// bug, >1s click-to-highlight latency, since that rebuild's cost scales with the total scene poly
// count, not the one actor whose selection changed, and it re-ran in all three ortho panes at once.
const EMPTY_SELECTION: ReadonlySet<string> = new Set()

/** Renders every ring `buildBrushRings` selects for `mode` -- ordinary weight for every non-selected
 * brush (`'csg-all'`) or nothing (`'selected-only'` when unselected), bold for every SELECTED one
 * (Part 3, Task 14: one ring per selected actor, not just one overall). Non-bold rings share ONE
 * merged draw call (`MergedThinWireframe`, item 4); bold (selected) rings stay individual `BoldRing`
 * objects -- there are only ever a handful of those, so merging them buys nothing and would lose
 * `Line2`'s real pixel-width support.
 *
 * A selected actor's ring is drawn in BOTH the thin merged buffer and as a bold overlay, rather than
 * excluded from the former: `BoldRing` draws on top with `depthTest={false}`, fully covering the
 * same-position, same-color thin line beneath it -- visually identical to exclusion, but it lets the
 * (expensive, whole-level) `'csg-all'` thin buffer skip rebuilding on a selection change. A ring's
 * own content (verts/color/actorName) doesn't depend on mode, only its inclusion/`bold` flag does --
 * so `'selected-only'`'s own ring list (already small, and already keyed on `selectedNames`) doubles
 * as the bold-overlay source for BOTH modes. */
export function BrushOutlines({ actors, selectedNames, mode, groupRef }: BrushOutlinesProps) {
  const csgAllRings = useMemo(() => buildBrushRings(actors, EMPTY_SELECTION, 'csg-all'), [actors])
  const selectedOnlyRings = useMemo(() => buildBrushRings(actors, selectedNames, 'selected-only'), [actors, selectedNames])
  const boldRings = useMemo(() => selectedOnlyRings.filter((r) => r.bold), [selectedOnlyRings])
  const thinRings = useMemo(
    () => (mode === 'csg-all' ? csgAllRings : selectedOnlyRings.filter((r) => !r.bold)),
    [mode, csgAllRings, selectedOnlyRings],
  )
  // Movers always render depthTest-off (see MergedThinWireframe's `alwaysOnTop` doc) -- split out of
  // the ordinary merged buffer so non-Mover thin rings keep normal depth-testing, unaffected.
  const thinMoverRings = useMemo(() => thinRings.filter((r) => r.isMover), [thinRings])
  const thinOtherRings = useMemo(() => thinRings.filter((r) => !r.isMover), [thinRings])
  return (
    <group ref={groupRef}>
      <MergedThinWireframe rings={thinOtherRings} />
      <MergedThinWireframe rings={thinMoverRings} alwaysOnTop />
      {boldRings.map((ring, i) => {
        // A selected brush's ring shows its plain, undimmed WireColor -- real UED22 doesn't brighten
        // on select at all (`DrawColor = WireColor * 1.0` when selected, `* 0.5` when not,
        // `selectionColor.ts`'s doc comment); the visible change is the UNSELECTED thin rings being
        // dimmed instead (`mergeThinRings`), not this one getting brighter.
        const color = toThreeColor(resolveWireColor(ring.csgClass, ring.color))
        return <BoldRing key={`${ring.actorName}-${i}`} verts={ring.verts} color={color} actorName={ring.actorName} />
      })}
    </group>
  )
}
