// Scene payload -> a drawable geometry: flat position/UV/color buffers split into one group per
// (texture, masked?, two_sided?, blend, lightmap?) tuple. Each group draws with its OWN THREE.Texture
// (RepeatWrapping) for the base map. Lit polys additionally carry a second UV set (`uv1`) into the
// lightmap atlas; unlit polys carry a per-vertex KEY_LIGHT flat shade in `colors`. This mirrors
// `level photo --native`'s render.rs: a lightmapped world surf is base*lumel; everything else is
// base*flatShade. Pure and framework-free so it's testable without a WebGL context.
import type { AtlasPayload, LightmapPayload, ScenePoly } from '../api'

/** The fixed key-light direction render.rs shades unlit faces against (render.rs `KEY_LIGHT`). */
const KEY_LIGHT: [number, number, number] = [-0.408, -0.577, 0.707]

/** Global fan winding for backface culling. render.rs culls single-sided faces by normal·camera
 * (`light_in_front`); three.js `FrontSide` culls by screen-space CCW winding, so ONE global order
 * must make the two agree. This was verified `false` (unreversed) against `Viewport3D`'s `CameraRig`
 * BEFORE `applyCameraPose` gained its projection-matrix mirror (`Viewport3D.tsx`'s own doc comment:
 * negates `projectionMatrix.elements[0]` to fix meshes rendering left-right reverted). That mirror
 * flips every triangle's APPARENT screen-space winding uniformly (a horizontal flip always reverses
 * signed area), which three.js's culling never compensates for on its own (it only auto-flips
 * winding from an object's OWN `matrixWorld` determinant, never the camera's) -- so the earlier
 * verification went stale the moment the mirror landed, silently culling the wrong face on every
 * single-sided wall (confirmed live: CSG subtracts and additive brushes appeared to swap which face
 * is visible). Superseded: the handedness fix moved from the projection matrix to a reflected
 * `<group scale={[1,-1,1]}>` around all world content (viewportRender.ts). three.js DOES auto-flip
 * `frontFace` from that group's negative `matrixWorld` determinant, so the natural winding is correct
 * again and this returns to `false` -- render.rs's own order, no per-camera reversal. */
const REVERSE_FAN = false

/** One contiguous [start, count] triangle-vertex range (three.js BufferGeometry group semantics:
 * start/count counted in VERTICES, matching a non-indexed geometry), tagged with the texture, mask
 * state, cull side (`twoSided`), `blend` mode, and whether it draws with the lightmap atlas.
 * `texIndex` -1 is untextured (flat grey base, still shaded/lit). Viewport3D maps each group to a
 * material. */
export interface GeometryGroup {
  texIndex: number
  masked: boolean
  twoSided: boolean
  blend: ScenePoly['blend']
  lit: boolean
  start: number
  count: number
}

export interface GeometryData {
  positions: Float32Array // flat [x,y,z, ...], one triangle's 3 verts at a time
  uvs: Float32Array // base-texture UV [u,v, ...], texture-space (1.0 = one tile), aligned with positions
  uv1: Float32Array // lightmap-atlas UV [u,v, ...] (normalized), (0,0) for unlit verts
  colors: Float32Array // per-vertex [r,g,b, ...]: flat KEY_LIGHT shade for unlit, white for lit
  groups: GeometryGroup[] // one per (texIndex, masked, twoSided, blend, lit) tuple, in first-seen order
  // One entry per TRIANGLE (not vertex), same order as `positions` -- `THREE.Raycaster`'s
  // `faceIndex` on a non-indexed geometry indexes this array directly, so a raycast hit resolves
  // to its owning actor without a second geometry pass (click-to-select, `selection.ts`).
  triangleOwners: (string | null)[]
  // Same per-triangle indexing as `triangleOwners`, but the SOURCE poly's index into the original
  // (unfiltered) `ScenePayload.polys` array -- not the local index into whatever subset `polys`
  // here happens to be (SceneResourcesContext builds this twice, for non-Mover and Mover polys
  // separately, so a local index would collide across the two). Callers that build from a subset
  // pass `sourceIndices` (below); a caller building from the full array can omit it. This is the
  // surface (single-polygon) click-to-select identity -- distinct from `triangleOwners`, which
  // resolves to the whole owning ACTOR (`selection.ts`'s `resolveHitSurface`).
  trianglePolyIndex: (number | null)[]
}

