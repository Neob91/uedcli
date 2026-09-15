// Constant-screen-size point-actor marker sprite (bug report: point actors, at ordinary
// level-viewing distances, shrink to sub-pixel size and read as "not rendering") -- shared by
// Viewport3D.tsx (perspective) and OrthoViewport.tsx (the three ortho panes), which used a FIXED
// world-unit `scale` before this. Ports `SelectionMarkers.tsx`'s `PivotMarker` technique: rescale
// the sprite every frame from the live camera/viewport state via `worldUnitsPerPixelAt`, instead of
// a fixed world-unit `scale` prop.
import { useRef } from 'react'
import type { ReactNode } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'

import { markerSpriteScale, worldUnitsPerPixelAt } from './markers'

export interface PointActorMarkerProps {
  position: [number, number, number]
  // Real class icon's `width / height` world-space footprint (preserves the icon's own aspect
  // ratio); pass 1 for the square fallback dot.
  aspect: number
  userData?: Record<string, unknown>
  // Ortho panes draw markers on top of brush wireframe/highlight (owner ruling, ortho only) via a
  // higher renderOrder than everything else in the pane; the perspective pane leaves this unset
  // (its own scene-graph/insertion order is fine there).
  renderOrder?: number
  // The `<spriteMaterial>` -- each caller keeps its own material props (map/color/depthTest/
  // depthWrite), which differ between the perspective and ortho panes (item 16: only the per-frame
  // rescale plumbing is shared, not the material).
  children: ReactNode
}

export function PointActorMarker({ position, aspect, userData, renderOrder, children }: PointActorMarkerProps) {
  const spriteRef = useRef<THREE.Sprite>(null)
  const { camera, size } = useThree()
  useFrame(() => {
    const sprite = spriteRef.current
    if (!sprite) return
    const worldPos = new THREE.Vector3(...position)
    const [width, height] = markerSpriteScale(worldUnitsPerPixelAt(camera, worldPos, size.height), aspect)
    sprite.scale.set(width, height, 1)
  })
  return (
    <sprite ref={spriteRef} position={position} userData={userData} renderOrder={renderOrder}>
      {children}
    </sprite>
  )
}
