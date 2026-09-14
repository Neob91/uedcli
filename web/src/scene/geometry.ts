// Scene payload -> a drawable geometry: flat position/UV buffers split into one group per
// (texture, masked?) pair. Each group draws with its OWN THREE.Texture (RepeatWrapping), so a world
// BSP surface can tile its texture across many repeats -- UVs are the RAW texel coordinates divided
// by the texture's own size (0..N over N tiles), NOT packed into a shared atlas rect (which collapsed
// a whole-tile-spanning surface to one texel; Viewport3D.tsx extracts a per-texture texture from the
// atlas image). Pure and framework-free so it's testable without a WebGL context.
import type { AtlasPayload } from '../api'
import type { ScenePoly } from '../api'

/** One contiguous [start, count] triangle-vertex range (three.js BufferGeometry group semantics:
 * start/count counted in VERTICES, matching a non-indexed geometry), tagged with the texture and
 * mask state it must draw with. `texIndex` -1 is untextured (flat grey, no map). Viewport3D maps
 * each group to a material. */
export interface GeometryGroup {
  texIndex: number
  masked: boolean
  start: number
  count: number
}

export interface GeometryData {
  positions: Float32Array // flat [x,y,z, ...], one triangle's 3 verts at a time
  uvs: Float32Array // flat [u,v, ...], texture-space (1.0 = one tile), aligned with `positions`
  groups: GeometryGroup[] // one per (texIndex, masked) pair present, in first-seen order
}

function dot(a: number[], b: number[]): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}

/** One poly's per-vertex UVs in the source texture's own coordinate space: the raw texel
 * coordinate divided by the texture's size, so a surface spanning N tiles yields UVs 0..N and
 * RepeatWrapping tiles the texture. No `mod`, no atlas rect. The texture's size is the manifest
 * rect's w/h (one rect = one whole texture). Untextured (tex_index < 0 / no rect) -> (0,0). */
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
    out.push([texelU / rect.w, texelV / rect.h])
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

interface Bucket {
  texIndex: number
  masked: boolean
  pos: number[]
  uv: number[]
}

export function buildGeometryData(polys: ScenePoly[], atlas: AtlasPayload): GeometryData {
  const buckets = new Map<string, Bucket>()
  const order: string[] = []

  for (const poly of polys) {
    if (poly.verts.length < 9) continue // degenerate (<3 verts): nothing to draw
    const uvs = polyUVs(poly, atlas)
    const key = `${poly.tex_index}:${poly.masked ? 1 : 0}`
    let bucket = buckets.get(key)
    if (!bucket) {
      bucket = { texIndex: poly.tex_index, masked: poly.masked, pos: [], uv: [] }
      buckets.set(key, bucket)
      order.push(key)
    }
    appendTriangleFan(poly, uvs, bucket.pos, bucket.uv)
  }

  const positions: number[] = []
  const uvs: number[] = []
  const groups: GeometryGroup[] = []
  for (const key of order) {
    const bucket = buckets.get(key) as Bucket
    const start = positions.length / 3
    positions.push(...bucket.pos)
    uvs.push(...bucket.uv)
    groups.push({ texIndex: bucket.texIndex, masked: bucket.masked, start, count: bucket.pos.length / 3 })
  }

  return { positions: new Float32Array(positions), uvs: new Float32Array(uvs), groups }
}