function dot(a: number[], b: number[]): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}

/** One poly's per-vertex base-texture UVs in the source texture's own coordinate space: the raw
 * texel coordinate divided by the texture's size, so a surface spanning N tiles yields UVs 0..N and
 * RepeatWrapping tiles the texture. Untextured (tex_index < 0 / no rect) -> (0,0). */
function polyUVs(poly: ScenePoly, atlas: AtlasPayload): [number, number][] {
  const rect = atlas.manifest[String(poly.tex_index)]
  if (poly.tex_index < 0 || !rect) {
    return poly.verts.length > 0 ? Array(poly.verts.length / 3).fill([0, 0]) : []
  }
  const out: [number, number][] = []
  for (let i = 0; i < poly.verts.length; i += 3) {
    const rel = [poly.verts[i] - poly.base[0], poly.verts[i + 1] - poly.base[1], poly.verts[i + 2] - poly.base[2]]
    out.push([(dot(rel, poly.tu) + poly.pan[0]) / rect.w, (dot(rel, poly.tv) + poly.pan[1]) / rect.h])
  }
  return out
}

/** One lit poly's per-vertex lightmap-atlas UVs (normalized), or `null` when the poly has no
 * lightmap or no packed rect. Per vertex the lumel coordinate is `lu = (pos-origin)·u_step /
 * (u_step·u_step)` (same for lv) -- render.rs's exact convention -- then mapped to the atlas texel
 * centre `(rect.x + lu + 0.5) / atlasW` so nearest-sampling picks lumel round(lu), matching
 * render.rs's `round().clamp()`; the 1-lumel gutter absorbs the clamp past an edge. */
function lightmapUVs(poly: ScenePoly, polyIndex: number, lm: LightmapPayload | null): [number, number][] | null {
  if (!poly.lightmap || !lm) return null
  const rect = lm.manifest[String(polyIndex)]
  if (!rect) return null
  const { origin, u_step, v_step } = poly.lightmap
  const uu = dot(u_step, u_step)
  const vv = dot(v_step, v_step)
  if (uu <= 1e-12 || vv <= 1e-12) return null // degenerate frame -> treat as unlit
  const out: [number, number][] = []
  for (let i = 0; i < poly.verts.length; i += 3) {
    const rel = [poly.verts[i] - origin[0], poly.verts[i + 1] - origin[1], poly.verts[i + 2] - origin[2]]
    const lu = dot(rel, u_step) / uu
    const lv = dot(rel, v_step) / vv
    out.push([(rect.x + lu + 0.5) / lm.width, (rect.y + lv + 0.5) / lm.height])
  }
  return out
}

/** Per-face flat brightness for an unlit poly, exactly render.rs's `0.55 + 0.45*|n·KEY_LIGHT|/|n|`
 * with `n` the Newell normal of the ring (degenerate ring -> 1.0, unshaded). */
function flatShade(poly: ScenePoly): number {
  let nx = 0
  let ny = 0
  let nz = 0
  const n = poly.verts.length / 3
  for (let i = 0; i < n; i++) {
    const a = i * 3
    const b = ((i + 1) % n) * 3
    const ax = poly.verts[a]
    const ay = poly.verts[a + 1]
    const az = poly.verts[a + 2]
    const bx = poly.verts[b]
    const by = poly.verts[b + 1]
    const bz = poly.verts[b + 2]
    nx += (ay - by) * (az + bz)
    ny += (az - bz) * (ax + bx)
    nz += (ax - bx) * (ay + by)
  }
  const len = Math.hypot(nx, ny, nz)
  if (len <= 1e-6) return 1.0
  return 0.55 + 0.45 * Math.abs(nx * KEY_LIGHT[0] + ny * KEY_LIGHT[1] + nz * KEY_LIGHT[2]) / len
}

