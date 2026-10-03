# The GUI's HTTP backend in Rust

**Date:** 2026-10-03 · **Status:** research only — no decisions taken, nothing implemented.
**Question:** What does `old/uedcli/serve/` expose and touch, what Rust framework and proxy
technique could carry it, and where is the strangler risky? Server-side companion to the frontend
note, whose findings are taken as given and corrected only where the server disagrees.

## Summary

- `old/uedcli/serve/` is **16 modules, 3,250 LOC** product plus **5,415 LOC** of tests, and
  `app.py` carries **23 route decorators**: 19 `/api/*`, 1 test-gated `/api/_boom`, 2 SPA HTML
  routes, 1 `@app.websocket`, plus a `StaticFiles` mount.
- **The GUI does write the trunk** — `POST /api/session/{id}/save` → `edits.save_staged` →
  `cli.level_sources.TrunkLevelSource.save`. "Never writes the trunk" was a **P1-era** claim P2
  superseded; `old/dev/docs/GUI.md:205` still asserts it. 1 of 19 routes is dangerous.
- **Nothing streams; nothing invokes the editor or Docker.** Atlases ship as base64 PNG in JSON, and
  **every real route is a sync `def`** already in Starlette's threadpool — a clean `spawn_blocking`
  mapping. **`cli`↔`serve` is circular** (6 imports one way, 2 back; classifier on the GUI side).
- **CSG is not the dominant cost.** Reload ~4.7s at 487 actors, ~14.4s at 2,288, identical on a
  no-op repeat; Rebuild ~24s; class-schema re-derive was ~3s/request before `593a2fe4`.
- **The WebSocket is strictly server→client** — the client never sends a frame. Three messages,
  three close codes. That makes WS upgrade proxying, the hard part of the strangler, **avoidable**.
  Supersession is polled at 100 ms; the code blames sync routes in a worker thread, true as a
  mechanism but `loop.call_soon_threadsafe` exists — a design choice, not a platform limit.
- `watchfiles` is **confirmed** Rust/`notify`-backed; Reload/Rebuild perf is the one `mvp.md` entry.

## What we have today

| module | LOC | purpose |
|---|---|---|
| `app.py` | 1,306 | FastAPI factory, 23 routes, `LevelContext`, claim gating, caches |
| `scene.py` | 839 | `ScenePayload` assembly: polys, actors, sprites, radii, arrows, hidden-ed filter |
| `edits.py` | 250 | stage/discard/save logic; the only trunk writer |
| `sessions.py` | 150 | `sessions/<sid>/index.json` lifecycle |
| `snapshots.py` | 137 | `StagingStore`: content-addressed blobs + per-session `staged.json` |
| `lightmap.py` | 96 | lightmap atlas pack + PNG encode (Pillow) |
| `errors.py` | 78 | `error_to_status` — shared with `cli/dispatch.py` |
| `build_pin.py` | 77 | two pins: per-session `build.json`, per-level `current.json` |
| `watch.py` | 75 | `TrunkWatcher`: `watchfiles.awatch` + 0.4s debounce |
| `package_raw.py` | 63 | package name → `.u` path; ETag/mtime byte memo |
| `textures.py` | 58 | base-texture atlas pack + PNG encode (Pillow) |
| `claims.py` 42, `atlas_pack.py` 32, `atomic_io.py` 27, `levels.py` 18 | 119 | in-memory `ClaimRegistry`; shelf rect-packer shared by both atlas builders; temp + `os.replace` writes; `GET /api/levels` payload |

`serve/` imports **22 distinct core `uedcli/` modules** — a thin shell over the model core, so most
of the port is not here. Deps: `fastapi>=0.115`, `uvicorn>=0.32`, `watchfiles>=0.24`, `httpx>=0.27`,
`websockets>=13`, `Pillow>=11`. `cli/commands/serve.py` is 25 LOC: validate level, `create_app`,
`uvicorn.run` on localhost, no auth.

## Findings

### Route inventory

**W** = writes (`t` trunk, `s` session/state dir, `m` in-memory); **Port** = proposed wave.

