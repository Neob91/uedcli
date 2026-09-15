// Typed client for uedcli serve's backend (uedcli/serve/app.py). Mirrors the JSON shapes those
// routes return field-for-field — see uedcli/serve/scene.py (ScenePoly/SceneActor), textures.py
// (the atlas manifest), and app.py's /ws "changes_available" message.

/** A lit surf's world-space lumel-sampling frame (uedcli/serve/scene.py::LightmapFrame). A lumel's
 * world position is `origin + u_step*u + v_step*v`; the client derives a per-vertex lumel UV from
 * it and samples the lightmap atlas. The baked lumel RGB is NOT here -- it's in the atlas. */
export interface LightmapFrame {
  origin: number[]
  u_step: number[]
  v_step: number[]
  u_size: number
  v_size: number
}

export interface ScenePoly {
  verts: number[] // flat world-space [x,y,z, x,y,z, ...] ring
  base: number[] // [x,y,z] base-UV frame origin
  tu: number[] // [x,y,z] texture-U axis
  tv: number[] // [x,y,z] texture-V axis
  pan: number[] // [u,v] pan offset
  tex_index: number // index into the atlas manifest, or -1 (untextured -> flat grey)
  masked: boolean // alpha-test this poly against the atlas's mask channel
  two_sided: boolean // draw both faces (PF_TwoSided|PF_Portal); else backface-culled (FrontSide)
  blend: 'opaque' | 'translucent' | 'modulated' // server-resolved compositing mode -> material state
  flags: number // raw merged PolyFlags (unused by the client; dropped in Phase 2)
  lightmap: LightmapFrame | null // lit-surf sampling frame; null = unlit (flat KEY_LIGHT shade)
  owner: string | null // owning actor's name (null: an out-of-range CSG join, no source actor)
}

/** A brush actor's own AUTHORED polygons (pre-CSG, local-space, transformed to world), for the
 * selection highlight -- NOT the CSG-solved `ScenePoly`s. `color` is the brush's CSG-classification
 * hue (uedcli/preview.py's `_CSG_PALETTE`), so a selected brush outlines in its own add/subtract/
 * semisolid/nonsolid/mover colour. */
export interface BrushHighlight {
  csg_class: string
  color: [number, number, number]
  polys: number[][] // one entry per poly: flat world verts [x0,y0,z0, x1,y1,z1, ...]
}

/** A point actor's resolved `DT_Sprite` billboard (uedcli/serve/scene.py::ActorSprite) -- the real
 * class-defined icon texture, at its natural size scaled by `DrawScale`. `tex_index` indexes the
 * SAME `/atlas` manifest every `ScenePoly.tex_index` does; `width`/`height` are the billboard's
 * world-space (UU) footprint. */
export interface ActorSprite {
  tex_index: number
  width: number
  height: number
}

export interface SceneActor {
  name: string
  cls: string
  bbox_lo: [number, number, number]
  bbox_hi: [number, number, number]
  location: [number, number, number]
  rotation: [number, number, number] // (pitch, yaw, roll) in Unreal rotation units
  folder: string | null
  labels: string[]
  order_value: string
  props: [string, string][] // the raw stored T3D property list, for the inspector's raw-props view
  categories: string[] // parallel to props: categories[i] is the UnrealEd category of props[i]
  brush: BrushHighlight | null // selection-highlight geometry; null for a non-brush actor
  sprite: ActorSprite | null // resolved DT_Sprite billboard; null -> client draws a generic marker
}

export interface ScenePayload {
  polys: ScenePoly[]
  actors: SceneActor[]
  // True once an explicit Rebuild has pinned solved geometry this session (else a cold-open/
  // no-Rebuild-yet response: `polys` is genuinely empty, not an error -- uedcli/serve/app.py's
  // `scene` route).
  geometry_pinned: boolean
}

export interface AtlasRect {
  x: number
  y: number
  w: number
  h: number
}

export interface AtlasPayload {
  width: number
  height: number
  manifest: Record<string, AtlasRect>
  png_base64: string
}

/** The lightmap atlas (uedcli/serve/lightmap.py): every lit poly's baked lumel grid packed into
 * one image, keyed by POLY INDEX (not texture index). `intensity` is the global multiplier scale
 * -- the client's `lightMapIntensity`, so `sampledTexel * intensity` recovers the baked value. */
