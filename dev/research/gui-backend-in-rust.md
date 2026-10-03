# The GUI's HTTP backend in Rust

**Date:** 2026-10-03 · **Status:** research only — no decisions taken, nothing implemented.
**Question:** What does `old/uedcli/serve/` actually expose and touch, what Rust framework and
proxy technique could carry it, and where is the strangler risky?

Server-side companion to the frontend note. Frontend findings are taken as given and only
corrected where the server disagrees.

## Summary

- `old/uedcli/serve/` is **16 modules, 3,250 LOC product + 5,415 LOC of tests** (16 `test_serve_*`
  files). `app.py` carries **23 route decorators**: 19 `/api/*`, 1 test-gated `/api/_boom`, 2 SPA
  HTML routes, 1 `@app.websocket`, plus a `StaticFiles` mount.
- **The GUI does write the trunk.** `POST /api/session/{id}/save` → `edits.save_staged` →
  `cli.level_sources.TrunkLevelSource.save`. The "never writes the trunk" line is a **P1-era**
  statement that P2 superseded; `old/dev/docs/GUI.md:205` still asserts it. One route out of 19 is
  genuinely dangerous; the other 18 cannot corrupt the trunk.
- **Nothing in `serve/` streams, and nothing invokes the editor or Docker.** No `subprocess`, no
  `driver`, no chunked/SSE response anywhere; atlases ship as base64 PNG inside JSON. The only
  reason `errors.py` classifies `DriverError` is that the CLI dispatcher shares the function.
- **Every real route is a sync `def`**, so it already runs in Starlette's threadpool. Only
  `health`, `_boom`, `_lifespan` and `ws_endpoint` are `async`. That maps cleanly onto
  `spawn_blocking`.
- **The `cli`/`serve` dependency is circular**: `serve/` → `cli/` 6 imports across 4 files
  (3 modules: `cli.errors`, `cli.level_sources`, `cli.resources`), and `cli/` → `serve/` 2 imports
  (`cli/dispatch.py` → `serve.errors.error_to_status`, 10 call sites). The shared error
  classification lives on the *GUI* side and the CLI borrows it.
- **The dominant cost is not CSG.** Recorded: Reload ~4.7s at 487 actors, ~14.4s at 2,288 actors,
  identical on a no-op repeat; Rebuild ~24s; the memoized class-schema derivation was ~3s per
  request before `593a2fe4`.
- **Supersession is polled at 100ms** (`_WS_CLAIM_POLL_INTERVAL_S`). The code attributes this to
  sync routes running in a worker thread — true as a mechanism, but `loop.call_soon_threadsafe`
  exists; the comment says the bridge "doesn't exist anywhere in this codebase," not that Python
  lacks one. Treat it as a design choice, not a platform limit.
- **The WebSocket is strictly server→client.** The client never calls `.send()`; the server reads
  and discards client text purely as a poll timer. Three message types, three close codes. That
  makes the hard part of the strangler (WS upgrade proxying) **avoidable** — see below.
- `watchfiles` being Rust/`notify`-backed is **confirmed**: `watchfiles` 1.3.0 depends on
  `notify = "8.2.0"` directly, with its own step/debounce loop and no debouncer crate.

## What we have today

| module | LOC | purpose |
|---|---|---|
| `app.py` | 1,306 | FastAPI factory, all 23 routes, `LevelContext`, claim gating, caches |
| `scene.py` | 839 | `ScenePayload` assembly: polys, actors, sprites, radii, arrows, hidden-ed filter |
| `edits.py` | 250 | stage/discard/save business logic; the only trunk writer |
| `sessions.py` | 150 | `sessions/<sid>/index.json` lifecycle (`create`/`get`/`list`/`delete`/`touch`) |
| `snapshots.py` | 137 | `StagingStore`: content-addressed blobs + per-session `staged.json` |
| `lightmap.py` | 96 | lightmap atlas pack + PNG encode (Pillow) |
| `errors.py` | 78 | `error_to_status` — shared with `cli/dispatch.py` |
| `build_pin.py` | 77 | two pins: per-session `build.json`, per-level `current.json` |
| `watch.py` | 75 | `TrunkWatcher`: `watchfiles.awatch` + 0.4s debounce |
| `package_raw.py` | 63 | resolve a package name to its `.u` path; ETag/mtime byte memo |
| `textures.py` | 58 | base-texture atlas pack + PNG encode (Pillow) |
| `claims.py` | 42 | in-memory `ClaimRegistry` (`mint`/`check`/`lock_for`/`forget`) |
| `atlas_pack.py` | 32 | shelf rect-packer shared by the two atlas builders |
| `atomic_io.py` | 27 | temp-file + `os.replace` JSON/text writes |
| `levels.py` | 18 | `GET /api/levels` payload via `cli.level_sources.list_levels` |
| `__init__.py` | 2 | — |

`serve/` imports **22 distinct core `uedcli/` modules** (`config`, `trunk`, `query`, `model`,
`emit`, `packages`, `preview`, `preview_native`, `native_ext`, `effective_props_native`, `uprops`,
`movers`, `rotation`, `writes`, `uuid7`, `classindex`, `classdefaults`, `build_cache`, `pkg_cache`,
`schema_cache`, `geometry`, `driver`). It is a thin HTTP shell over the model core — the bulk of
the port is not in `serve/`.

Runtime deps (`old/pyproject.toml`): `fastapi>=0.115`, `uvicorn>=0.32`, `watchfiles>=0.24`,
`httpx>=0.27`, `websockets>=13`, `Pillow>=11`. `uedcli serve` binds localhost, no auth
(`old/uedcli/cli/commands/serve.py`, 25 LOC: validate level, `create_app`, `uvicorn.run`).

## Findings

### Route inventory

Columns: **W** = writes (`t` trunk, `s` session/state dir, `m` in-memory only, `—` none);
**Claim** = requires `X-Claim-Token`; **Port** = proposed port-order wave.