| Method · path | touches | W | claim | cost | Port |
|---|---|---|---|---|---|
| `GET /api/health`, `GET /api/levels` | nothing; maps dir listing | — | no | trivial | 1 |
| `GET /session/{id}` (+ `…/`), mount `/` `StaticFiles(html=True)` | `web/dist`, `index.html` | — | no | trivial | 1 |
| `GET /api/package/{name}/raw` | search path, `.u` bytes, ETag memo | — | no | 1-2 MB body | 2 |
| `GET /api/sessions`; `POST /api/level/{lvl}/sessions` | list `sessions/*/index.json`; new session dir + mint claim + inherit level pin | s,m | mints | small | 3 |
| `GET /api/session/{id}` | **mints a fresh claim**, superseding the old | m | mints | small | 3 |
| `POST /api/session/{id}/rename` | `index.json` | s | yes | small | 3 |
| `DELETE /api/session/{id}` | `rmtree sessions/<sid>/`, `claims.forget` | s,m | yes | small | 3 |
| `GET /api/session/{id}/status` | `build.json`, generation; `touch_session` (30s-throttled) | s | no | **polled 3s/tab** | 3 |
| `GET /api/session/{id}/staged` | `staged.json` | — | no | small | 4 |
| `POST /api/session/{id}/stage` | trunk read; `staged.json` + blob write + eviction | s | yes | trunk read | 4 |
| `POST /api/session/{id}/discard` | `staged.json` write/remove + eviction | s | yes | small | 4 |
| `POST /api/session/{id}/t3d` | trunk read, staged overlay, `emit_map_with_carriers` | — | no | trunk read | 4 |
| `GET /api/session/{id}/scene` | trunk read + scene/wireframe payload | — | no | large JSON | 5 |
| `POST /api/session/{id}/load` | full trunk re-read + sprite/mesh/mover resolve | s,m | yes | **~4.7s / ~14.4s** | 5 |
| `GET /api/session/{id}/atlas` | texture table → shelf pack → PNG → base64 | — | no | CPU + big body | 6 |
| `GET /api/session/{id}/lightmap` | lumel grids → pack → PNG → base64 | — | no | CPU + big body | 6 |
| `POST /api/session/{id}/save` | **writes the trunk**; promotes level pin | **t**,s | yes | trunk write | 7 |
| `POST /api/session/{id}/rebuild` | `build_scene` CSG+lighting, `build_cache`, pin, eviction | s,m | after solve | **~24s** | 8 |
| `WS /ws?session=&claim=` | per-level connection set; 100 ms claim/existence poll | m | query param | long-lived | 8 |

Of the mutating routes only `/save` touches the trunk; the rest write `.uedcli/sessions/…` or
in-memory claims. `GZipMiddleware(minimum_size=500)` covers every response (recorded on `/raw`:
DeusEx.u 1.92 MB → 0.38 MB, Engine.u 1.24 MB → 0.40 MB); the test-only `GET /api/_boom`
(`fault_route=True`) is never ported. Wave reasoning: 1-2 is the walking skeleton; 3 is session CRUD
plus the claim registry — the whole concurrency model, in-memory and cheap to differential-test; 4
is staging and the `Decimal` boundary, no trunk write; 5-6 the heavy read payloads needing the Rust
renderer; 7 the single trunk writer; 8 the CSG solve and the push channel. Unported routes proxy.

**`error_to_status` is type dispatch, not a message-prefix map** — a sibling note has it backwards.
It is a 13-arm `isinstance` chain on **exception type** which *produces* the prefixes
(`"invalid coordinate: …"`, `"editor error: …"`); arm order is load-bearing where subclassing exists
(`TimeoutError` before the `OSError` backstop); outside the closed set it raises `TypeError`, which
`app.py`'s handler renders as a logged 500 + `"internal error"` — the only place an unclassified
exception is traced. Statuses 404/422/500/502 come from the classifier; routes hand-return 409, 304
(`/raw` ETag), 204, and a bare 404 for an unknown session on GET/DELETE only — inconsistent with the
422 the same condition gives elsewhere, flagged in the code. In Rust: one `enum` + `IntoResponse`.

### Scene-resolution pipeline and its memo

`/load` and `_get_trunk` both do `trunk.read_level_with_bodies` → `resolve_actor_sprites` →
`resolve_mesh_scene_polys` → `resolve_mover_scene_polys` → a `_LoadedTrunk` snapshot. `/rebuild`
adds `edits.apply_staged_overlay` on a *copy* of the level, then `build_scene(..., include_meshes=
False, include_movers=False)`, which self-stores into `build_cache`. `/scene` calls
`build_scene_payload` (pin resolved) or `build_wireframe_payload`.

