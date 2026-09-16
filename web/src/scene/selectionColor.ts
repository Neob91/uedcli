import * as THREE from 'three'

// UED22's own selected/highlighted-brush wire brightening: `WireColor * 1.2`, each channel clamped
// to 1 (the `_brighten(rgb, 1.2)` transform from DrawLevelBrush / UnEdRend.cpp, ported in
// `uedcli/preview.py`). Shared so a selected brush's bold OUTLINE ring (BrushOutlines) and its
// vertex-handle dots (SelectionMarkers) brighten by one identical rule -- a selected brush reads as
// its own CSG hue, brightened, in every pane and mode.
export const SELECTION_BRIGHTEN = 1.2

export function brightenWireColor(rgb: [number, number, number], factor = SELECTION_BRIGHTEN): THREE.Color {
  return new THREE.Color(
    Math.min(1, (rgb[0] / 255) * factor),
    Math.min(1, (rgb[1] / 255) * factor),
    Math.min(1, (rgb[2] / 255) * factor),
  )
}