| # | Method · path | touches | W | Claim | cost | Port |
|---|---|---|---|---|---|---|
| 1 | `GET /api/health` | nothing | — | no | trivial | 1 |
| 2 | `GET /api/levels` | maps dir listing via `cli.level_sources` | — | no | trivial | 1 |
| 3 | `GET /session/{id}`, `…/` | `web/dist/index.html` | — | no | trivial | 1 |
| 4 | mount `/` `StaticFiles(html=True)` | `web/dist` | — | no | trivial | 1 |
| 5 | `GET /api/package/{name}/raw` | search path, `.u` bytes, ETag memo | — | no | 1-2 MB body | 2 |
| 6 | `GET /api/sessions` | every `sessions/*/index.json` | — | no | small | 3 |
| 7 | `POST /api/level/{lvl}/sessions` | new session dir, mint claim, inherit level pin | s,m | no (mints) | small | 3 |
| 8 | `GET /api/session/{id}` | **mints a fresh claim**, superseding the old one | m | no (mints) | small | 3 |
| 9 | `POST /api/session/{id}/rename` | `index.json` | s | yes | small | 3 |
| 10 | `DELETE /api/session/{id}` | `rmtree sessions/<sid>/`, `claims.forget` | s,m | yes | small | 3 |
| 11 | `GET /api/session/{id}/status` | `build.json`, generation counter; `touch_session` (30s-throttled write) | s | no | small, **polled 3s/tab** | 3 |
| 12 | `GET /api/session/{id}/staged` | `staged.json` | — | no | small | 4 |
| 13 | `POST /api/session/{id}/stage` | trunk read; `staged.json` + blob write + blob eviction | s | yes | trunk read | 4 |
| 14 | `POST /api/session/{id}/discard` | `staged.json` write/remove + blob eviction | s | yes | small | 4 |
| 15 | `POST /api/session/{id}/t3d` | trunk read, staged overlay, `emit_map_with_carriers` | — | no | trunk read | 4 |
| 16 | `GET /api/session/{id}/scene` | trunk read + `build_scene_payload`/`build_wireframe_payload` | — | no | large JSON | 5 |
| 17 | `POST /api/session/{id}/load` | full trunk re-read + sprite/mesh/mover resolve; bumps `last_seen_generation` | s,m | yes | **~4.7s / ~14.4s** | 5 |
| 18 | `GET /api/session/{id}/atlas` | texture table → shelf pack → PNG → base64 | — | no | CPU + big body | 6 |
| 19 | `GET /api/session/{id}/lightmap` | lit-poly lumel grids → pack → PNG → base64 | — | no | CPU + big body | 6 |
| 20 | `POST /api/session/{id}/save` | **writes the trunk** via `TrunkLevelSource.save`; promotes level pin | **t**,s | yes | trunk write | 7 |
| 21 | `POST /api/session/{id}/rebuild` | `build_scene` CSG+lighting solve, `build_cache`, session pin, cache eviction | s,m | yes (checked **after** the solve) | **~24s** | 8 |
| 22 | `WS /ws?session=&claim=` | per-level connection set; 100ms claim/existence poll | m | yes (query param) | long-lived | 8 |
| 23 | `GET /api/_boom` | raises `CommandError` | — | — | — | never (test-only) |

Classification by kind:

- **Pure reads of the T3D trunk**: 2, 5, 12, 15, 16, 18, 19 (plus 1, 3, 4 which touch no trunk).
- **Mutating**: 7, 8, 9, 10, 11 (incidental `last_active_at`), 13, 14, 17, 20, 21. Only **20**
  touches the trunk; the rest write `.uedcli/sessions/…` or in-memory claims.
- **Editor/Docker**: **none**. `grep` over `serve/*.py` finds no `subprocess`, no `docker`, no
  `driver` use outside `errors.py`'s classification arm.
- **Streaming**: **none**. Atlas/lightmap PNGs are base64 inside JSON; `package_raw` returns one
  buffered `Response`. `GZipMiddleware(minimum_size=500)` compresses everything (recorded gains on
  `/raw`: DeusEx.u 1.92 MB → 0.38 MB, Engine.u 1.24 MB → 0.40 MB).

Port-order reasoning: waves 1-2 are the walking skeleton (static + liveness + a byte-exact binary
route with an ETag), wave 3 is session CRUD plus the claim registry (the whole concurrency model,
in-memory and cheap to differential-test), wave 4 is staging (`Decimal` boundary, no trunk write),
wave 5-6 are the heavy read payloads where the Rust renderer work lands, wave 7 is the single
trunk writer, and wave 8 is the CSG solve plus the push channel. Anything unported proxies.

### `error_to_status` is type dispatch, not a message-prefix map

A sibling note described `old/uedcli/serve/errors.py::error_to_status` as carrying a
"message-prefix→status mapping". It is the reverse: a 13-arm `isinstance` chain on **exception
type**, which *produces* the message prefixes (`"invalid coordinate: …"`, `"invalid brush
geometry: …"`, `"editor error: …"`, `"filesystem error: …"`). Arm order is load-bearing where
subclassing exists (`TimeoutError` before the `OSError` backstop). It raises `TypeError` for
anything outside the closed set, and `app.py`'s handler turns that into a logged 500 + `"internal
error"` — the only place an unclassified exception is traced.

Statuses used: 404 (`PackageRawError`), 422 (most domain errors), 500 (schema/cache/filesystem),
502 (`DriverError`/`TimeoutError`). Routes also hand-return 409 (claim/supersession/non-empty
staged on delete), 404 (unknown session on GET/DELETE only — deliberately inconsistent with the
422 the same condition gives elsewhere, flagged in the code), 304 (`/raw` ETag), 204 (DELETE).
In Rust this is one `enum` + `IntoResponse`, and it must stay shared with the CLI.

### The scene-resolution pipeline and its memo

`POST /load` and `_get_trunk` both do: `trunk.read_level_with_bodies` →
`resolve_actor_sprites` → `resolve_mesh_scene_polys` → `resolve_mover_scene_polys` → build a
`_LoadedTrunk` snapshot. `POST /rebuild` adds `edits.apply_staged_overlay` on a *copy* of the
level, then `build_scene(..., include_meshes=False, include_movers=False)`, which returns
`(polys, texture_table, owners, geom_hash, light_hash)` and self-stores into `build_cache`.
`GET /scene` then calls `build_scene_payload` (pin resolved) or `build_wireframe_payload` (no pin).

