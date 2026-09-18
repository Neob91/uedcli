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
}

export function SelectedMeshWireframe({ positions, triangleOwners, selectedActorNames }: SelectedMeshWireframeProps) {
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
  }, [positions, triangleOwners, selectedActorNames])
  useEffect(() => () => geometry?.dispose(), [geometry])

  if (!geometry) return null
  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color={SELECTED_MESH_WIRE_COLOR} depthTest={false} />
    </lineSegments>
  )
}
