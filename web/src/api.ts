// Typed client for uedcli serve's backend (uedcli/serve/app.py). Mirrors the JSON shapes those
// routes return field-for-field — see uedcli/serve/scene.py (ScenePoly/SceneActor), textures.py
// (the atlas manifest), and app.py's /ws reload message.

export interface ScenePoly {
  verts: number[] // flat world-space [x,y,z, x,y,z, ...] ring
  base: number[] // [x,y,z] base-UV frame origin
  tu: number[] // [x,y,z] texture-U axis
  tv: number[] // [x,y,z] texture-V axis
  pan: number[] // [u,v] pan offset
  tex_index: number // index into the atlas manifest, or -1 (untextured -> flat grey)
  masked: boolean // alpha-test this poly against the atlas's mask channel
  flags: number // raw merged PolyFlags
  lightmap: unknown | null // baked lightmap patch; unused by Slice 1's unlit draw
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