Caches, innermost out:

| cache | scope | keyed by | invalidation |
|---|---|---|---|
| `_scene_inputs_cache` | process | `project.root` | **never** (owner ruling 2026-09-28) |
| `LevelContext.scene_inputs_ref` | per level | — | replaced with `trunk_ref` |
| `LevelContext.resolve_ctx_ref` / `class_cache_ref` | per level | FQCN inside | reset with `trunk_ref` |
| `LevelContext.trunk_ref` | per level | generation guard | `/load`, or generation bump mid-build |
| `_BuildResultCache` | process | `(level, geom_hash, light_hash)` | LRU, 8 entries |
| `build_cache` (on disk) | project | content hashes | `evict_unreferenced` on rebuild |

`593a2fe4` ("Memoize scene-resolution inputs across GUI /load and /rebuild requests") added the
first row. Before it, `index`/`defaults` were re-derived per `/load` and `/rebuild` — **~3s of
class-schema re-parsing on a real level, the dominant cost of both, not the CSG solve**. The commit
records the deliberate trade: already-loaded packages are never invalidated during a `serve` run,
so a package edited on disk needs a process restart; a manual reload verb is future work. Keyed by
`project.root` rather than `id(project)` (GC address-reuse hazard) or the object (test fixtures
pass an unhashable `SimpleNamespace`) — `4114bf6e` fixed that.

Lock-free read ordering is load-bearing and easy to break in a port: `scene_inputs_ref` and
`class_cache_ref` are written **before** `resolve_ctx_ref`, which is written **before**
`trunk_ref`, so no reader ever pairs a new trunk with stale resolution state. In Rust this whole
pattern collapses into one `ArcSwap`/`RwLock<Arc<LoadedTrunk>>` holding all five together, which
removes the ordering hazard by construction.

### Performance picture

`old/dev/docs/epics/mvp.md` has exactly one entry, and it is this topic: board item
`incremental-gui-reload-only-re-resolve-actors` — "GUI Reload re-resolves every actor from scratch
on every call; want it to diff against the session's last-loaded snapshot … targeting hundreds of
ms instead of scaling with the whole level."

Recorded numbers:

| measurement | value | source |
|---|---|---|
| Reload, 487 actors | ~4.7s | `inbox/incremental-gui-reload-only-re-resolve-actors` |
| Reload, 2,288 actors | ~14.4s | same — **identical on a no-op repeat** |
| Rebuild (CSG + lighting) | ~24s | `old/web/src/api.ts` `postRebuild` doc |
| class-schema re-derive, per request | ~3s | `593a2fe4` commit message |
| `build_scene_payload`, synthetic 2,288 actors / 19 classes | ~1.8s every call → ~1.8s once then ~0.06s | `scene.py` docstring |
| `/status` poll | every 3,000 ms per open tab | `old/web/src/App.tsx` `STATUS_POLL_MS` |
| WS claim poll | every 100 ms per open socket | `_WS_CLAIM_POLL_INTERVAL_S` |

`c288842b` ("board: rescue two orphaned GUI-rebuild-perf findings") recovered two ideas from an
abandoned uncommitted worktree: `incremental-csg-checkpointing-for-gui-rebuild` (checkpoint the
native CSG world-model per brush-order position so an edit replays only from the changed position
forward — order-dependent algorithm, so today any brush change re-solves the whole level) and
`gui-unlit-fast-rebuild-button` (decouple lighting from CSG for a fast unlit preview; survives only
as a one-sentence cross-reference, original author unidentified). `rebuild-should-run-in-background-
on-a-trunk-snapshot` asks for `/rebuild` to return immediately and report via the WS or `/status`,
plus real phase-level progress — and records that `build_scene` and the native solve have **no
progress-callback mechanism at all** today.

Two blockers named for incremental Reload, both relevant to how the Rust types get designed:
`_LoadedTrunk`'s tables are flat lists built in one pass over all actors (need to be keyed/mergeable
by actor name), and texture indices are deduped by table *position* (need a content-keyed registry
so adding one actor doesn't shift everyone's stored index). Designing that in from the start costs
nothing extra; retrofitting it is the reason the item is still unspec'd.

### Live reload, server-side

`TrunkWatcher` (75 LOC) watches **one level's trunk directory** (`<maps>/<level>/`) with
`watchfiles.awatch`, recursive by default, and feeds every raw batch into `notify()`. `notify()` is
a 0.4s restartable timer: N calls inside the window collapse to one `on_change`. The timer task
holds only the sleep phase — `on_change` runs as a separate untracked task, so a `notify()`
arriving mid-broadcast cancels only a pending timer, never the broadcast (a prior review finding).

`on_change` is `_on_trunk_settled`: `generation += 1`, `changes_available = True`,
`_broadcast_changes_available` — which iterates a **snapshot** of `ctx.connections` (awaiting
`send_json` yields the loop; a concurrent connect/disconnect would otherwise raise "Set changed
size during iteration" and drop the whole broadcast) and never takes `trunk_lock`.

One watcher per `LevelContext`. The startup level's is started by `_lifespan`; a lazily created
level's is started by `ws_endpoint` on first connect (`start()` is not idempotent — calling it
twice leaks `_watch_task`). `_lifespan` shutdown sweeps every context under the lock.

Message shapes — exactly three, all server→client:

| message | sent by | trigger |
|---|---|---|
| `{"type":"changes_available","level":"<name>"}` | `_broadcast_changes_available` | debounced trunk change |
| `{"type":"superseded"}` | connect check, or 100ms poll | a newer claim was minted |
| `{"type":"closed"}` | 100ms poll | session directory gone |

Close codes: **4001** (unknown session or missing claim — closed without `accept()`), **4003**
(claimed elsewhere, after an `accept()` so the client can learn it), **4004** (session deleted).

