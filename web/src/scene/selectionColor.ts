import * as THREE from 'three'

// A selected brush's outline ring (BrushOutlines) and its vertex-handle dots (SelectionMarkers) are
// drawn in a clearly BRIGHTER version of the brush's own CSG hue, so a selected brush visibly pops in
// every pane and mode (owner ruling: it must be obviously brighter). A plain `WireColor * 1.2`
// multiply (UED22's `_brighten`, preview.py) barely moves a saturated CSG colour -- a blue `add`
// brush (70,110,255) has a channel already maxed, so multiplying does almost nothing. Instead lift
// each channel a fixed fraction of the way to white: that brightens EVERY hue, saturated or not,
// while keeping it recognisably the CSG colour.
export const SELECTION_WHITE_LIFT = 0.45

export function brightenWireColor(rgb: [number, number, number], lift = SELECTION_WHITE_LIFT): THREE.Color {
  const toward = (c: number) => (c / 255) + (1 - c / 255) * lift
  return new THREE.Color(toward(rgb[0]), toward(rgb[1]), toward(rgb[2]))
}