Six caches sit under that. Process-wide: `_scene_inputs_cache`, keyed by `project.root` and
**never** invalidated (owner ruling 2026-09-28), and `_BuildResultCache`, an 8-entry LRU keyed by
`(level, geom_hash, light_hash)`. Per level inside `LevelContext`: `scene_inputs_ref`,
`resolve_ctx_ref` and `class_cache_ref` (the latter two memoized per FQCN), all replaced alongside
`trunk_ref`, which is itself generation-guarded and refreshed by `/load` or discarded on a
generation bump mid-build. On disk: the project `build_cache`, pruned by `evict_unreferenced`.
`593a2fe4` added the first of those. Before it, `index`/`defaults` were re-derived per `/load` and
`/rebuild` — **~3s of class-schema re-parsing, the dominant cost of both, not the CSG solve**. The
trade: already-loaded packages are never invalidated during a `serve` run, so a package edited on
disk needs a restart. `4114bf6e` re-keyed it from `id(project)` (GC address-reuse hazard) to
`project.root`. Write ordering is load-bearing for lock-free readers (`scene_inputs_ref` and
`class_cache_ref` before `resolve_ctx_ref` before `trunk_ref`); in Rust one
`RwLock<Arc<LoadedTrunk>>` holding all five removes that hazard by construction.

### Performance picture

`old/dev/docs/epics/mvp.md` has exactly **one** entry, and it is this topic —
`incremental-gui-reload-only-re-resolve-actors`: Reload should diff against the session's last-loaded
snapshot and cost hundreds of ms instead of scaling with the level.

| measurement | value | source |
|---|---|---|
| Reload, 487 actors | ~4.7s | `inbox/incremental-gui-reload-only-re-resolve-actors` |
| Reload, 2,288 actors | ~14.4s | same — **identical on a no-op repeat** |
| Rebuild (CSG + lighting) | ~24s | `old/web/src/api.ts` `postRebuild` doc |
| class-schema re-derive, per request | ~3s | `593a2fe4` |

`c288842b` rescued two ideas from an abandoned worktree:
`incremental-csg-checkpointing-for-gui-rebuild` (checkpoint the native CSG world-model per
brush-order position so an edit replays only forward from the change — today any brush change
re-solves the whole level, the algorithm being order-dependent) and `gui-unlit-fast-rebuild-button`
(a fast unlit preview decoupling lighting from CSG; survives as one sentence).
`rebuild-should-run-in-background-on-a-trunk-snapshot` wants `/rebuild` to return immediately, and
records **no progress callback at all** in `build_scene` or the native solve. Two blockers named for
incremental Reload shape the Rust types: `_LoadedTrunk`'s flat per-pass tables need keying by actor
name, and position-deduped texture indices need a content-keyed registry.

### Live reload, server-side
`TrunkWatcher` watches **one level's trunk directory** with `watchfiles.awatch`, recursive, feeding
every raw batch into `notify()` — a 0.4s restartable timer collapsing a burst into one `on_change`.
The timer task holds only the sleep phase, so a `notify()` arriving mid-broadcast cancels a pending
timer, never the broadcast (a prior review finding). `on_change` is `_on_trunk_settled`:
`generation += 1`, `changes_available = True`, `_broadcast_changes_available` — which iterates a
**snapshot** of `ctx.connections` (a concurrent connect/disconnect would otherwise drop the whole
broadcast) and never takes `trunk_lock`. One watcher per `LevelContext`: the startup level's is
started by `_lifespan`, a lazily created level's by `ws_endpoint` on first connect (`start()` is not
idempotent, so calling it twice leaks `_watch_task`).
Messages: `{"type":"changes_available","level":"<name>"}` on a debounced trunk change;
`{"type":"superseded"}` from the connect check or the 100 ms poll when a newer claim is minted;
`{"type":"closed"}` from the poll when the session directory is gone. Close codes **4001** (unknown
session / missing claim — closed without `accept()`), **4003** (claimed elsewhere, after an
`accept()` so the client can learn it), **4004** (session deleted).
**Poll-vs-push, verified:** `changes_available` *is* pushed — its trigger is on the event loop. Only
supersession and deletion are polled, because they originate in
`claims.mint`/`sessions.delete_session`, called from sync `def` routes Starlette runs in the anyio
threadpool. The code says there is "no cheap direct way for that thread to push into an already-open
WS living on a different thread's loop without a real cross-thread-to-loop bridge, which doesn't
exist anywhere in this codebase today" — accurate about the codebase, but not a Starlette limitation,
since `asyncio.run_coroutine_threadsafe` is the standard bridge. In Rust a `tokio::sync::broadcast`
is callable from any thread, so the 100 ms tick disappears.
**Known wart, already filed** (`inbox/gui-save-doesn-t-suppress-its-own-trunk-watcher`): the
post-Save `/load` usually completes inside the 0.4s debounce, so the watcher re-sets the flag
afterwards and the user sees "changes available" for their own save — "the default case, not a rare
race." Still true (`/load` calls `set_last_seen_generation`, `/save` does not): a `TODO` for the new
code, not a fix in `old/`.

