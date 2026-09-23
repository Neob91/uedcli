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

/** The other message `/ws` ever sends (Task 17, `uedcli/serve/app.py` `ws_endpoint`): this
 * connection's claim token no longer matches the session's current one -- another window took it
 * over, or the session was deleted. The socket closes right after sending it (code 4003 or 4004),
 * so a caller must treat this as the live signal, not the close event that follows it. */
export interface SupersededMessage {
  type: 'superseded'
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
    // `status` rides on the thrown Error rather than a dedicated error class, so every existing
    // `.rejects.toThrow(message)` assertion keeps working unchanged -- `isSupersededError` below is
    // the one place anything reads it.
    const err = new Error(`${url}: ${message}`) as Error & { status: number }
    err.status = res.status
    throw err
  }
  return (await res.json()) as T
}

/** True for a mutating call's 409 (persistent-GUI-editing-sessions plan, Task 17): this session's
 * claim was taken by another window, or the session was deleted. Every session-scoped mutating
 * route (`/load`, `/rebuild`, `/stage`, `/discard`, `/save`) 409s this way (uedcli/serve/app.py) --
 * the fallback path for the same takeover the `/ws` "superseded" push shows, for whenever that
 * push was lost or hasn't arrived yet. */
export function isSupersededError(e: unknown): boolean {
  return typeof e === 'object' && e !== null && (e as { status?: number }).status === 409
}

// The session's current claim token (Task 17) -- module-level, not threaded through every mutating
// call's own parameter list: `postStage` alone is called from both Viewport3D.tsx and
// OrthoViewport.tsx, several props deep under QuadLayout, and re-threading it down through all of
// that just to reach this one header would touch a pile of files with no other reason to change.
// App.tsx sets this once, in a `useEffect` keyed on `SessionContext`'s own `claimToken` -- the same
// "one source of truth pushed into a leaf module" shape `theme/useTheme.ts` and `layout/
// useSidebar.ts` already use for their own persisted state.
let currentClaimToken: string | null = null

export function setClaimToken(token: string | null): void {
  currentClaimToken = token
}

/** Merges the current claim token into `init`'s headers, leaving `init` untouched when there is no
 * token (so a caller with no session yet -- or a test that never calls `setClaimToken` -- gets the
 * exact same request it always did, no empty `headers: {}` for `toHaveBeenCalledWith` to trip on). */
function withClaimToken(init: RequestInit): RequestInit {
  if (!currentClaimToken) return init
  return { ...init, headers: { ...(init.headers as Record<string, string> | undefined), 'X-Claim-Token': currentClaimToken } }
}

export function fetchScene(sessionId: string): Promise<ScenePayload> {
  return request<ScenePayload>(`/api/session/${encodeURIComponent(sessionId)}/scene`)
}

export function fetchAtlas(sessionId: string): Promise<AtlasPayload> {
  return request<AtlasPayload>(`/api/session/${encodeURIComponent(sessionId)}/atlas`)
}

export function fetchLightmap(sessionId: string): Promise<LightmapPayload> {
  return request<LightmapPayload>(`/api/session/${encodeURIComponent(sessionId)}/lightmap`)
}

export function fetchStatus(sessionId: string): Promise<StatusPayload> {
  return request<StatusPayload>(`/api/session/${encodeURIComponent(sessionId)}/status`)
}

/** `GET /api/levels` (quad-layout Part 7, Task 26): every level under the project's maps dir --
 * mirrors `level list --json`'s `{name, active}` shape (`uedcli/serve/levels.py`). `current` is the
 * server's own startup/default level (`app.state.default_level`) -- SessionContext's own bootstrap
 * fallback for "which level does a brand-new session with no `?session=` in the URL start on"
 * (persistent-GUI-editing-sessions plan, Task 16). */
export interface LevelsPayload {
  levels: { name: string; active: boolean }[]
  current: string
}

export function fetchLevels(): Promise<LevelsPayload> {
  return request<LevelsPayload>('/api/levels')
}

/** `POST /api/level/{level}/sessions` (persistent-GUI-editing-sessions plan, Task 12): creates a
 * new session on `level` and mints its first claim token. Replaces the old in-process `PUT
 * /api/level` level switch entirely -- a session, not a level, is now the unit of navigation
 * (SessionContext.tsx). */
export interface SessionRecord {
  id: string
  level: string
  created_at: string
  claim_token: string
}

export function createSession(level: string): Promise<SessionRecord> {
  return request<SessionRecord>(`/api/level/${encodeURIComponent(level)}/sessions`, { method: 'POST' })
}

/** `GET /api/session/{id}` (Task 12): resolves a session id to its record, minting a FRESH claim
 * token every call -- this is the "reloading re-resolves the session, superseding whichever window
 * currently holds it" operation the spec describes, not an idempotent read. 404s (as a thrown
 * `Error`, via `request`'s own error handling) when the id is unknown or was closed. */
export interface SessionDetail {
  id: string
  level: string
  created_at: string
  last_active_at: string
  claim_token: string
}

export function fetchSession(sessionId: string): Promise<SessionDetail> {
  return request<SessionDetail>(`/api/session/${encodeURIComponent(sessionId)}`)
}

/** One entry of `GET /api/sessions` (Task 12) -- no claim token, since listing mints none. */
export interface SessionSummary {
  id: string
  level: string
  created_at: string
  last_active_at: string
}

