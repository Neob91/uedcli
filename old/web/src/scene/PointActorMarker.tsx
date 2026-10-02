// World-space point-actor marker sprite -- a DT_Sprite billboard drawn at its real WORLD footprint
// (DrawScale x texel size, UED22 parity), so it foreshortens with distance (perspective) and shrinks
// when you zoom out (ortho) like ordinary geometry, instead of holding a constant screen size (owner:
// markers must not grow relative to the world as you zoom out). Shared by Viewport3D.tsx (perspective)
// and OrthoViewport.tsx (ortho). three.js Sprites billboard toward the camera in-shader, so no
// per-frame CPU rescale is needed -- a static world `scale` suffices, and it stays a correct, upright,
// un-mirrored w x h billboard inside the reflected `<group scale={[1,-1,1]}>` (the sprite shader reads
// the sign-free lengths of the model-matrix columns for its size).
import type { ReactNode } from 'react'

export interface PointActorMarkerProps {
  position: [number, number, number]
  // The billboard's world-space (UU) footprint: `ActorSprite.width`/`height` for a resolved class
  // icon, or `DEFAULT_MARKER_FOOTPRINT_UU` square for the fallback grey dot.
  width: number
  height: number
  userData?: Record<string, unknown>
  // Both panes pass `MARKER_RENDER_ORDER` (`markers.ts`) so a marker composites after any
  // coincident-depth transparent overlay (a surface highlight, e.g.) regardless of the two
  // objects' meaningless distance tiebreak -- see that constant's doc comment for the mechanism.
  renderOrder?: number
  // The `<spriteMaterial>` -- each caller sets its own map/color/depthTest (which differ by pane and
  // shading mode: depthTest is off in wireframe, on otherwise).
  children: ReactNode
}

export function PointActorMarker({ position, width, height, userData, renderOrder, children }: PointActorMarkerProps) {
  return (
    <sprite position={position} scale={[width, height, 1]} userData={userData} renderOrder={renderOrder}>
      {children}
    </sprite>
  )
}