/** Fan-triangulate a convex n-gon ring (BSP node polys are convex) into the flat output arrays. */
function appendTriangleFan(
  poly: ScenePoly,
  sourceIndex: number,
  uvs: [number, number][],
  lmUVs: [number, number][] | null,
  shade: number,
  out: Bucket,
): void {
  const n = poly.verts.length / 3
  for (let i = 1; i < n - 1; i++) {
    for (const idx of REVERSE_FAN ? [0, i + 1, i] : [0, i, i + 1]) {
      out.pos.push(poly.verts[idx * 3], poly.verts[idx * 3 + 1], poly.verts[idx * 3 + 2])
      out.uv.push(uvs[idx][0], uvs[idx][1])
      out.uv1.push(lmUVs ? lmUVs[idx][0] : 0, lmUVs ? lmUVs[idx][1] : 0)
      if (lmUVs) out.color.push(1, 1, 1) // lit: lightmap does the shading, vertex colour is a no-op
      else out.color.push(shade, shade, shade)
    }
    out.owner.push(poly.owner) // one entry per TRIANGLE, not per vertex
    out.polyIndex.push(sourceIndex)
  }
}

interface Bucket {
  texIndex: number
  masked: boolean
  twoSided: boolean
  blend: ScenePoly['blend']
  lit: boolean
  pos: number[]
  uv: number[]
  uv1: number[]
  color: number[]
  owner: (string | null)[]
  polyIndex: number[]
}

export function buildGeometryData(
  polys: ScenePoly[],
  atlas: AtlasPayload,
  lightmap: LightmapPayload | null = null,
  // Maps `polys`' own local index to its index in the original `ScenePayload.polys` array -- see
  // `GeometryData.trianglePolyIndex`'s doc comment. Defaults to the identity (`polys` IS the
  // canonical index space), matching every existing caller that doesn't pre-filter its input.
  sourceIndices?: number[],
): GeometryData {
  const buckets = new Map<string, Bucket>()
  const order: string[] = []

  polys.forEach((poly, polyIndex) => {
    if (poly.verts.length < 9) return // degenerate (<3 verts): nothing to draw
    const uvs = polyUVs(poly, atlas)
    const lmUVs = lightmapUVs(poly, polyIndex, lightmap)
    const lit = lmUVs !== null
    const key = `${poly.tex_index}:${poly.masked ? 1 : 0}:${poly.two_sided ? 1 : 0}:${poly.blend}:${lit ? 1 : 0}`
    let bucket = buckets.get(key)
    if (!bucket) {
      bucket = {
        texIndex: poly.tex_index, masked: poly.masked, twoSided: poly.two_sided, blend: poly.blend,
        lit, pos: [], uv: [], uv1: [], color: [], owner: [], polyIndex: [],
      }
      buckets.set(key, bucket)
      order.push(key)
    }
    const sourceIndex = sourceIndices ? sourceIndices[polyIndex] : polyIndex
    appendTriangleFan(poly, sourceIndex, uvs, lmUVs, lit ? 1 : flatShade(poly), bucket)
  })

  const positions: number[] = []
  const uvs: number[] = []
  const uv1: number[] = []
  const colors: number[] = []
  const groups: GeometryGroup[] = []
  const triangleOwners: (string | null)[] = []
  const trianglePolyIndex: (number | null)[] = []
  for (const key of order) {
    const bucket = buckets.get(key) as Bucket
    const start = positions.length / 3
    positions.push(...bucket.pos)
    uvs.push(...bucket.uv)
    uv1.push(...bucket.uv1)
    colors.push(...bucket.color)
    triangleOwners.push(...bucket.owner)
    trianglePolyIndex.push(...bucket.polyIndex)
    groups.push({
      texIndex: bucket.texIndex, masked: bucket.masked, twoSided: bucket.twoSided,
      blend: bucket.blend, lit: bucket.lit, start, count: bucket.pos.length / 3,
    })
  }

  return {
    positions: new Float32Array(positions),
    uvs: new Float32Array(uvs),
    uv1: new Float32Array(uv1),
    colors: new Float32Array(colors),
    groups,
    triangleOwners,
    trianglePolyIndex,
  }
}
