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
  // This poly's own index into `owner`'s AUTHORED `brush.polys` -- `BRUSH:IDX` addressing
  // (uedcli/surface.py), the same identity `brush poly find`/`--highlight` already use. Several
  // ScenePolys (several CSG-solved fragments) can share one i_brush_poly when a face gets split --
  // that's the surface-selection identity (selectionSet.ts's surfaceKey), NOT this poly's own array
  // position, so a click anywhere on the authored face selects/highlights every fragment of it.
  // null when `owner` has no single source poly (a mesh actor, no `.brush.polys` at all) or when
  // `owner` itself is null.
  i_brush_poly: number | null
}

/** A brush actor's own AUTHORED polygons (pre-CSG, local-space, transformed to world), for the
 * selection highlight -- NOT the CSG-solved `ScenePoly`s. `color` is the brush's CSG-classification
 * hue (uedcli/preview.py's `_CSG_PALETTE`), so a selected brush outlines in its own add/subtract/
 * semisolid/nonsolid/mover colour. `local_origin` is the world position of the brush's LOCAL
 * coordinate origin (`Location - R*PrePivot`) -- coincides with `SceneActor.location` (the true
 * pivot) only when PrePivot is zero. */
export interface BrushHighlight {
  csg_class: string
  color: [number, number, number]
  polys: number[][] // one entry per poly: flat world verts [x0,y0,z0, x1,y1,z1, ...]
  local_origin: [number, number, number]
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

/** Collision-cylinder / light-reach / sound-reach radii for one non-brush actor (uedcli/serve/
 * scene.py::ActorRadii) -- ported from `actor diagram --show collision`/`--show light-range`/
 * `--show sound-range`. `collision_height` is the HALF-height (the cylinder spans
 * `location.z +/- collision_height`). Resolved unconditionally server-side whenever the actor
 * clears the matching real-engine gate (`bCollideActors`; `LightType`+`LightBrightness`+
 * `LightRadius`; `AmbientSound` set) -- the client's own radii-overlay toggle decides what to draw. */
export interface ActorRadii {
  collision_radius: number | null
  collision_height: number | null
  light_radius: number | null // world units, already resolved server-side (preview.world_light_radius)
  sound_radius: number | null // world units, already resolved server-side (preview.world_sound_radius)
}

/** UED22's directional-facing arrow gizmo (`AActor.bDirectional`, `C_ActorArrow` -- own-binary RE,
 * `GUI-PARITY.md` "Directional arrow gizmo"). Present for ANY actor (brush included) whose
 * effective `bDirectional` resolves true server-side. `require_selection` is false only for an
 * `Engine.Camera`-descendant actor -- real UED22 shows a Camera's arrow unconditionally except
 * while that Camera is the viewport's own possessed actor, a case this GUI's free-fly viewports
 * never hit, so the client always shows a Camera's arrow unconditionally. */
export interface DirectionalArrow {
  require_selection: boolean
  // 5-segment dart, WORLD-space, flat (x,y,z) triples: 5 segments * 2 points * 3 floats = 30
  // numbers, consecutive pairs forming one line each (shaft, then 4 fins). Already resolved
  // server-side from the actor's own Location/Rotation (`rotation.actor_matrix`) -- the client
  // draws these verbatim, no rotation math of its own.
  lines: number[]
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
  csg_rank: number // 1-based position in level.order (CSG evaluation order); order_value's human-readable stand-in
  props: [string, string][] // the raw stored T3D property list, for the inspector's raw-props view
  categories: string[] // parallel to props: categories[i] is the UnrealEd category of props[i]
  brush: BrushHighlight | null // selection-highlight geometry; null for a non-brush actor
  sprite: ActorSprite | null // resolved DT_Sprite billboard; null -> client draws a generic marker
  radii: ActorRadii | null // collision/light radii; null for a brush actor or one that clears neither gate
  // The server's authoritative `movers.is_mover` answer (always false for a non-brush actor) --
  // always wireframe-only rendering by default, see GUI.md "Movers". Never re-derived from `cls`
  // client-side: the client has no class-schema access to walk the descends-from-Engine.Mover chain.
  is_mover: boolean
  // null when the actor's effective bDirectional is false. Resolved for EVERY actor server-side
  // (brush included -- DeusEx.DeusExMover sets bDirectional=True), unlike `radii`/`sprite`.
  directional_arrow: DirectionalArrow | null
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

/** `GET /api/levels` (quad-layout Part 7, Task 26): every level under the project's maps dir,
 * flagging which one this app currently serves -- mirrors `level list --json`'s `{name, active}`
 * shape (`uedcli/serve/levels.py`). */
export interface LevelsPayload {
  levels: { name: string; active: boolean }[]
  current: string
}

export function fetchLevels(): Promise<LevelsPayload> {
  return request<LevelsPayload>('/api/levels')
}

/** `PUT /api/level` (spec §6): switches which level this SAME running app serves, in-process --
 * no page reload. On success, the caller sets its own `level` state to the new name; the existing
 * `useEffect(..., [level])`s (scene/atlas/lightmap fetch, the changes-available WS subscription)
 * already unsubscribe-old/refetch-fresh on that state change (reload.ts needs no changes). */
export function switchLevel(name: string): Promise<{ level: string }> {
  return request('/api/level', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ level: name }),
  })
}