**The poll-vs-push claim, verified.** `changes_available` *is* pushed — its trigger lives on the
event loop. Only supersession and deletion are polled, because they originate in
`claims.mint`/`sessions.delete_session`, called from sync `def` routes that Starlette runs in the
anyio worker threadpool. The code's own words: "there is no cheap direct way for that thread to
push into an already-open WS living on a different thread's loop without a real
cross-thread-to-loop bridge, which doesn't exist anywhere in this codebase today." That last clause
is accurate about the codebase; it is not a Starlette limitation — `asyncio.run_coroutine_threadsafe`
/ `loop.call_soon_threadsafe` is the standard bridge. In Rust the question vanishes: a
`tokio::sync::broadcast` or `watch` channel is callable from any thread, so supersession becomes a
push and the 100ms tick disappears.

**Known wart, already filed.** The GUI's own Save trips its own watcher.
`inbox/gui-save-doesn-t-suppress-its-own-trunk-watcher` records that the post-Save `/load` usually
completes inside the 0.4s debounce, so the watcher re-sets the flag afterwards and the user sees
"changes available" for their own save — "the default case, not a rare race." Under the current
session-scoped code it is structurally the same: `/load` calls `set_last_seen_generation`, `/save`
does not, so the generation bump from one's own write leaves `changes_available` true. Per the
frozen-`old/` rule this is a `TODO` for the new code, not a fix in `old/`.

### Sessions: two different things, one word

These are **not** the same concept and must not be conflated:

- **The deleted level session store.** The pre-2026-07 editor-centric model held the authoritative
  level in a live UnrealEd, with every read a `MAP EXPORT` and an interim on-disk session store
  (slices ≤3). `old/dev/docs/architecture.md` records it was **deleted outright**;
  `old/dev/docs/direction/trunk-and-editor.md` states "There is no session and no session store —
  git is the history and merge engine," and explicitly rejects "a bespoke event-sourced session
  store." This is about *level authority and history*, and git replaced it.
- **GUI editing sessions.** `old/dev/docs/board/to-spec/persistent-gui-editing-sessions/` — a
  durable, per-browser-tab unit of *GUI navigation and unsaved work*: its own id (uuid7), its own
  `staged.json`, its own independently-solved build pin (deduped against a shared content-hash
  cache), its own `last_seen_generation`, surviving a refresh and a server restart, with no
  auto-expiry. It carries **no history and no merge authority**, and a save still funnels into the
  one model-side trunk write path. `old/dev/docs/rationale/gui-editing.md` is the standing argument
  that this is "one more writer on the existing trunk write path," not a direction change.

Mechanics as built: a session is created only by a real page load
(`POST /api/level/{lvl}/sessions`), never automatically — `create_app(project, level=None)` starts
with **zero** `LevelContext`s. Ownership is a `claim_token`: `GET /api/session/{id}` mints a fresh
one on every call, deliberately non-idempotent, so "whichever window last loaded always wins." The
sibling note is right that this GET mutates and that it is load-bearing. `ClaimRegistry` is
in-memory only and `check` treats an *unrecorded* id as a legitimate first claim (restart safety) —
which is why every gated route also re-checks `sessions.get_session(...) is not None` under the same
per-session lock, or a DELETE racing a request would resurrect the directory via
`atomic_write_json`'s unconditional `mkdir`. That interleaving is the single subtlest thing in the
package and the thing a port is most likely to get wrong.

Storage: `.uedcli/sessions/<sid>/{index.json,staged.json,build.json}` plus shared
`.uedcli/staging/blobs/` and the project build cache. All writes go through `atomic_io`
(temp + `os.replace`).

**Board-stage drift:** the item sits in `to-spec` with a `spec.md` and no `plan.md`, yet the code
is littered with "plan Task 9/11/12/13/14/15" references and the work has clearly shipped.

### Doc drift the server confirms

The sibling found three stale `api.ts` citations and three drifted spots in `GUI.md`. Server-side
confirmation, plus more:

- `PUT /api/level` **does not exist** in `app.py`. `GUI.md` still documents the level-switch flow
  around it, and `errors.py`'s `json.JSONDecodeError` arm comments on "`PUT /api/level`'s
  `await request.json()`" — a comment for a route that is gone.
- `GET /api/level/{level}/status` and `POST /api/level/{level}/save` are cited in `api.ts` doc
  comments; neither exists. Both are session-scoped now.
- `GUI.md:3` calls the API "read-mostly" and `GUI.md:205` says "this GUI is P1, read-only, no write
  path" — P2 shipped a trunk writer.
- `scene.py`'s `build_scene_payload` docstring credits the fix to `app.py`'s
  `_payload_ref`/`_get_payload`; neither identifier exists any more (removed when Rebuild became
  session-scoped).
- The sessions spec says "`PUT /api/level` and `GET /api/levels` have no place in the new API
  surface." `GET /api/levels` is still mounted and still called from `api.ts`.
- `/api/package/{name}/raw` is fetched from `old/web/src/scene/classResolver.ts:57`, **not** from
  `api.ts` — a small correction to "all called from `api.ts`".
- `GET /api/health` is mounted but called from nowhere in `old/web/src`.

Two board items in the brief are not GUI-backend concerns at all:
`level-preview-multi-preview-port-url-surfacing` is about the noVNC port for `level photo`'s Docker
editor, and `boot-time-floating-windows` is a `uned/` ini/entrypoint chore — out of scope for this
rewrite by the spec's own Scope section.

### Reuse vs duplication, and what it means for crate layering

Measured edges, both directions:

| direction | edges | modules |
|---|---|---|
| `serve/` → `cli/` | 6 imports in 4 files | `cli.errors` (×3), `cli.level_sources` (×2), `cli.resources` (×1) |
| `cli/` → `serve/` | 2 imports | `cli/dispatch.py` → `serve.errors` (10 call sites); `cli/commands/serve.py` → `serve.app` (deferred) |

The sibling's "8 edges (`cli.errors`, `cli.resources`)" matches the total only if both directions
are counted, and it misses `cli.level_sources` — which is the important one, because
`TrunkLevelSource` is *the* trunk write path and `list_levels` is *the* level enumeration. So
`serve/` genuinely reuses rather than duplicates: there is no second write mechanism, no second
level enumeration, no second error classifier.

But the direction is wrong for a clean crate split. Three things currently filed under `cli/` or
`serve/` are really **shared core**:

- `error_to_status` — lives in `serve/`, imported by the CLI dispatcher. Belongs in the error crate.
- `TrunkLevelSource` / `level_sources` — lives in `cli/`, is the model-side write path both
  surfaces use. Belongs in the trunk crate.
- `resources.resolve_project` / `resources.mover_index` — lives in `cli/`, used by `serve` and the
  `serve` verb. Belongs in a project/config crate.

That is exactly what the rewrite spec's "plain code reuse (the CLI handler and the GUI handler both
call the same core function)" asks for, once those three move down a layer. The spec rejected a
generic schema-driven CLI/GUI registry; nothing here argues against that rejection — the duplication
it was meant to solve (brush-builder definitions) does not exist in `serve/` today, because
`serve/` has no brush-builder routes yet. The thing to watch is the *future* case the
`gui-builder-brushes` ruling in `old/dev/docs/rationale/gui-editing.md` describes: a generic
property path mirroring `propedit`'s plan/apply, never a per-field endpoint. That ruling also names
the existing debt — `scene.py`'s `SceneActor` carries dedicated `location`/`rotation` fields beside
its generic `props` list, and `StagingStore` stages `Location` specifically with baseline/conflict
machinery keyed to that one field. A port that copies that shape inherits the debt.

### Does the GUI write the trunk?

**Yes, through exactly one route.** `POST /api/session/{id}/save` → `edits.save_staged` →
`TrunkLevelSource.save(verb="move", …)`. The write is defended in depth: claim check and session
existence re-check under `claims.lock_for(session_id)`; per-actor conflict detection against the
baseline captured at stage time; an immediate pre-write re-read of every touched actor's trunk
`Location` that reverts and re-flags anything that moved in the gap (narrowing, not eliminating,
the TOCTOU window); then one load + one save for the whole batch through the same
delete-then-readd-with-rollback path every CLI verb uses. Pin promotion is sequenced strictly after
the trunk write, under `trunk_lock`, never while the claim lock is held.

So the port's danger is concentrated, not diffuse: 18 of 19 routes can at worst produce a wrong
picture or a stale cache, and the differential test for them is "same JSON for the same trunk."
Route 20 can corrupt a user's level, and it needs the conflict/TOCTOU semantics ported exactly,
with the flock + refuse-same-actor-concurrent-edit rule from `direction/safety.md` intact. The
honest framing for the owner: the GUI backend is a *safe* port everywhere except one route, and
that one route deserves its own PR.

### Rust HTTP frameworks (external; versions from the crates.io API, 2026-10-03)

| | version | last release | 90d dl | WebSocket | static/SPA | streaming | middleware | OpenAPI |
|---|---|---|---|---|---|---|---|---|
| `axum` | 0.8.9 | 2026-04-14 | 127.0M | built-in (`ws` feature) | `tower-http` `ServeDir` + `not_found_service` | `Body::from_stream` | tower | `utoipa-axum`, `aide` |
| `actix-web` | 4.15.0 | 2026-08-21 | 11.4M | `actix-ws` 0.4.0 (separate) | own `Files` | yes | bespoke `Service`/`Transform`, **not tower** | `utoipa` (actix bindings) |
| `salvo` | 1.0.0 | 2026-09-24 | ~0.3M | built-in | built-in | yes | own + `tower-compat` | `salvo-oapi` |
| `poem` | 3.1.12 | **2025-07-28** | 0.41M | built-in | built-in | yes | own + `tower-compat` | `poem-openapi` |
| `rocket` | 0.5.1 | **2024-05-23** | 2.16M | via `rocket_ws` | built-in | yes | fairings | third-party |

Reads of that table: `axum` is ~11× `actix-web` by downloads and the only one with a dominant
middleware ecosystem, so every piece this backend needs (compression to replace
`GZipMiddleware`, `ServeDir`, tracing, timeouts, a reverse proxy) is one `tower` layer.
`rocket` is dormant — 2.3 years since a release, last commit 2025-12-28; not a candidate for a
late-2026 target. `poem`'s repo is busy under a new maintainer but has had **no crates.io release
in 14 months**. `salvo` 1.0.0 is three weeks old with a thin ecosystem. `actix-web` is healthy and
fast, but its middleware stack is tower-incompatible, which means re-implementing what `tower-http`
gives free. Direct normal-dependency counts (a weight proxy only — **no compile times were
measured**): `salvo` 17, `axum` 33, `rocket` 31, `actix-web` 36 including its own runtime and actor
layer.

Nothing in this backend's shape stresses a framework. 23 routes, one WebSocket, no streaming today,
and the heavy work is all CPU in a threadpool. The choice is about ecosystem, not capability.

### The WebSocket-proxy risk — and why it is avoidable here

This is the one genuinely hard part of the strangler, and this contract makes it optional.

**Why it is hard.** Proxying a WebSocket means intercepting the `101 Switching Protocols`
handshake, forwarding `Sec-WebSocket-Key`/`-Version`/`-Protocol`/`-Extensions`, relaying the
upstream's `Sec-WebSocket-Accept` **verbatim** (recomputing it yourself is the classic silent
handshake failure), calling `hyper::upgrade::on` on both the client request and the upstream
response, then byte-copying with `tokio::io::copy_bidirectional`. Named pitfalls: `Upgraded`'s
`Parts::read_buf` holds bytes already read during the handshake, so destructuring it instead of
using it as an `AsyncRead` silently eats the first frame; `copy_bidirectional` returns only when
both directions finish, so a peer that stops reading without closing leaks the task; a
frame-decoding proxy cannot relay `permessage-deflate` and must re-mask client→server frames; and a
naive bridge collapses every disconnect into close code 1006, destroying the 4001/4003/4004
contract.

**Off-the-shelf options.**

| crate | version | last release | WS upgrade | status |
|---|---|---|---|---|
| `axum-reverse-proxy` | 2.2.0 | 2026-08-29 | yes, frame-level | active; `axum ^0.8`, `hyper ^1`, `tokio-tungstenite ^0.28` |
| `tower-proxy` | 0.10.1 | 2026-09-22 | **unverified** | active fork of the deprecated `axum-proxy` |
| `pingora` | 0.9.0 | 2026-09-09 | yes (h1 upgrade passthrough, undocumented) | Cloudflare; a whole server, not an axum layer |
| `hyper-reverse-proxy` | 0.5.1 | **2022-03-12** | no | dead, predates hyper 1.0 |
| `reverse-proxy-service` | 0.2.1 | 2023-09-11 | not documented | superseded |