### Sessions: two different things, one word
- **The deleted level session store.** The pre-2026-07 editor-centric model held the authoritative
  level in a live UnrealEd, every read a `MAP EXPORT`, with an interim on-disk session store, since
  deleted outright (`architecture.md`). `direction/trunk-and-editor.md`: "There is no session and no
  session store — git is the history and merge engine," explicitly rejecting "a bespoke
  event-sourced session store." That was about *level authority and history*.
- **GUI editing sessions** (`board/to-spec/persistent-gui-editing-sessions/`) — a durable,
  per-browser-tab unit of *GUI navigation and unsaved work*: own uuid7 id, `staged.json`,
  independently-solved build pin (deduped against a shared content-hash cache),
  `last_seen_generation`; survives refresh and restart; no auto-expiry. **No history, no merge
  authority**; a save funnels into the one model-side trunk write path.

A session is created only by a page load (`POST /api/level/{lvl}/sessions`) —
`create_app(project, level=None)` starts with **zero** `LevelContext`s. Ownership is a `claim_token`;
`GET /api/session/{id}` mints a fresh one every call, deliberately non-idempotent, so "whichever
window last loaded always wins" (the sibling is right that this GET mutates, load-bearingly).
`ClaimRegistry` is in-memory only and `check` treats an *unrecorded* id as a legitimate first claim
(restart safety) — so every gated route also re-checks `sessions.get_session(...)` under the same
per-session lock, or a DELETE racing a request resurrects the directory via `atomic_write_json`'s
unconditional `mkdir`. That interleaving is the subtlest thing here and the likeliest for a port to
break. Storage: `.uedcli/sessions/<sid>/{index,staged,build}.json` plus shared
`.uedcli/staging/blobs/`, via `atomic_io`. **Board-stage drift:** the item sits in `to-spec` with no
`plan.md`, yet the code cites "plan Task 9/11/…/15" and has shipped.

### Doc drift the server confirms
`PUT /api/level`, `GET /api/level/{level}/status` and `POST /api/level/{level}/save` **do not
exist**: `GUI.md` still documents the level-switch flow around the first, `errors.py`'s
`JSONDecodeError` arm comments on "`PUT /api/level`'s `await request.json()`", and `api.ts` cites
the other two. `GUI.md:3` calls the API "read-mostly" and `GUI.md:205` "P1, read-only, no write
path", but P2 shipped a trunk writer; `scene.py`'s `build_scene_payload` docstring credits the perf
fix to `_payload_ref`/`_get_payload`, neither of which exists any more. The sessions spec says
`GET /api/levels` "has no place in the new API surface", yet it is mounted and called, while
`GET /api/health` is called from nowhere and `/api/package/{name}/raw` is fetched from
`scene/classResolver.ts:57`, **not** `api.ts`. Two board items in the brief are not GUI-backend
concerns at all: `level-preview-multi-preview-port-url-surfacing` (noVNC for `level photo`'s Docker
editor) and `boot-time-floating-windows` (a `uned/` ini chore).

### Reuse vs duplication, and crate layering

`serve/` → `cli/` is 6 imports across 4 files (`cli.errors` ×3, `cli.level_sources` ×2,
`cli.resources` ×1); `cli/` → `serve/` is 2 (`cli/dispatch.py` → `serve.errors`, 10 call sites;
`cli/commands/serve.py` → `serve.app`, deferred). The sibling's "8 edges (`cli.errors`,
`cli.resources`)" matches that total only if both directions are counted, and misses
`cli.level_sources` — the important one, since `TrunkLevelSource` is *the* trunk write path. So
`serve/` genuinely reuses: no second write mechanism and no second error classifier.
But the direction is wrong for a clean crate split. Three things are really **shared core**:
`error_to_status` (in `serve/`, imported by the CLI dispatcher → the error crate);
`level_sources`/`TrunkLevelSource` (in `cli/`, the model-side write path → the trunk crate);
`resources.resolve_project`/`mover_index` (in `cli/`, used by both → a project/config crate).
Moving those down a layer is exactly the spec's "plain code reuse", and nothing here argues against
its rejection of a generic CLI/GUI registry — the duplication that targeted (brush-builder
definitions) does not exist in `serve/` yet. Watch `rationale/gui-editing.md`'s ruling: one generic
property path mirroring `propedit`'s plan/apply, never per-field endpoints.

