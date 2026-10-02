// Mesh-actor wireframe overlay (GUI.md "Shading modes"): a mesh actor's own triangle-edge
// wireframe, drawn only in wireframe mode -- real UnrealEd renders a mesh as wireframe there too,
// matching its brush convention (`BrushOutlines.tsx`), never solid or hidden. Shared by Viewport3D
// and OrthoViewport so both panes draw the identical geometry
// (`SceneResourcesContext.tsx`'s `meshWireframeGeometry`).
//
// Colored per UED22's own measured convention (GUI-PARITY.md "Mesh-actor wireframe rendering",
// `render.dll`'s `DrawLodMesh`, own-binary disassembly-confirmed) -- an olive/brown baseline, not
// the plain white this used before that finding landed.
import { useEffect, useMemo } from 'react'
import * as THREE from 'three'

import type { Vec3 } from './camera'
import { SELECTED_MESH_WIRE_COLOR, UNSELECTED_MESH_WIRE_COLOR } from './selectionColor'

export function MeshWireframe({ geometry }: { geometry: THREE.BufferGeometry }) {
  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color={UNSELECTED_MESH_WIRE_COLOR} />
    </lineSegments>
  )
}

/** The SELECTED subset of the mesh-actor wireframe, drawn on top of `MeshWireframe`'s baseline in
 * UED22's own selected-edge color. A small, separately-built `THREE.WireframeGeometry` over just
 * the selected actors' own triangles (typically 0-2 actors), rather than threading owner data
 * through the shared merged wireframe's own edge extraction (`THREE.WireframeGeometry` dedupes
 * shared edges internally, discarding per-triangle owner correspondence) -- cheap because a
 * selection is small, and it reuses the exact same triangle positions `meshPickGeometry` already
 * carries (`SceneResourcesContext.tsx`), just filtered. */
export interface SelectedMeshWireframeProps {
  positions: Float32Array
  triangleOwners: (string | null)[]
  selectedActorNames: ReadonlySet<string>
  // Perf fix's own follow-on correctness fix: `positions` is `meshPickGeometry`'s LIVE position
  // buffer, now live-PATCHED in place for a staged mesh-actor move (`usePatchedMeshPositions`) rather
  // than replaced with a new array each frame -- so `positions`' own REFERENCE never changes during a
  // drag, even though its CONTENT does, and this component's memo below would never re-run without
  // some OTHER trigger. `stagedOffsets` (unused inside the memo body -- it exists purely as an
  // invalidation signal) is that trigger: a genuinely new object every frame a staged move is active,
  // forcing a re-read of `positions`' current (patched) values. Rebuilding this SMALL geometry every
  // such frame is cheap (bounded by selection size, per this component's own doc comment above).
  stagedOffsets: Readonly<Record<string, Vec3>>
}

export function SelectedMeshWireframe({
  positions,
  triangleOwners,
  selectedActorNames,
  stagedOffsets,
}: SelectedMeshWireframeProps) {
  const geometry = useMemo(() => {
    if (selectedActorNames.size === 0) return null
    const filtered: number[] = []
    for (let tri = 0; tri < triangleOwners.length; tri++) {
      const owner = triangleOwners[tri]
      if (owner == null || !selectedActorNames.has(owner)) continue
      const base = tri * 9 // 3 verts * 3 components, flat position array order matches triangleOwners
      for (let i = 0; i < 9; i++) filtered.push(positions[base + i])
    }
    if (filtered.length === 0) return null
    const trianglesGeo = new THREE.BufferGeometry()
    trianglesGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(filtered), 3))
    const wire = new THREE.WireframeGeometry(trianglesGeo)
    trianglesGeo.dispose()
    return wire
    // stagedOffsets is deliberately listed but not read: see this prop's own doc comment above (a
    // pure invalidation trigger, since `positions`' own reference never changes from an in-place patch).
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [positions, triangleOwners, selectedActorNames, stagedOffsets])
  useEffect(() => () => geometry?.dispose(), [geometry])

  if (!geometry) return null
  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color={SELECTED_MESH_WIRE_COLOR} depthTest={false} />
    </lineSegments>
  )
}