`axum-reverse-proxy` 2.2.0 is a one-line mount (`ReverseProxy::new("/api", "http://127.0.0.1:8000")`
→ `Router`) and claims RFC 9110 §7.6.1 hop-by-hop stripping, `X-Forwarded-*`, and verbatim close-frame
forwarding. It **strips `Sec-WebSocket-Extensions`** because it forwards frames, not bytes — harmless
here, since these three tiny JSON messages gain nothing from compression. `tower-http` has no
forwarding layer at all. `pingora` is the wrong shape: it is a server framework, not something you
mount inside `axum` while Rust owns individual routes.

**Why it is avoidable.** The contract is three server→client JSON messages and three close codes,
and the client **never sends a frame** (`old/web/src/api.ts` `openChangesAvailableSocket` only adds
a `message` listener; `ws_endpoint` reads client text solely as a poll timer and discards it). That
means:

1. **Port `/ws` first, before any `/api` route.** It depends on almost nothing — the
   `watchfiles`-equivalent watcher, the per-level connection set, and the claim registry. Owning it
   in Rust from day one means the proxy only ever forwards plain HTTP, which is the easy case.
   This inverts the usual instinct to port the push channel last.
2. **If `/ws` must be proxied anyway**, the fallback is to point the browser's socket directly at
   the old backend's port. No proxy code at all; the cost is breaking the one-origin assumption
   (the WS URL needs separate host/port plumbing and the uvicorn-side `Origin` check must accept
   it). WebSockets are not CORS-governed, so CORS is a non-issue. Acceptable for a local,
   no-auth, dev-only channel; bad if it ever carries session state. *(Reasoned, not sourced.)*
3. **A rewrite to SSE is on the table** precisely because the channel is one-directional.
   `axum::response::sse` with `KeepAlive` needs no upgrade handling, reconnects automatically, and
   proxies as ordinary HTTP. Costs: close codes become an in-band field, and SSE counts against the
   HTTP/1.1 6-connections-per-origin limit. This is a contract change, so it is the owner's call,
   not something a port should do silently.

**Plain-HTTP proxy gotchas** (the part that is unavoidable). The canonical reference is axum's own
`examples/reverse-proxy`, which uses `hyper_util::client::legacy::Client<_, axum::body::Body>` —
**not `reqwest`**, because passing axum's `Body` through streams both directions with no buffering,
while `reqwest` forces `Bytes`/`Stream` adapters and loses trailers. The example is a toy: it
strips no hop-by-hop headers, sets no `X-Forwarded-*`, and maps every error to 400. Add yourself:
strip `Connection` (and every header it names), `Transfer-Encoding`, `Upgrade`, `Keep-Alive`, `TE`,
`Trailer`, `Proxy-*` on both legs (forwarding `Transfer-Encoding: chunked` into hyper 1.x
double-encodes); decide `Host` rewrite-vs-preserve; map connect errors to 502 and your own
`tokio::time::timeout` to 504 (**hyper has no default timeout**, so a hung uvicorn hangs the
request forever); hold **one** pooled `Client` in state with `pool_idle_timeout` below uvicorn's
5s keep-alive, or reused sockets race into spurious 502s. Keep the client leg on HTTP/1.1 —
upgrades do not exist in h2.

### File watching in Rust

`notify` is stable at **8.2.0** (2025-08-03), with a 9.0.0-rc line running since early 2026 (rc.5,
2026-08-30) — not shipped. Backends: inotify on Linux, FSEvents on macOS, `ReadDirectoryChangesW`
on Windows, `PollWatcher` everywhere as fallback. `notify-debouncer-full` 0.7.0 (2026-01-23) adds
per-path coalescing **plus rename stitching** (pairing `RenameMode::From`/`To`);
`notify-debouncer-mini` 0.7.0 only does time-based dedup.

**The `watchfiles` claim is confirmed.** `watchfiles` 1.3.0's `Cargo.toml` depends directly on
`notify = "8.2.0"` with `pyo3 = "0.29.2"`, and its PyPI description says so outright. It uses
**neither** debouncer crate — it runs its own loop in `src/lib.rs` (`RecommendedWatcher`, falling
back to `PollWatcher` on `force_polling` or `ENOSYS`), with `step_ms`/`debounce_ms`/`timeout_ms`
accumulating a change set until it stabilises. `awatch` defaults: `debounce=1600` ms max grouping
window, `step=50` ms quiet period, `rust_timeout=5000` ms, `recursive=True`. So
`TrunkWatcher.notify()`'s 0.4s timer sits on top of a 50ms/1.6s batcher, and a Rust port using
`notify` directly reaches the *same* library one layer lower — this is the lowest-risk module in
the whole package.

Pitfalls that matter for a trunk directory of one subdirectory per actor:

- **inotify is non-recursive in the kernel** (`inotify(7)`): `notify` walks the tree and adds one
  watch per directory. A level with thousands of actors burns thousands of watches and seconds of
  startup. `fs.inotify.max_user_watches` is no longer a flat 8192 — the kernel computes ~1% of
  addressable RAM clamped to `[8192, 1048576]` — but 8192 is still the floor on small machines, and
  `max_user_instances` defaults to 128.
- **Atomic-rename saves do not produce `Modify(Data)`.** An editor writing temp + renaming over the
  target yields `Modify(Name::From)`/`Remove` then `Modify(Name::To)`/`Create`. Matching the pair is
  "inherently racy" per the man page. A trigger keyed only on `Modify` misses saves from vim,
  JetBrains, and VS Code with atomic save. `notify-debouncer-full` exists for exactly this.
- **Event storms silently lose changes.** `max_queued_events` defaults to 16384; a `git checkout`
  or `rebase` across a large trunk can overflow it and emit `IN_Q_OVERFLOW`. Debouncing reduces
  downstream work but does not prevent kernel-side overflow — overflow has to trigger a rescan.
  `watchfiles` does not handle this today either, so it is a new-code improvement, not a regression.