### Does the GUI write the trunk?
**Yes, through exactly one route.** `POST /api/session/{id}/save` → `edits.save_staged` →
`TrunkLevelSource.save(verb="move", …)`, defended in depth: claim check plus session-existence
re-check under `claims.lock_for(session_id)`; per-actor conflict detection against the stage-time
baseline; an immediate pre-write re-read of every touched actor's trunk `Location` that reverts and
re-flags anything that moved in the gap (narrowing, not closing, the TOCTOU window); then one load +
one save for the batch through the same delete-then-readd-with-rollback path every CLI verb uses.
Pin promotion is sequenced strictly after the write, under `trunk_lock`. The danger is
concentrated: 18 of 19 routes can at worst produce a wrong picture or a stale cache,
differential-tested as "same JSON for the same trunk." `/save` can corrupt a level and needs the
conflict/TOCTOU semantics ported exactly, with `direction/safety.md`'s flock +
refuse-same-actor rule intact — its own PR.

### Rust HTTP frameworks (crates.io API, 2026-10-03)

| | version | last release | 90d dl | WebSocket | static/SPA | streaming | middleware | OpenAPI |
|---|---|---|---|---|---|---|---|---|
| `axum` | 0.8.9 | 2026-04-14 | 127.0M | built-in (`ws`) | `tower-http` `ServeDir` + `not_found_service` | `Body::from_stream` | tower | `utoipa-axum`, `aide` |
| `actix-web` | 4.15.0 | 2026-08-21 | 11.4M | `actix-ws` 0.4.0 | own `Files` | yes | bespoke, **not tower** | `utoipa` |
| `salvo` | 1.0.0 | 2026-09-24 | ~0.3M | built-in | built-in | yes | own + `tower-compat` | `salvo-oapi` |
| `poem` | 3.1.12 | **2025-07-28** | 0.41M | built-in | built-in | yes | own + `tower-compat` | `poem-openapi` |
| `rocket` | 0.5.1 | **2024-05-23** | 2.16M | `rocket_ws` | built-in | yes | fairings | third-party |

`axum` is ~11× `actix-web` by downloads and the only one with a dominant middleware ecosystem, so
everything this backend needs (compression to replace `GZipMiddleware`, `ServeDir`, tracing,
timeouts, a reverse proxy) is one tower layer. `rocket` is dormant (2.3 years since a release, last
commit 2025-12-28); `poem`'s repo is busy under a new maintainer but has had **no crates.io release
in 14 months**; `salvo` 1.0.0 is three weeks old with a thin ecosystem; `actix-web` is healthy and
fast but tower-incompatible, so you re-implement what `tower-http` gives free. Direct
normal-dependency counts (a weight proxy only — **no compile times measured**): `salvo` 17, `axum`
33, `rocket` 31, `actix-web` 36.

### The WebSocket-proxy risk — and why it is avoidable here

**Why it is hard.** You intercept the `101 Switching Protocols` handshake, forward
`Sec-WebSocket-Key`/`-Version`/`-Protocol`/`-Extensions`, relay the upstream's
`Sec-WebSocket-Accept` **verbatim** (recomputing it is the classic silent handshake failure), call
`hyper::upgrade::on` on both the client request and the upstream response, then byte-copy with
`tokio::io::copy_bidirectional`. Pitfalls: `Upgraded`'s `Parts::read_buf` holds bytes already read
during the handshake, so destructuring it rather than using it as an `AsyncRead` silently eats the
first frame; `copy_bidirectional` returns only when both directions finish, leaking the task on a
half-close; a frame-decoding proxy cannot relay `permessage-deflate` and must re-mask client→server
frames; a naive bridge collapses every disconnect into 1006, destroying the close-code contract. The
off-the-shelf options:

| crate | version | last release | WS upgrade | status |
|---|---|---|---|---|
| `axum-reverse-proxy` | 2.2.0 | 2026-08-29 | yes, frame-level | active; `axum ^0.8`, `hyper ^1`, `tokio-tungstenite ^0.28` |
| `tower-proxy` | 0.10.1 | 2026-09-22 | **unverified** | active fork of the deprecated `axum-proxy` |
| `pingora` | 0.9.0 | 2026-09-09 | yes (h1 passthrough, undocumented) | Cloudflare; a whole server, not an axum layer |
| `hyper-reverse-proxy` | 0.5.1 | **2022-03-12** | no | dead, predates hyper 1.0 |
| `reverse-proxy-service` | 0.2.1 | 2023-09-11 | not documented | superseded |