/** One `POST /save` (or `/load`) conflict entry: a staged actor move whose baseline trunk location
 * no longer matches the trunk's current on-disk location for that actor (uedcli/serve/app.py's
 * `_serialize_location` -- both locations are the raw `[x, y, z]` floats). */
export interface ConflictPayload {
  name: string
  staged_location: [number, number, number]
  trunk_location: [number, number, number]
}

/** `POST /api/level/{level}/save`'s result (uedcli/serve/app.py `save`): `applied` is the list of
 * actor names actually written to the trunk; `conflicts` is empty unless a staged move's baseline
 * disagreed with the trunk and no resolution for it was supplied. */
export interface SaveResult {
  applied: string[]
  conflicts: ConflictPayload[]
}

/** One entry of `GET /api/level/{level}/staged` (uedcli/serve/app.py `staged`). */
export interface StagedActorPayload {
  staged_location: [number, number, number]
  baseline_location: [number, number, number]
}

/** The explicit Load action (gui-explicit-rebuild spec §2): re-reads the trunk and clears the
 * server's `changes_available` flag. Does NOT solve geometry -- see `postRebuild`. `resolutions`
 * answers a load-conflict entry ("accept-load" is the only verdict this direction supports) --
 * default `{}` matches the backend's own default (uedcli/serve/app.py `load`). */
export function postLoad(
  level: string,
  resolutions: Record<string, 'accept-load'> = {},
): Promise<{ status: string; conflicts: ConflictPayload[] }> {
  return request(`/api/level/${encodeURIComponent(level)}/load`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resolutions }),
  })
}

/** The explicit Rebuild action (spec §3): the only thing that ever runs the ~24s CSG+lighting
 * solve. Resolves once the new geometry is pinned server-side. */
export function postRebuild(level: string): Promise<{ status: string; geom_hash: string | null; light_hash: string | null }> {
  return request(`/api/level/${encodeURIComponent(level)}/rebuild`, { method: 'POST' })
}

/** Stages a batch of actor moves (uedcli/serve/app.py `stage`) -- not written to the trunk until
 * `postSave`. `actors` maps actor name -> new `[x, y, z]` location. Returns the names actually
 * staged. */
export function postStage(level: string, actors: Record<string, [number, number, number]>): Promise<{ staged: string[] }> {
  return request(`/api/level/${encodeURIComponent(level)}/stage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actors }),
  })
}

/** Discards staged moves for this level (uedcli/serve/app.py `discard`) -- no trunk write. With no
 * `actors`, discards EVERY staged move for the level (the original whole-level behavior). With an
 * `actors` subset, discards only those actors' staged moves, leaving every other staged actor's
 * move in place -- lets the Save conflict-resolution UI drop one conflicting actor's stage without
 * losing unrelated staged work (Task 10's extension to Task 3's route). */
export function postDiscard(level: string, actors?: string[]): Promise<{ status: string }> {
  return request(`/api/level/${encodeURIComponent(level)}/discard`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(actors ? { actors } : {}),
  })
}

/** Writes staged moves to the trunk (uedcli/serve/app.py `save`). `resolutions` answers a
 * save-conflict entry (staged vs. trunk) by actor name; default `{}` matches the backend's own
 * default. */
export function postSave(level: string, resolutions: Record<string, 'staged' | 'trunk'> = {}): Promise<SaveResult> {
  return request(`/api/level/${encodeURIComponent(level)}/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resolutions }),
  })
}

/** The current staging state (uedcli/serve/app.py `staged`) -- maps actor name -> its staged and
 * pre-stage baseline locations. */
export function fetchStaged(level: string): Promise<Record<string, StagedActorPayload>> {
  return request(`/api/level/${encodeURIComponent(level)}/staged`)
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