### Typed contract across the boundary

| tool | version | last release | shape |
|---|---|---|---|
| `utoipa` (+ `utoipa-axum` 0.3.0) | 6.0.0 | 2026-09-22 | 16.5M 90d dl; `#[utoipa::path]` per handler, `OpenApiRouter` + `routes!` + `split_for_parts()` |
| `aide` | 0.15.1 | 2025-08-19 | 873k 90d dl; closure-style docs + `schemars::JsonSchema`; 0.16 alpha since 2025-11 |
| `ts-rs` | 12.0.1 | 2026-01-31 | 6.9M 90d dl; `#[derive(TS)]`, export runs as a generated `cargo test` |
| `specta` | 2.0.0-rc.25 | 2026-05-07 | RC since 2023; `specta-typescript` still 0.0.12; mostly Tauri/`rspc` |

For 22 routes, `utoipa` + `ts-rs` is the conventional pick (stable semver on both; `ts-rs`'s
test-driven export fits CI). **OpenAPI cannot describe the WebSocket messages** — 3.1 has no
channel concept — and Rust AsyncAPI tooling is thin (`asyncapi-rust` 0.5.0, ~70k 90d dl, is the
only live option; no widely-adopted from-code generator could be verified). The practical answer
for this contract is to define the push-message enum once in Rust, derive TS from it, and document
the channel and its close codes in prose. That is strictly better than today, where the three
message shapes exist only as hand-written TS interfaces in `api.ts` and hand-written dicts in
`app.py`.

### SPA plus API from one binary

Today `app.py` mounts `StaticFiles(directory=web/dist, html=True)` at `/` with two explicit
`/session/{id}` routes in front, and logs a `WARNING` when `web/dist` is absent (staying API-only —
deliberate, so a packaging drift is visible). The Rust equivalent is
`ServeDir::new(dist).not_found_service(ServeFile::new("dist/index.html"))` (`tower-http` 0.7.1),
which also serves prebuilt `.br`/`.gz` via `precompressed_br`/`precompressed_gzip`.

For the shipped binary, `rust-embed` 8.12.0 (2026-07-08) over `include_dir` 0.7.4 (last release
2024-06-17): `rust-embed` **reads from disk in debug builds** unless `debug-embed` is set, so a
frontend edit needs no Rust rebuild, while release builds embed. `include_dir` always embeds, so
every asset change forces a recompile. `axum-embed` 0.1.0 is frozen at one release from 2023 —
inline the glue instead. Atlas PNGs are generated per request and must not be embedded.

### Long-running compute in a request

Every heavy route is already a sync `def` in a threadpool, so the mapping is direct — but three
details bite:

- `tokio::task::spawn_blocking` runs on a pool capped by `max_blocking_threads` (default **512**).
  The docs are explicit that such tasks **cannot be aborted**: "If you call `abort` on a
  `spawn_blocking` task, then this will not have any effect." Runtime shutdown waits indefinitely
  for running blocking tasks unless `shutdown_timeout` is set. The docs themselves point at
  semaphores or rayon for CPU-bound work.
- The `rayon` bridge is ~20 lines: `rayon::spawn(move || { let _ = tx.send(heavy()); })` with a
  `tokio::sync::oneshot` awaited in the handler. `tokio-rayon` wraps exactly this but its last
  release is 2021-04-05 — copy the pattern, do not depend on it.