`axum-reverse-proxy` 2.2.0 is a one-line mount (`ReverseProxy::new("/api", "http://127.0.0.1:8000")`
→ `Router`) claiming RFC 9110 §7.6.1 hop-by-hop stripping, `X-Forwarded-*`, and verbatim close-frame
forwarding. It **strips `Sec-WebSocket-Extensions`** because it forwards frames, not bytes —
harmless here, since three tiny JSON messages gain nothing from compression. `tower-http` has no
forwarding layer; `pingora` is the wrong shape (a server framework, not an `axum` layer).
**Why it is avoidable.** The contract is three server→client JSON messages and three close codes,
and the client **never sends a frame** (`api.ts`'s `openChangesAvailableSocket` only adds a
`message` listener; `ws_endpoint` reads client text solely as a poll timer and discards it). So:

1. **Port `/ws` first, before any `/api` route.** It depends on almost nothing — the watcher, the
   per-level connection set, the claim registry. Owning it in Rust from day one means the proxy only
   ever forwards plain HTTP, the easy case. This inverts the instinct to port push last.
2. **If `/ws` must be proxied anyway**, point the browser's socket straight at the old backend's
   port. No proxy code; the cost is breaking the one-origin assumption (separate host/port plumbing,
   uvicorn's `Origin` check must accept it — WebSockets are not CORS-governed, so CORS is a
   non-issue). Fine for a local no-auth dev channel. *(Reasoned, not sourced.)*
3. **A rewrite to SSE is on the table** precisely because the channel is one-directional.
   `axum::response::sse` with `KeepAlive` needs no upgrade handling and proxies as ordinary HTTP.
   Costs: close codes become in-band, and SSE counts against the HTTP/1.1 6-per-origin limit. A
   contract change, so the owner's call.
**Plain-HTTP proxy gotchas** (unavoidable). The canonical reference is axum's own
`examples/reverse-proxy`, using `hyper_util::client::legacy::Client<_, axum::body::Body>` — **not
`reqwest`**, which forces `Bytes`/`Stream` adapters and loses trailers where axum's `Body` passes
through unbuffered. That example strips no hop-by-hop headers, sets no `X-Forwarded-*`, and maps
every error to 400. Add yourself: strip `Connection` (and every header it names),
`Transfer-Encoding`, `Upgrade`, `Keep-Alive`, `TE`, `Trailer`, `Proxy-*` on both legs (forwarding
`chunked` into hyper 1.x double-encodes); decide `Host` rewrite-vs-preserve; map connect errors to
502 and your own `tokio::time::timeout` to 504 (**hyper has no default timeout**); hold **one**
pooled `Client` with `pool_idle_timeout` below uvicorn's 5s keep-alive. Client leg stays HTTP/1.1.

### File watching in Rust

`notify` is stable at **8.2.0** (2025-08-03), with an unshipped 9.0.0-rc line (rc.5, 2026-08-30);
backends are inotify, FSEvents, `ReadDirectoryChangesW`, with a `PollWatcher` fallback.
`notify-debouncer-full` 0.7.0 adds per-path coalescing **plus rename stitching** (pairing
`RenameMode::From`/`To`); `notify-debouncer-mini` 0.7.0 only time-dedups.
**The `watchfiles` claim is confirmed:** `watchfiles` 1.3.0's `Cargo.toml` depends directly on
`notify = "8.2.0"` with `pyo3 = "0.29.2"`, and uses **neither** debouncer crate — its own loop in
`src/lib.rs` uses `RecommendedWatcher` (falling back to `PollWatcher` on `force_polling`/`ENOSYS`)
with `step_ms`/`debounce_ms`/`timeout_ms` accumulating a change set until it stabilises (`awatch`
defaults: `debounce=1600` ms window, `step=50` ms quiet period, `recursive=True`). So
`TrunkWatcher.notify()`'s 0.4s timer sits on a 50 ms/1.6s batcher, and a Rust port using `notify`
directly reaches the *same* library one layer lower — the lowest-risk module here.
Pitfalls for a trunk of one subdirectory per actor: **inotify is non-recursive in the kernel**
(`inotify(7)`), so `notify` adds one watch per directory — thousands of actors burn thousands of
watches and seconds of startup (`fs.inotify.max_user_watches` is ~1% of RAM clamped to
`[8192, 1048576]`, so 8192 is still the floor on small machines).
**Atomic-rename saves do not produce `Modify(Data)`** — temp-write + rename yields
`Modify(Name::From)`/`Remove` then `Modify(Name::To)`/`Create`, and pairing them is "inherently
racy" per the man page, so a trigger keyed only on `Modify` misses vim/JetBrains/VS Code saves.
**Event storms silently lose changes** — `max_queued_events` defaults to 16384, a `git checkout` can
overflow it and emit `IN_Q_OVERFLOW`, and only a rescan recovers. `watchfiles` handles neither.

