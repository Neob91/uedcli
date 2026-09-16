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

// UED22's own selected-actor colors for sprites/meshes (GUI-PARITY.md "Selection highlight
// rendering" -- NOT this codebase's own invention). The sprite tint and mesh ambient-bias formulas
// are ✅ binary-confirmed (disassembly of this project's own `render.dll`, not just the third-party
// UE1 v200 source tree that first surfaced them); the wireframe edge colors are data-confirmed in
// the same binary but not instruction-linked (still essentially certain -- see GUI-PARITY.md).
// Three distinct techniques, one constant each:
//
// - Point-actor sprite (`DrawActorSprite`): a MULTIPLICATIVE tint on the icon texture,
//   `Color = bSelected ? (.5,.9,.5) : (1,1,1)` -- halves R/B, keeps G near-full. Apply as
//   `SELECTED_SPRITE_TINT` multiplied onto whatever color the sprite would otherwise use.
// - Mesh actor, solid shading (`DrawMesh`): the ambient/unlit floor is rescaled,
//   `floor*0.4 + (0,0.6,0)` when selected. This codebase's `MeshBasicMaterial`-only pipeline has no
//   equivalent ambient/lit split to target directly, so the formula is applied to the whole
//   finished pixel instead -- the closest available term, not UED22's exact decomposition. Reaches
//   the identical result via normal (non-additive) alpha blending a PURE green (0,1,0) source at
//   0.6 opacity over the base pixel: `src*a + dst*(1-a)` with a=0.6, src=(0,1,0) reduces exactly to
//   `dst*0.4 + (0,0.6,0)` -- ordinary alpha blending, not a custom WebGL blend factor.
// - Mesh actor, wireframe (`DrawMesh`, the `bWire` branch): flat edge-line color, selected
//   (.2,.8,.1), unselected (.6,.4,.1) -- an olive/brown, not white.
export const SELECTED_SPRITE_TINT = new THREE.Color(0.5, 0.9, 0.5)
// The explicit UNSELECTED value for the same prop -- react-three-fiber treats an `undefined` prop
// as "leave whatever's already applied alone," not "reset to default," so a spriteMaterial's
// `color` must be given a real value in BOTH branches or a deselected sprite keeps its last tint
// forever (bug: point actors stayed green after deselection). Plain white is the identity
// multiplier over the sprite's own map/color, matching UED22's own `(1,1,1)` unselected constant.
export const UNSELECTED_SPRITE_TINT = new THREE.Color(1, 1, 1)
export const SELECTED_MESH_SOLID_OVERLAY_COLOR = 0x00ff00
export const SELECTED_MESH_SOLID_OVERLAY_OPACITY = 0.6
export const SELECTED_MESH_WIRE_COLOR = new THREE.Color(0.2, 0.8, 0.1)
export const UNSELECTED_MESH_WIRE_COLOR = new THREE.Color(0.6, 0.4, 0.1)