export interface LightmapPayload {
  width: number
  height: number
  intensity: number
  manifest: Record<string, AtlasRect> // poly index -> interior lumel rect
  png_base64: string
}

// gui-explicit-rebuild spec §2: the ONLY push this socket ever sends -- a banner/badge signal for
// an explicit Load, never an instruction to auto-refetch (see reload.ts). Supersedes the old
// `"reload"` message type this client used to auto-refetch on.
export interface ChangesAvailableMessage {
  type: 'changes_available'
  level: string
}

/** `GET /api/level/{level}/status` (uedcli/serve/app.py `status`): whether a settled trunk change
 * is waiting on an explicit Load, and whether solved geometry is currently pinned (and if not,
 * why). `build_status` is `'built'` whenever `geometry_pinned`; `'no_build'` if geometry was never
 * populated (fresh open, no on-disk pointer either); `'evicted'` if an on-disk pointer exists but
 * the cache entry it names is gone. */
export interface StatusPayload {
  changes_available: boolean
  geometry_pinned: boolean
  build_status: 'no_build' | 'evicted' | 'built'
}

/** The backend's structured error body: `{"error": "<offending-value message>"}` (never a bare
 * traceback -- uedcli/serve/errors.py::error_to_status). */
interface ErrorBody {
  error?: string
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await (init ? fetch(url, init) : fetch(url))
  if (!res.ok) {
    let message = res.statusText
    try {
      const body = (await res.json()) as ErrorBody
      if (body.error) message = body.error
    } catch {
      // The error body wasn't JSON -- fall back to the HTTP status text.
    }
    throw new Error(`${url}: ${message}`)
  }
  return (await res.json()) as T
}

export function fetchScene(level: string): Promise<ScenePayload> {
  return request<ScenePayload>(`/api/level/${encodeURIComponent(level)}/scene`)
}

export function fetchAtlas(level: string): Promise<AtlasPayload> {
  return request<AtlasPayload>(`/api/level/${encodeURIComponent(level)}/atlas`)
}

export function fetchLightmap(level: string): Promise<LightmapPayload> {
  return request<LightmapPayload>(`/api/level/${encodeURIComponent(level)}/lightmap`)
}

export function fetchStatus(level: string): Promise<StatusPayload> {
  return request<StatusPayload>(`/api/level/${encodeURIComponent(level)}/status`)
}

/** The explicit Load action (gui-explicit-rebuild spec §2): re-reads the trunk and clears the
 * server's `changes_available` flag. Does NOT solve geometry -- see `postRebuild`. */
export function postLoad(level: string): Promise<{ status: string }> {
  return request(`/api/level/${encodeURIComponent(level)}/load`, { method: 'POST' })
}

/** The explicit Rebuild action (spec §3): the only thing that ever runs the ~24s CSG+lighting
 * solve. Resolves once the new geometry is pinned server-side. */
export function postRebuild(level: string): Promise<{ status: string; geom_hash: string | null; light_hash: string | null }> {
  return request(`/api/level/${encodeURIComponent(level)}/rebuild`, { method: 'POST' })
}

export interface LevelState {
  scene: ScenePayload
  atlas: AtlasPayload
  lightmap: LightmapPayload
}

/** Fetches scene+atlas+lightmap together -- the one shape every full-refresh call site (initial
 * open, post-Load, post-Rebuild) needs. */
export async function fetchLevelState(level: string): Promise<LevelState> {
  const [scene, atlas, lightmap] = await Promise.all([fetchScene(level), fetchAtlas(level), fetchLightmap(level)])
  return { scene, atlas, lightmap }
}

/** Opens the live "changes available" WebSocket and calls `onChanged` for every settled trunk
 * change push (uedcli/serve/watch.py's debounced TrunkWatcher). Returns the socket so the caller
 * can close it on unmount. This is a banner signal ONLY -- the caller decides what, if anything,
 * to refetch (gui-explicit-rebuild spec §2: no silent auto-reload). */
export function openChangesAvailableSocket(onChanged: (msg: ChangesAvailableMessage) => void): WebSocket {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${proto}://${window.location.host}/ws`)
  ws.addEventListener('message', (event: MessageEvent<string>) => {
    const msg = JSON.parse(event.data) as ChangesAvailableMessage
    if (msg.type === 'changes_available') onChanged(msg)
  })
  return ws
}