### Typed contract, and the SPA
OpenAPI from `axum`: `utoipa` 6.0.0 (2026-09-22, 16.5M 90d dl; `#[utoipa::path]` +
`utoipa-axum` 0.3.0's `OpenApiRouter`/`routes!`/`split_for_parts()`) versus `aide` 0.15.1
(2025-08-19, 873k dl; closure-style docs + `schemars`, with 0.16 in alpha since 2025-11). Rust→TS:
`ts-rs` 12.0.1 (2026-01-31, 6.9M dl; `#[derive(TS)]`, export runs as a generated `cargo test`)
versus `specta` 2.0.0-rc.25 (RC since 2023, `specta-typescript` still 0.0.12, mostly Tauri/`rspc`).
`utoipa` + `ts-rs` is the conventional pick — stable semver on both. **OpenAPI cannot describe the
WebSocket messages** (3.1 has no channel concept) and Rust AsyncAPI tooling is thin
(`asyncapi-rust` 0.5.0 is the only live option; **no widely-adopted from-code generator could be
verified**), so define the push-message enum once in Rust and derive TS from it.
The SPA mount (`StaticFiles(directory=web/dist, html=True)` at `/`, two explicit `/session/{id}`
routes in front, a `WARNING` when `web/dist` is absent) becomes
`ServeDir::new(dist).not_found_service(ServeFile::new("dist/index.html"))` (`tower-http` 0.7.1),
which also serves prebuilt `.br`/`.gz`. For the shipped binary `rust-embed` 8.12.0 beats
`include_dir` 0.7.4 (2024-06-17): it **reads from disk in debug builds** unless `debug-embed` is
set, so a frontend edit needs no Rust rebuild.

### Long-running compute in a request
`tokio::task::spawn_blocking` runs on a pool capped by `max_blocking_threads` (default **512**),
and such tasks **cannot be aborted**: "If you call `abort` on a `spawn_blocking` task, then this
will not have any effect." Shutdown waits indefinitely for them unless `shutdown_timeout` is set,
and the docs point at semaphores or rayon instead. The `rayon` bridge is ~20 lines —
`rayon::spawn` with a `tokio::sync::oneshot` awaited in the handler (`tokio-rayon` wraps it, last
release 2021-04-05 — copy it, don't depend on it).

**Cancellation on disconnect is a real trap.** axum/hyper *do* drop the handler future when the
client disconnects (tokio-rs/axum#2610). That drops the `oneshot` receiver, but the
`spawn_blocking`/`rayon` job keeps burning CPU to completion. A 24s CSG solve behind a closed tab
needs an explicit cooperative cancel (`CancellationToken` or an `AtomicBool` checked inside the
solve) plus a `Semaphore` bounding concurrent rebuilds — today's blocking `/rebuild` has the same
problem. Progress: SSE (`axum::response::sse` + `KeepAlive`) is cheapest, but the WebSocket already
exists; either way the blocker is upstream (no progress callback in `build_scene`).

## Options

| Option | Pros | Cons |
|---|---|---|
| **A. `axum`, port `/ws` first, proxy unported `/api`** | WS upgrade proxying never happens; proxy stays plain HTTP; `/ws` has the fewest deps in the package | Push lands before the routes it reports on, so early PRs are hard to demo end to end |
| **B. `axum` + `axum-reverse-proxy` 2.2.0, `/ws` included** | One-line mount; hop-by-hop, `X-Forwarded-*`, close-frame relay free; route ownership stays in code | A dependency on the trust boundary; strips `Sec-WebSocket-Extensions`; one more thing to debug when live reload misbehaves |
| **C. Hand-rolled `hyper_util` proxy + `copy_bidirectional`** | ~60 lines, no dependency; relays `permessage-deflate` and close codes free | You own hop-by-hop hygiene, `X-Forwarded-*`, timeouts, pooling, the `read_buf` trap |
| **D. Browser connects `/ws` straight to the old port** | Zero proxy code | Breaks one-origin; `Origin` plumbing both sides; a dead end once `/ws` is ported |
| **E. Replace the WebSocket with SSE** | No upgrade handling anywhere, ever; auto-reconnect | A contract change the frontend must follow; close codes become in-band |
| **F. `nginx`/`caddy` in front of both** | No Rust proxy code at all | Three processes; route ownership moves into config that must track the strangler |

**Separate binary vs `uedcli serve` subcommand (explicitly open per the spec).** A subcommand keeps
one artifact and one `--help`, shares the project/config resolution the verb already does, and makes
the `cli`↔`serve` circularity a non-issue by construction. A separate binary keeps
`axum`/`tower`/`hyper`/`rust-embed` and the embedded `web/dist` out of every CLI invocation, and
*forces* the three shared pieces into core crates. Decisive question: does CLI binary size and cold
start matter? The code does not decide it.

## Proposal (owner's call — not decided)

`axum` 0.8.9 + `tower-http` 0.7.1, with **Option A**: port `/ws` plus the `TrunkWatcher` (`notify`
8.2.0 + `notify-debouncer-full` 0.7.0) and the claim registry as the first PR, so the strangler proxy
only ever forwards plain HTTP and this note's hardest external risk never materialises — keeping
`axum-reverse-proxy` 2.2.0 in reserve if an unported route needs WS passthrough. Port the 19 `/api`
routes in the waves tabled above, leaving `/save` and `/rebuild`
their own PRs: one is the only route that can damage a level, the other the only one needing
cancellation and concurrency bounding. Make supersession a `tokio::sync::broadcast` push (deleting
the 100 ms poll); defer `utoipa`/`ts-rs` until the route set stops moving.

## Open questions / what to verify next

- Compile time and transitive weight were **not measured** for any framework — only direct
  dependency counts, a weak proxy. Worth a `cargo build --timings` on a skeleton first. And
  `tower-proxy` 0.10.1's WebSocket support is **unverified**; `pingora`'s is in `proxy_h1.rs` but
  undocumented. Preserve the WebSocket contract exactly (A/B/C), or allow SSE (E)?
- Should `/rebuild` keep blocking at all, given `rebuild-should-run-in-background-on-a-trunk-
  snapshot`? Porting the blocking shape and changing it later means porting it twice.
- `SceneActor`'s `location`/`rotation` special-casing (`inbox/sceneactor-special-cases-location-
  rotation`, p1) and `StagingStore`'s `Location`-keyed baselines are debt the generic-prop ruling
  forbids. Inherit for differential-test parity, or fix in flight? Likewise `GET /api/levels`.

## Sources

- Internal: `old/uedcli/serve/` (16 modules), `old/uedcli/cli/{dispatch.py,commands/serve.py}`,
  `old/web/src/{api.ts,App.tsx,scene/classResolver.ts}`, `old/dev/docs/{GUI.md,architecture.md,
  epics/mvp.md,direction/trunk-and-editor.md,rationale/gui-editing.md,
  board/to-spec/persistent-gui-editing-sessions/}`; commits `593a2fe4`, `4114bf6e`, `c288842b`;
  board inbox `incremental-gui-reload-only-re-resolve-actors`,
  `incremental-csg-checkpointing-for-gui-rebuild`, `gui-unlit-fast-rebuild-button`,
  `rebuild-should-run-in-background-on-a-trunk-snapshot`, `gui-save-doesn-t-suppress-its-own-trunk-watcher`.
- crates.io API, 2026-10-03 — every version and release date in the external tables. axum:
  `docs.rs/axum/latest/axum/{extract/ws,response/sse}/`;
  `github.com/tokio-rs/axum/blob/main/examples/reverse-proxy/src/main.rs`; issue
  `tokio-rs/axum#2610`. Proxy: `docs.rs/axum-reverse-proxy/latest/`;
  `docs.rs/hyper/latest/hyper/upgrade/`; pingora's `pingora-proxy/src/proxy_h1.rs`.
- Watching: `docs.rs/notify/latest/notify/`; `man7.org/linux/man-pages/man7/inotify.7.html`;
  `fs/notify/inotify/inotify_user.c`; `github.com/samuelcolvin/watchfiles` (`Cargo.toml`,
  `src/lib.rs`); `watchfiles.helpmanual.io/api/watch/`. Also `tower-http` `ServeDir`,
  `docs.rs/tokio/.../spawn_blocking.html`, `docs.rs/rayon`, `docs.rs/rust-embed`, `ts-rs`, `aide`.
- **Unverified / reasoned only:** compile times; `tower-proxy` WS support; the direct-WS and proxy-in-front trade-offs; Rust AsyncAPI adoption.
