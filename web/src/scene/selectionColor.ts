import * as THREE from 'three'

// Real UED22 brush-wireframe selection mechanism (GUI-PARITY.md "Brush wireframe selection color",
// `UnEdRend.cpp`'s `DrawLevelBrush`, source-confirmed 2026-09-16 -- owner report "brush colors seem
// off, at least on highlight" traced this codebase's PREVIOUS `brightenWireColor` (lift 45% toward
// white on select) to a double error: (1) it conflated two DIFFERENT real formulas --
// `DrawColor = WireColor * (selected ? 1.0 : 0.5)` for the brush wire itself, `VertexColor =
// WireColor * 1.2` for the vertex-handle dots ONLY -- into one function applied to both; (2) UED22
// doesn't brighten on select at all, it DIMS when NOT selected. Direction was backwards.
//
// `WireColor` itself is chosen per brush CSG kind -- these are UED22's real `Default.ini` values
// (`Engine/Config/Default.ini`, v200 shipped defaults; not yet confirmed against this project's
// actual DeusEx-customized `Editor.dll`/its own `.ini`, same gap noted throughout GUI-PARITY.md),
// not this codebase's previous `preview.py`-derived, dark-bg-tuned palette. Scoped to the web GUI
// only (owner ruling 2026-09-16) -- `preview.py`'s own `_CSG_PALETTE` (actor diagram/level
// photo/eval screenshots) is untouched.
export const CSG_WIRE_COLOR: Record<string, [number, number, number]> = {
  add: [127, 127, 255],
  subtract: [255, 192, 63],
  // `semisolid` is NOT a real UED22 `Default.ini` value (unlike its siblings above) -- that value,
  // (127,255,0), came from the now-banned third-party UE1 source (GUI-PARITY.md, owner ruling
  // 2026-09-18) and read as bright green, clashing with `mover`. Replaced with this project's own
  // established, deliberate convention instead: `preview.py`'s `_CSG_PALETTE["semisolid"]` front
  // value, a warm coral chosen specifically to stay distinct from mover's magenta (see that file's
  // comment). Scaling this by the 0.5 unselected factor below (~118,60,40) already lands close to
  // `_CSG_PALETTE`'s own back/unselected tuple (125,62,40) -- no second value needed here.
  semisolid: [235, 120, 80],
  nonsolid: [63, 192, 32],
  mover: [255, 0, 255],
}

/** The real `WireColor` for a brush's CSG kind, or `fallback` (the server's own color, currently
 * `preview.py`'s tuned palette) for a `csgClass` not in the faithful table above -- e.g. intersect/
 * deintersect, which this codebase doesn't yet distinguish from `add` server-side (a separate,
 * already-tracked gap, `gui-csg-brush-coloring-never-distinguishes`; not silently guessed here). */
export function resolveWireColor(csgClass: string, fallback: [number, number, number]): [number, number, number] {
  return CSG_WIRE_COLOR[csgClass] ?? fallback
}

/** A plain per-channel multiply, clamped to a byte -- `DrawColor`'s 0.5 (unselected-brush dim) and
 * `VertexColor`'s 1.2 (vertex-handle dots, always brightened regardless of selection) both reduce to
 * this same real UED22 operation, just a different factor. */
export function scaleColor(rgb: [number, number, number], factor: number): [number, number, number] {
  return [
    Math.min(255, Math.round(rgb[0] * factor)),
    Math.min(255, Math.round(rgb[1] * factor)),
    Math.min(255, Math.round(rgb[2] * factor)),
  ]
}

export function toThreeColor(rgb: [number, number, number]): THREE.Color {
  return new THREE.Color(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
}

// UED22's own selected-actor colors for sprites/meshes (GUI-PARITY.md "Selection highlight
// rendering" -- NOT this codebase's own invention, except where noted). The sprite tint, mesh
// ambient-bias, and mesh wireframe-edge formulas are all ✅ binary-confirmed (disassembly of this
// project's own `render.dll`, not the third-party UE1 v200 source tree that first surfaced them --
// see GUI-PARITY.md's "Mesh-actor wireframe rendering" section for the wire-color instruction trace).
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
// - Mesh actor, wireframe (`DrawLodMesh`, reached via `DrawMesh`'s dispatch, RVA `0xd050`): flat
//   edge-line color, selected (.2,.8,.1), unselected (.6,.4,.1) -- an olive/brown, not white.
export const SELECTED_SPRITE_TINT = new THREE.Color(0.5, 0.9, 0.5)
// The explicit UNSELECTED value for the same prop -- react-three-fiber treats an `undefined` prop
// as "leave whatever's already applied alone," not "reset to default," so a spriteMaterial's
// `color` must be given a real value in BOTH branches or a deselected sprite keeps its last tint
// forever (bug: point actors stayed green after deselection). Plain white is the identity
// multiplier over the sprite's own map/color, matching UED22's own `(1,1,1)` unselected constant.
export const UNSELECTED_SPRITE_TINT = new THREE.Color(1, 1, 1)
export const SELECTED_MESH_WIRE_COLOR = new THREE.Color(0.2, 0.8, 0.1)
export const UNSELECTED_MESH_WIRE_COLOR = new THREE.Color(0.6, 0.4, 0.1)