export function fetchSessions(): Promise<{ sessions: SessionSummary[] }> {
  return request('/api/sessions')
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

/** One entry of `GET /api/session/{id}/staged` (uedcli/serve/app.py `session_staged`). */
export interface StagedActorPayload {
  staged_location: [number, number, number]
  baseline_location: [number, number, number]
}

/** The explicit Load action (gui-explicit-rebuild spec §2): re-reads the trunk and clears this
 * session's `changes_available` flag. Does NOT solve geometry -- see `postRebuild`. `resolutions`
 * answers a load-conflict entry ("accept-load" is the only verdict this direction supports) --
 * default `{}` matches the backend's own default (uedcli/serve/app.py `session_load`). Sends the
 * session's current `X-Claim-Token` (Task 17) -- required for the backend to actually write; a
 * stale/superseded token 409s "session superseded" (`isSupersededError`). */
export function postLoad(
  sessionId: string,
  resolutions: Record<string, 'accept-load'> = {},
): Promise<{ status: string; conflicts: ConflictPayload[] }> {
  return request(`/api/session/${encodeURIComponent(sessionId)}/load`, withClaimToken({
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resolutions }),
  }))
}

/** The explicit Rebuild action (spec §3): the only thing that ever runs the ~24s CSG+lighting
 * solve. Session-scoped (`uedcli/serve/app.py session_rebuild`), not the memoryless per-level
 * route -- only the session-scoped one pins the solved geometry `session_status`/`session_scene`
 * read back, via `build_pin`. Same claim-token requirement as `postLoad` above. */
export function postRebuild(sessionId: string): Promise<{ geom_hash: string | null; light_hash: string | null }> {
  return request(`/api/session/${encodeURIComponent(sessionId)}/rebuild`, withClaimToken({ method: 'POST' }))
}

/** Stages a batch of actor moves (uedcli/serve/app.py `session_stage`) -- not written to the trunk
 * until `postSave`. `actors` maps actor name -> new `[x, y, z]` location. Returns the names
 * actually staged. Same claim-token requirement as `postLoad` above. */
export function postStage(sessionId: string, actors: Record<string, [number, number, number]>): Promise<{ staged: string[] }> {
  return request(`/api/session/${encodeURIComponent(sessionId)}/stage`, withClaimToken({
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actors }),
  }))
}

/** Discards staged moves for this session (uedcli/serve/app.py `session_discard`) -- no trunk
 * write. With no `actors`, discards EVERY staged move for the session (the original whole-level
 * behavior, now per-session). With an `actors` subset, discards only those actors' staged moves,
 * leaving every other staged actor's move in place -- lets the Save conflict-resolution UI drop one
 * conflicting actor's stage without losing unrelated staged work (Task 10's extension to Task 3's
 * route). Same claim-token requirement as `postLoad` above. */
export function postDiscard(sessionId: string, actors?: string[]): Promise<{ status: string }> {
  return request(`/api/session/${encodeURIComponent(sessionId)}/discard`, withClaimToken({
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(actors ? { actors } : {}),
  }))
}

/** Writes staged moves to the trunk (uedcli/serve/app.py `session_save`). `resolutions` answers a
 * save-conflict entry (staged vs. trunk) by actor name; default `{}` matches the backend's own
 * default. Same claim-token requirement as `postLoad` above. */
export function postSave(sessionId: string, resolutions: Record<string, 'staged' | 'trunk'> = {}): Promise<SaveResult> {
  return request(`/api/session/${encodeURIComponent(sessionId)}/save`, withClaimToken({
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resolutions }),
  }))
}

/** The current staging state (uedcli/serve/app.py `session_staged`) -- maps actor name -> its
 * staged and pre-stage baseline locations. An ungated read, no claim token needed. */
export function fetchStaged(sessionId: string): Promise<Record<string, StagedActorPayload>> {
  return request(`/api/session/${encodeURIComponent(sessionId)}/staged`)
}

export interface LevelState {
  scene: ScenePayload
  atlas: AtlasPayload
  lightmap: LightmapPayload
}

/** Fetches scene+atlas+lightmap together -- the one shape every full-refresh call site (initial
 * open, post-Load, post-Rebuild) needs. */
export async function fetchLevelState(sessionId: string): Promise<LevelState> {
  const [scene, atlas, lightmap] = await Promise.all([fetchScene(sessionId), fetchAtlas(sessionId), fetchLightmap(sessionId)])
  return { scene, atlas, lightmap }
}

/** Opens the live "changes available" WebSocket for one session, presenting its current claim
 * token on the URL (Task 17 -- `uedcli/serve/app.py ws_endpoint` requires `?session=<id>&claim=
 * <token>`, no back-compat no-params mode). Calls `onChanged` for every settled trunk change push
 * (uedcli/serve/watch.py's debounced TrunkWatcher) -- a banner signal ONLY, the caller decides
 * what, if anything, to refetch (gui-explicit-rebuild spec §2: no silent auto-reload) -- and
 * `onSuperseded` for the one other message this socket ever sends. Returns the socket so the
 * caller (`reload.ts`) can close it on unmount, or notice an ordinary close and reconnect. */
export function openChangesAvailableSocket(
  sessionId: string,
  claimToken: string,
  onChanged: (msg: ChangesAvailableMessage) => void,
  onSuperseded: () => void,
): WebSocket {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${proto}://${window.location.host}/ws?session=${encodeURIComponent(sessionId)}&claim=${encodeURIComponent(claimToken)}`
  const ws = new WebSocket(url)
  ws.addEventListener('message', (event: MessageEvent<string>) => {
    const msg = JSON.parse(event.data) as ChangesAvailableMessage | SupersededMessage
    if (msg.type === 'changes_available') onChanged(msg)
    else if (msg.type === 'superseded') onSuperseded()
  })
  return ws
}