- **Cancellation on disconnect is a real trap.** axum/hyper *do* drop the handler future when the
  client disconnects (tokio-rs/axum#2610). The dropped future drops the `oneshot` receiver, but the
  `spawn_blocking`/`rayon` job keeps burning CPU to completion. A 24s CSG solve behind a user who
  closed the tab needs an explicit cooperative cancel (`CancellationToken` or `AtomicBool` checked
  inside the solve) plus a `Semaphore` bounding concurrent rebuilds — otherwise abandoned work
  queues up. This is a *new* requirement: today's blocking `/rebuild` has the same problem, which
  is part of why `rebuild-should-run-in-background-on-a-trunk-snapshot` was filed.
- Progress: `axum::response::sse` with `KeepAlive` is the cheap one-way option, but a WebSocket
  already exists, so folding progress into it avoids a second connection and SSE's
  6-connections-per-origin ceiling. Either way, the blocker is upstream — `build_scene` and the
  native solve expose **no progress callback at all**.

## Options

| Option | Pros | Cons |
|---|---|---|
| **A. `axum` + port `/ws` first, proxy unported `/api`** | WS upgrade proxying never happens; proxy stays plain HTTP; `/ws` has the fewest dependencies of anything in the package | Push channel lands before the routes it reports on, so early PRs are hard to demo end-to-end |
| **B. `axum` + `axum-reverse-proxy` 2.2.0 for everything incl. `/ws`** | One-line mount; hop-by-hop, `X-Forwarded-*`, close-frame relay for free; route ownership stays in Rust code | Adds a dependency on the trust boundary; strips `Sec-WebSocket-Extensions`; one more thing to debug when live reload misbehaves |
| **C. Hand-rolled `hyper_util` proxy + `copy_bidirectional` for `/ws`** | ~60 lines, no dependency, relays `permessage-deflate` and close codes for free | You own hop-by-hop hygiene, `X-Forwarded-*`, timeouts, pooling, and the `read_buf` trap |
| **D. Browser connects `/ws` straight to the old port** | Zero proxy code | Breaks the one-origin assumption; `Origin` plumbing on both sides; a dead end once `/ws` is ported |
| **E. Replace the WebSocket with SSE** | No upgrade handling anywhere, ever; proxies as plain HTTP; auto-reconnect | A contract change the frontend must follow; close codes become in-band |
| **F. `nginx`/`caddy` in front of both** | No Rust proxy code at all | Three processes; route ownership moves into config that must track the strangler's progress |

Separate-binary vs `uedcli serve` subcommand (**explicitly open per the spec**): a subcommand keeps
one artifact, one `--help`, and shares the project/config resolution the verb already does, and it
matches what users type today. A separate binary keeps `axum`/`tower`/`hyper`/`rust-embed` and the
embedded `web/dist` out of every CLI invocation's binary and link time, and lets the GUI backend
ship on its own cadence. The decisive question is whether the CLI binary's size and cold-start cost
matter to the owner; nothing in the code forces either answer. Note that a subcommand makes the
`cli`↔`serve` circular dependency a non-issue by construction, while a separate binary forces the
three shared pieces (`error_to_status`, `TrunkLevelSource`, `resolve_project`) down into core crates
— which is the right layering anyway.

## Proposal (owner's call — not decided)

`axum` 0.8.9 + `tower-http` 0.7.1, with **Option A**: port `/ws` plus the `TrunkWatcher`
(`notify` 8.2.0 + `notify-debouncer-full` 0.7.0) and the claim registry as the GUI backend's first
PR, so the strangler proxy only ever forwards plain HTTP and the hardest external risk in this note
never materialises. Keep `axum-reverse-proxy` 2.2.0 in reserve as the escape hatch if an unported
route turns out to need WS passthrough after all. Port the 19 `/api` routes in the waves tabled
above, leaving `POST /save` and `POST /rebuild` for their own PRs — one because it is the only
route that can damage a user's level, the other because it is the only one that needs the
cancellation/semaphore machinery. Make supersession a `tokio::sync::broadcast` push and delete the
100ms poll. Defer `utoipa`/`ts-rs` until the route set stops moving; hand-write the TS types until
then, as today.

## Open questions / what to verify next

- Compile time and transitive dependency weight were **not measured** for any framework — only
  direct normal-dependency counts, which is a weak proxy. Worth a real `cargo build --timings` on a
  skeleton before committing.
- `tower-proxy` 0.10.1's WebSocket support is **unverified**; `pingora`'s is implemented in
  `proxy_h1.rs` but absent from its docs.
- Whether the owner wants the WebSocket contract preserved exactly (favours A/B/C) or is open to
  SSE (E). This decides how much of this note's risk section is live.
- Whether `/rebuild` should keep blocking at all, given
  `rebuild-should-run-in-background-on-a-trunk-snapshot` wants it async. Porting the blocking shape
  first and changing it later means porting it twice.
- The `SceneActor` `location`/`rotation` special-casing (`inbox/sceneactor-special-cases-location-
  rotation`, p1) and `StagingStore`'s `Location`-keyed baseline machinery are known debt the
  standing generic-prop ruling forbids. Does the port inherit them for differential-test parity, or
  fix them as it goes? The frozen-`old/` rule says `old/` keeps the bug and the new code carries a
  `TODO`, which argues for inheriting the *output* while restructuring the *internals*.
- `GET /api/levels` is still mounted and still called, though the sessions spec says it has no
  place in the new surface. Port it, or drop it with the frontend refactor?

## Sources

- `old/uedcli/serve/` (all 16 modules), `old/uedcli/cli/commands/serve.py`,
  `old/uedcli/cli/dispatch.py`, `old/web/src/api.ts`, `old/web/src/scene/classResolver.ts`,
  `old/web/src/App.tsx` — the route surface, caches, claim/lock protocol, and WS contract.
- `old/dev/docs/board/to-spec/persistent-gui-editing-sessions/{overview,spec}.md` — GUI editing
  sessions; `old/dev/docs/direction/trunk-and-editor.md` + `old/dev/docs/architecture.md` — the
  deleted level session store.
- `old/dev/docs/rationale/gui-editing.md` — the P2 staging/Save reasoning and the
  no-special-cased-props ruling. `old/dev/docs/GUI.md` — frontend architecture (drifted, see above).
- Commits `593a2fe4`, `4114bf6e` (scene-inputs memo), `c288842b` (rescued perf findings).
- Board: `inbox/incremental-gui-reload-only-re-resolve-actors` (the sole `epics/mvp.md` entry),
  `inbox/incremental-csg-checkpointing-for-gui-rebuild`, `inbox/gui-unlit-fast-rebuild-button`,
  `inbox/rebuild-should-run-in-background-on-a-trunk-snapshot`,
  `inbox/gui-save-doesn-t-suppress-its-own-trunk-watcher`.
- crates.io API, 2026-10-03 — every version and release date in this note's external tables.
- https://docs.rs/axum/latest/axum/extract/ws/index.html — `WebSocketUpgrade`, `on_upgrade`.
- https://docs.rs/tower-http/latest/tower_http/services/fs/struct.ServeDir.html — SPA fallback,
  precompressed assets.
- https://github.com/tokio-rs/axum/blob/main/examples/reverse-proxy/src/main.rs — the `hyper_util`
  forwarding pattern (and what it omits).
- https://docs.rs/axum-reverse-proxy/latest/axum_reverse_proxy/ — `ReverseProxy`, `ProxyPolicy`,
  hop-by-hop stripping, close-frame relay, `Sec-WebSocket-Extensions` stripping.
- https://docs.rs/hyper/latest/hyper/upgrade/index.html — `upgrade::on`, `Parts::read_buf`.
- https://github.com/cloudflare/pingora/blob/main/pingora-proxy/src/proxy_h1.rs — h1 upgrade
  passthrough (implemented, undocumented).
- https://docs.rs/notify/latest/notify/ · https://man7.org/linux/man-pages/man7/inotify.7.html ·
  `fs/notify/inotify/inotify_user.c` — backends, non-recursive watches, rename raciness, limits.
- https://github.com/samuelcolvin/watchfiles/blob/main/Cargo.toml and `src/lib.rs` ·
  https://watchfiles.helpmanual.io/api/watch/ — the `notify` 8.2.0 dependency and `awatch` defaults.
- https://docs.rs/tokio/latest/tokio/task/fn.spawn_blocking.html — no abort, 512-thread default.
- https://github.com/tokio-rs/axum/issues/2610 — handler futures are dropped on client disconnect.
- https://docs.rs/rayon/latest/rayon/fn.spawn.html · https://docs.rs/rust-embed ·
  https://crates.io/crates/ts-rs · https://docs.rs/aide/latest/aide/axum/index.html.
- **Unverified / reasoned only:** compile times and transitive weights; `tower-proxy` WS support;
  the direct-WS-to-old-port and `nginx`/`caddy` trade-offs; whether any Rust AsyncAPI generator has
  real adoption.
