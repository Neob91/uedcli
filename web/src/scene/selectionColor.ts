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
// rendering" -- NOT this codebase's own invention, except where noted). The sprite tint and mesh
// ambient-bias formulas are ✅ binary-confirmed (disassembly of this project's own `render.dll`, not
// just the third-party UE1 v200 source tree that first surfaced them); the wireframe edge colors are
// data-confirmed in the same binary but not instruction-linked (still essentially certain -- see
// GUI-PARITY.md).
//
// - Point-actor sprite (`DrawActorSprite`): a MULTIPLICATIVE tint on the icon texture,
//   `Color = bSelected ? (.5,.9,.5) : (1,1,1)` -- halves R/B, keeps G near-full. Apply as
//   `SELECTED_SPRITE_TINT` multiplied onto whatever color the sprite would otherwise use.
// - Mesh actor, solid shading: UED22's real `DrawMesh` rescales the ambient/unlit floor,
//   `floor*0.4 + (0,0.6,0)` -- a bias on the pre-lighting term, not a flat tint on the finished
//   pixel. This codebase's `MeshBasicMaterial`-only pipeline has no equivalent ambient/lit split to
//   target, so an EARLIER version of this file applied that formula (via alpha blending) to the
//   whole finished pixel instead -- live-tested 2026-09-16 and rejected: it read as a flat, washed-
//   out solid green that crushed all texture/shading detail (owner: "much lighter green" than real
//   UED22), and broke NPC glasses/hair masked materials. Replaced by a DELIBERATE STYLE CHOICE, not
//   a UED22 formula: the SAME multiplicative technique as the point-actor sprite above
//   (`SELECTED_SPRITE_TINT`, opaque, always sampling the base texture) -- preserves texture/shading
//   detail, reuses one proven mechanism instead of two, and reads closer to the owner's own memory
//   of the real editor than the literal-formula approximation did. The literal `DrawMesh` formula
//   stays documented in `GUI-PARITY.md` as what real UED22 does; this implementation now knowingly
//   departs from it.
// - Mesh actor, wireframe (`DrawMesh`, the `bWire` branch): flat edge-line color, selected
//   (.2,.8,.1), unselected (.6,.4,.1) -- an olive/brown, not white.
export const SELECTED_SPRITE_TINT = new THREE.Color(0.5, 0.9, 0.5)
// The explicit UNSELECTED value for the same prop -- react-three-fiber treats an `undefined` prop
// as "leave whatever's already applied alone," not "reset to default," so a spriteMaterial's
// `color` must be given a real value in BOTH branches or a deselected sprite keeps its last tint
// forever (bug: point actors stayed green after deselection). Plain white is the identity
// multiplier over the sprite's own map/color, matching UED22's own `(1,1,1)` unselected constant.
export const UNSELECTED_SPRITE_TINT = new THREE.Color(1, 1, 1)
export const SELECTED_MESH_WIRE_COLOR = new THREE.Color(0.2, 0.8, 0.1)
export const UNSELECTED_MESH_WIRE_COLOR = new THREE.Color(0.6, 0.4, 0.1)
