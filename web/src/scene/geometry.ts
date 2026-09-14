// Scene payload -> a drawable geometry: flat position/UV buffers plus a masked/non-masked group
// split (Viewport3D.tsx's two-group material split, so the atlas alpha test only applies to polys
// whose `masked` flag is set -- a non-masked poly using a texture whose mask marks index-0 texels
// must still render solid). Pure and framework-free so it's testable without a WebGL context.
import type { AtlasPayload } from '../api'
import type { ScenePoly } from '../api'

export interface GeometryData {
  positions: Float32Array // flat [x,y,z, ...], one triangle's 3 verts at a time
  uvs: Float32Array // flat [u,v, ...], atlas-space, aligned with `positions`
  /** Contiguous [start, count] triangle-vertex ranges for the non-masked and masked groups (three.js
   * BufferGeometry group semantics: start/count are counted in VERTICES, matching a non-indexed
   * geometry). Either may be empty (count 0) if the scene has no polys of that kind. */
  groups: { nonMasked: { start: number; count: number }; masked: { start: number; count: number } }
}

function dot(a: number[], b: number[]): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}

function mod(v: number, m: number): number {
  if (m <= 0) return 0
  return ((v % m) + m) % m
}

/** One poly's per-vertex atlas UVs, tiling the source texture within its atlas rect (texel
 * coordinates wrap into [0, w) x [0, h) before mapping into the rect -- an approximation: an
 * atlas-packed texture can't repeat past its own tile boundary without bleeding, which Slice 1's
 * unlit draw accepts (the pixel-identical still is the Slice 2 photo endpoint, not this viewport). */
function polyUVs(poly: ScenePoly, atlas: AtlasPayload): [number, number][] {
  const rect = atlas.manifest[String(poly.tex_index)]
  if (poly.tex_index < 0 || !rect) {
    return poly.verts.length > 0 ? Array(poly.verts.length / 3).fill([0, 0]) : []
  }
  const out: [number, number][] = []
  for (let i = 0; i < poly.verts.length; i += 3) {
    const v = [poly.verts[i], poly.verts[i + 1], poly.verts[i + 2]]
    const rel = [v[0] - poly.base[0], v[1] - poly.base[1], v[2] - poly.base[2]]
    const texelU = dot(rel, poly.tu) + poly.pan[0]
    const texelV = dot(rel, poly.tv) + poly.pan[1]
    const u = (rect.x + mod(texelU, rect.w)) / atlas.width
    const v2 = (rect.y + mod(texelV, rect.h)) / atlas.height
    out.push([u, v2])
  }
  return out
}

/** Fan-triangulate a convex n-gon ring (BSP node polys are convex) into flat position/UV arrays. */
function appendTriangleFan(
  poly: ScenePoly,
  uvs: [number, number][],
  positions: number[],
  uvOut: number[],
): void {
  const n = poly.verts.length / 3
  for (let i = 1; i < n - 1; i++) {
    for (const idx of [0, i, i + 1]) {
      positions.push(poly.verts[idx * 3], poly.verts[idx * 3 + 1], poly.verts[idx * 3 + 2])
      uvOut.push(uvs[idx][0], uvs[idx][1])
    }
  }
}

export function buildGeometryData(polys: ScenePoly[], atlas: AtlasPayload): GeometryData {
  const nonMaskedPos: number[] = []
  const nonMaskedUV: number[] = []
  const maskedPos: number[] = []
  const maskedUV: number[] = []

  for (const poly of polys) {
    if (poly.verts.length < 9) continue // degenerate (<3 verts): nothing to draw
    const uvs = polyUVs(poly, atlas)
    if (poly.masked) {
      appendTriangleFan(poly, uvs, maskedPos, maskedUV)
    } else {
      appendTriangleFan(poly, uvs, nonMaskedPos, nonMaskedUV)
    }
  }

  const positions = new Float32Array([...nonMaskedPos, ...maskedPos])
  const uvs = new Float32Array([...nonMaskedUV, ...maskedUV])
  const nonMaskedCount = nonMaskedPos.length / 3
  const maskedCount = maskedPos.length / 3
  return {
    positions,
    uvs,
    groups: {
      nonMasked: { start: 0, count: nonMaskedCount },
      masked: { start: nonMaskedCount, count: maskedCount },
    },
  }
}
