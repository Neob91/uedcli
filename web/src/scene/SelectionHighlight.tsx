// Issue 1 fix (2026-09-15): the "lights up" surface highlight for every selected brush. Renders an
// overlay mesh restricted to just the selected triangles (`selectedTriangleIndices`), sharing the
// base geometry's `position` attribute directly (an indexed subset -- no vertex data duplicated, one
// small index buffer), drawn with additive-white blending: a pure brightness boost on top of the
// actor's own material/texture/CSG hue, per `selectedTriangles.ts`'s doc comment (matches
// `BrushOutlines`' "same hue, just bolder" convention rather than painting an alien highlight color).
// Shared by both Viewport3D and OrthoViewport, mirroring BrushOutlines/SelectionMarkers' own
// cross-pane sharing. Only meaningful when the base mesh itself is drawn (not in 'wireframe' mode,
// which has no surface to light up) -- callers gate on `mode !== 'wireframe'`, same as the base mesh.
import { useEffect, useMemo } from 'react'
import * as THREE from 'three'

import { selectedTriangleIndices } from './selectedTriangles'

// Additive white, not a new hue -- a brightness boost that reads correctly over any base texture/CSG
// color. Moderate opacity so it reads as "lit up," not a blown-out white silhouette.
const HIGHLIGHT_COLOR = 0xffffff
const HIGHLIGHT_OPACITY = 0.25

export interface SelectionHighlightProps {
  bufferGeometry: THREE.BufferGeometry
  triangleOwners: (string | null)[]
  selectedNames: ReadonlySet<string>
}

export function SelectionHighlight({ bufferGeometry, triangleOwners, selectedNames }: SelectionHighlightProps) {
  const indices = useMemo(
    () => selectedTriangleIndices(triangleOwners, selectedNames),
    [triangleOwners, selectedNames],
  )
  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', bufferGeometry.attributes.position)
    geo.setIndex(indices)
    return geo
  }, [bufferGeometry, indices])
  // Only the overlay geometry (the index buffer) is ours to dispose -- `position` is a SHARED
  // reference to the base mesh's own attribute, still in use by it after this unmounts/rebuilds.
  useEffect(() => () => geometry.dispose(), [geometry])
  const material = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: HIGHLIGHT_COLOR,
        transparent: true,
        opacity: HIGHLIGHT_OPACITY,
        blending: THREE.AdditiveBlending,
        depthWrite: false, // a pure visual overlay -- never occludes anything behind it
        polygonOffset: true, // avoid z-fighting against the base mesh's own coplanar triangles
        polygonOffsetFactor: -1,
        polygonOffsetUnits: -1,
      }),
    [],
  )
  useEffect(() => () => material.dispose(), [material])
  if (indices.length === 0) return null
  return <mesh geometry={geometry} material={material} />
}
