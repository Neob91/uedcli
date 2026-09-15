// Typed client for uedcli serve's backend (uedcli/serve/app.py). Mirrors the JSON shapes those
// routes return field-for-field — see uedcli/serve/scene.py (ScenePoly/SceneActor), textures.py
// (the atlas manifest), and app.py's /ws reload message.

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

export interface ReloadMessage {
  type: 'reload'
  level: string
}

/** The backend's structured error body: `{"error": "<offending-value message>"}` (never a bare
 * traceback -- uedcli/serve/errors.py::error_to_status). */
interface ErrorBody {
  error?: string
}

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
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
  return fetchJson<ScenePayload>(`/api/level/${encodeURIComponent(level)}/scene`)
}

export function fetchAtlas(level: string): Promise<AtlasPayload> {
  return fetchJson<AtlasPayload>(`/api/level/${encodeURIComponent(level)}/atlas`)
}

export function fetchLightmap(level: string): Promise<LightmapPayload> {
  return fetchJson<LightmapPayload>(`/api/level/${encodeURIComponent(level)}/lightmap`)
}

/** Open the live-reload WebSocket and call `onReload` for every settled trunk-change push
 * (uedcli/serve/watch.py's debounced TrunkWatcher). Returns the socket so the caller can close it
 * on unmount. */
export function openReloadSocket(onReload: (msg: ReloadMessage) => void): WebSocket {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${proto}://${window.location.host}/ws`)
  ws.addEventListener('message', (event: MessageEvent<string>) => {
    const msg = JSON.parse(event.data) as ReloadMessage
    if (msg.type === 'reload') onReload(msg)
  })
  return ws
}
