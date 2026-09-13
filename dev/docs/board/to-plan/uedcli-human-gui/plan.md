# uedcli human GUI — P1 Implementation Plan

> **For agentic workers:** use `superpowers:subagent-driven-development` or `superpowers:executing-plans`
> to implement task-by-task. Follow `dev/docs/rules/building-features.md` (worktree, verify, review,
> squash-merge). This plan details **Slice 1** (the thin end-to-end skeleton); Slices 2–4 are
> milestone outlines that each get their own detailed plan when scheduled.

**Goal:** A read-only browser GUI over the T3D trunk — navigate/inspect a level and audit AI changes —
served by `uedcli serve`, with the viewport drawing a scene the existing `--native` path solves.

**Architecture:** FastAPI+uvicorn backend wraps the model-side library and holds all logic; a
React/TS + react-three-fiber client draws a scene payload and owns only camera + selection. The DRY
seam: backend ships the same solved scene `level photo --native` consumes; client draws it; a photo
action routes through the identical `render_frame` for pixel-identical stills.

**Tech Stack:** Python (FastAPI, uvicorn, `websockets`/Starlette WS), existing `uedcli-native` +
`preview_native`/`preview_cache`/`utexture`/`stashlib`; React + TypeScript + react-three-fiber
(three.js) + Vite.

**Spec:** `dev/docs/board/to-plan/uedcli-human-gui/spec.md` (read it — this plan argues from it).

## Global Constraints

- **Read-only (P1):** no endpoint writes the trunk. `serve` may write only `.uedcli/` (cache,
  snapshots) and the client's camera-bookmarks sidecar (outside the watched path).
- **No Python exception reaches the user:** every endpoint returns a structured error (JSON with a
  message naming the offending value), never a bare traceback (`CLAUDE.md`).
- **No fallbacks / no back-compat:** one code path; a missing tool/host is a clear error, not a
  second path (`direction/conventions.md`).
- **Bind localhost only, no auth.** Multiple read-only viewers may connect.
- **Reuse, do not reimplement:** the CSG solve, lightmap bake, texture decode, and snapshot format
  come from `preview_native`/`preview_cache`/`utexture`/`stashlib` — never a second copy.
- **Tests:** `bin/test -k <module>` scoped to the change; full suite once before merge
  (`dev/docs/rules/tests.md`). Frontend tests run under the `web/` toolchain, isolated from pytest.
- **Frontend isolation:** all JS/TS lives under `web/`; it is not imported by the Python package and
  does not affect `bin/test`.

---

## File structure (P1 whole)

Backend (`uedcli/serve/`, new package):

| File | Responsibility |
|---|---|
| `uedcli/cli/commands/serve.py` | the `serve` verb body: build the app, run uvicorn (blocks) |
| `uedcli/cli/parsers/serve.py` | `register(sub)` — the `serve` subparser (level, `--host`, `--port`) |
| `uedcli/serve/app.py` | FastAPI app factory + route registration + structured error handler |
| `uedcli/serve/errors.py` | `error_to_status(exc) -> (http_status:int, message:str)` factored out of `dispatch.py`'s domain-error arms — the single classification both the CLI and `serve` use (CLI normalizes any nonzero → exit 2) |
| `uedcli/serve/scene.py` | trunk → scene payload (wraps `preview_native.build_scene` + `preview_cache`; joins actor metadata fresh) |
| `uedcli/serve/textures.py` | base-texture atlas assembly from `build_scene`'s `texture_table` (index-keyed) |
| `uedcli/serve/watch.py` | trunk file-watcher (`watchfiles`); debounced WS "reload" broadcast |
| `uedcli/serve/photo.py` | pose → `render_frame` passthrough, pixel-identical `--native` still (Slice 2) |
| `uedcli/serve/levels.py` | enumerate the project's levels for the picker (Slice 2) |
| `uedcli/serve/snapshots.py` | content-addressed dedup snapshot store (Slice 3) |
| `uedcli/serve/diff.py` | semantic per-actor diff (Slice 3) |
| `uedcli/serve/gitread.py` | read-only git adapter: log, tree-at-ref, author (Slice 4) |

New Python deps: `fastapi`, `uvicorn`, `watchfiles`, and `httpx` (FastAPI's `TestClient` needs it).
WS uses Starlette's built-in `WebSocket` (bundled with FastAPI) — no extra lib. **Two install points,
both required (Task 1):** add them to `pyproject.toml` `dependencies` AND to `bin/_venv.sh`'s
hardcoded `_DEPS_SPEC` (the test venv installs ONLY from `_DEPS_SPEC`, never from `pyproject.toml`, so
missing this makes the Slice-1 tests fail at import, not on the intended missing symbol). Also add the
new `uedcli/serve` package to `pyproject.toml`'s static `[tool.setuptools] packages` list (tests/CLI
run via PYTHONPATH so a wheel-drop is latent, but keep it correct).

Frontend (`web/`, new):

| File | Responsibility |
|---|---|
| `web/` (Vite+React+TS scaffold) | app shell, dev-proxy to FastAPI |
| `web/src/api.ts` | typed client for the backend endpoints + WS |
| `web/src/scene/Viewport3D.tsx` | R3F perspective viewport drawing the scene payload |
| `web/src/scene/camera.ts` | faithful UnrealEd drag-fly + Alt-orbit controls |
| `web/src/panels/Inspector.tsx` | read-only property inspector |
| `web/src/panels/OrgPanel.tsx` | folder tree + label facets + find (Slice 2) |
| `web/src/audit/Timeline.tsx`, `ChangeList.tsx`, `Compare.tsx` | audit UI (Slice 3) |

---

## Slice 1 — thin end-to-end skeleton

Deliverable: `uedcli serve <level>` opens a browser showing one perspective viewport of the level,
**textured (unlit)**, with click-select, a read-only inspector, and live reload when the trunk
changes. Proves the `serve → scene → WebGL` seam end-to-end: the scene payload (geometry + base
textures) flows and draws. **Lit rendering is deferred to Slice 2** (it needs per-poly lightmap-UV
derivation + a lightmap atlas — see C2 below); the pixel-identical *lit* DRY-proof is the Slice 2
photo endpoint. Slice 1 still consumes `build_scene`'s lit payload (the lightmap tuple rides along,
just unused by the unlit draw), so no scene-source change is needed for Slice 2.

Test/validate Slice 1 against a **small or already-cached** fixture level — a cold uncached solve is
~24 s and Slice 1 has no loading UX yet (that is Slice 2), so a large level like UNATCO would look
hung on the first `/scene`. Use a tiny fixture.

### Task 1: `serve` verb + FastAPI app skeleton

**Files:** Create `uedcli/serve/app.py`, `uedcli/serve/errors.py`, `uedcli/cli/commands/serve.py`,
`uedcli/cli/parsers/serve.py`; Test `uedcli/tests/test_serve_app.py`. Modify: `uedcli/cli/main.py`
(`build_parser` — import + call `parsers.serve.register(sub)`), `uedcli/cli/dispatch.py` (a `serve`
route branch; and factor its domain-error arms into `serve/errors.py::error_to_status` so the CLI and
the app share one classification — no second copy). Add the deps at both install points (above).

**Interfaces:**
- Produces: `create_app(project, level: str, *, fault_route: bool = False) -> FastAPI` (registers
  routes; installs an exception handler that calls `error_to_status`; `fault_route=True`, set only in
  tests, mounts a `/api/_boom` route that raises a domain error — the shipped app never mounts it);
  `error_to_status(exc) -> tuple[int, str]` returning `(http_status, message)` — incl. a
  `NativePreviewError` arm (the solve's primary failure, a plain `Exception` NOT in the old chain, so
  added explicitly). The CLI maps its result to exit codes by normalizing any nonzero → exit 2 (all
  dispatch domain arms already return 2); `serve` uses the `http_status` directly. `serve` verb
  `uedcli serve <level> [--host 127.0.0.1] [--port 8765]`; it runs uvicorn **indefinitely** inside
  `dispatch()`'s guard rather than returning an exit code — blocks until Ctrl-C.

- [ ] **Step 1: Failing test** — `create_app` returns an app whose `GET /api/health` returns
  `{"status":"ok","level":<name>}`; and with `fault_route=True`, the `/api/_boom` route (raising a
  real domain error) returns HTTP 4xx JSON `{"error": "...offending value..."}`, not a 500 traceback.

```python
from uedcli.cli.errors import CommandError  # a real existing domain error (has .message)

def test_health_and_structured_errors():
    app = create_app(fake_project, "TestLevel", fault_route=True)  # fault route: tests only
    c = TestClient(app)
    assert c.get("/api/health").json()["level"] == "TestLevel"
    # /api/_boom raises CommandError("Actor not found: Foo"); handler → structured JSON, no traceback
    r = c.get("/api/_boom")
    assert r.status_code == 422 and "Foo" in r.json()["error"]
```

- [ ] **Step 2:** run it, verify FAIL (no `create_app`).
- [ ] **Step 3:** factor the **domain-error arms** of `dispatch.py`'s except-chain into
  `serve/errors.py::error_to_status(exc) -> (int, str)` and add a `NativePreviewError` arm; have
  `dispatch.py` call it so behavior is unchanged — **preserve the exact stderr message prefixes**
  (`"invalid brush geometry: …"`, `"invalid coordinate: …"`, etc.); `test_dispatch_error_boundary.py`
  pins them and only the merge-time full suite catches a drift, not the scoped `-k serve` run.
  **Leave `BrokenPipeError` in `dispatch`** — it
  returns exit 0 and reassigns `sys.stdout` (a side effect), so it does not reduce to `(int, str)`
  and is not a `serve` concern anyway. Implement `create_app` with the health route + an
  exception handler that renders `error_to_status` as `{"error": msg}` with a 4xx status. Implement
  the `serve` verb (parser `register` + command body) to build the app and run uvicorn bound to
  `--host` (default `127.0.0.1`, `--port` default `8765`), blocking. The verb first validates the
  level exists — `(config.project_maps_dir(project) / level).is_dir()` — and exits 2 "level not
  found: `<level>`" if not, rather than binding and later failing inside `build_scene` with a
  misleading "no CSG brush actors" (the no-half-answer rule).
- [ ] **Step 4:** run, verify PASS.
- [ ] **Step 5:** commit `feat: uedcli serve verb + FastAPI app skeleton`.

### Task 2: scene endpoint

**Files:** Create `uedcli/serve/scene.py`; Test `uedcli/tests/test_serve_scene.py`.

**Interfaces:**
- Consumes: `preview_native.build_scene` (the LIT path — it decodes textures into `texture_table` and
  stamps each poly's integer `tex_index` into it; `solve_world_surfaces` is the *unlit* `actor
  diagram` path and does NOT decode textures, so it is not the source here) + `preview_cache`.
  `build_scene`'s real signature is `build_scene(level, search_files, index, *, defaults, project,
  level_name)` — its **primary input is the loaded `Level` object**, not `level_name` (which is only
  the cache key). The `level photo --native` call site assembles all of these in
  `cli/commands/level.py` (~lines 732–745, the `render_shots` path): `search_files =
  config.composed_search_files(...)`, `index = resources.mover_index(...)`, `defaults =
  ClassDefaults(packages.schema_resolver(...))`, plus `project`/`level_name`. Reuse that assembly —
  do NOT grep `cli/rendering.py` (that is the `actor diagram`/`solve_world_surfaces` path and never
  calls `build_scene`).
- Produces: `build_scene_payload(project, level_name, index, defaults, search_files) -> ScenePayload`
  — loads the trunk once via `trunk.read_level_with_bodies(maps_dir/level_name)` → `(level, ranks,
  bodies, folders)` (a lock-free read, read-only-safe) and passes `level` to `build_scene`. Returns a
  frozen dataclass: `polys` (verts, base-UV frame, `tex_index` [int], `masked` [bool — the per-poly
  `PF_Masked` OR texture `bMasked` flag `build_scene` computes; gates the alpha test], `flags`,
  `lightmap` tuple-or-None [carried, unused in Slice 1]), `actors` (name, class, bbox, location,
  rotation, folder [from `folders`], labels, `order_value` [from the `ranks` map — NOT on the `Level`
  model; `doctor.py` notes the `Level` doesn't carry it]). **The payload does NOT ship texture
  bytes** — the client uses `tex_index` + the `/atlas` rects; the atlas endpoint rebuilds the table
  from the same cached `build_scene`. Route `GET /api/level/{level}/scene`.

- [ ] **Step 1: Failing test** — following the `test_preview_native.py` pattern (a `StubClassIndex`,
  `DEFAULTS = ClassDefaults(...)` over the git-tracked `uned/UED22/*.u`, a UED22 `skipif`, and a
  `SimpleNamespace(root=...)` project for the cache): a small fixture level produces a payload with
  ≥1 poly whose `tex_index` is in range, the expected actor entries (name/class/bbox/order_value
  present), and a second call is a `preview_cache` hit (assert via a solve-call spy).
- [ ] **Step 2:** FAIL. **Step 3:** implement, assembling `build_scene`'s inputs exactly as the
  `render_shots` call site in `cli/commands/level.py` (~732–745) does — `config.composed_search_files`,
  `resources.mover_index(..., project=project)`, `ClassDefaults(packages.schema_resolver(...))` —
  (NOT `cli/rendering.py`, which never calls `build_scene`), and joining actor metadata from the
  `read_level_with_bodies` result the cache does not hold. **Step 4:** PASS. **Step 5:** commit.

### Task 3: texture atlas endpoint

**Files:** Create `uedcli/serve/textures.py`; Test `uedcli/tests/test_serve_textures.py`.

**Interfaces:**
- Consumes: `build_scene`'s `texture_table` (`list[(w,h,rgb,mask)]`), obtained from the SAME cached
  solve Task 2 uses (call `build_scene` — a `preview_cache` hit — and take its `texture_table`); NOT a
  fresh `TextureResolver` decode (that would be a second decode path), and the scene payload does not
  ship the bytes.
- Produces: `build_atlas(texture_table) -> Atlas` — one RGBA image with a manifest keyed by **table
  index**: `{tex_index: {x,y,w,h}}`, one rect per table entry (mesh-skin entries included, since
  polys index into the same table). The atlas carries each entry's `rgb` + its `mask` as the alpha
  channel; **whether the alpha test is applied is decided per-poly by the payload's `masked` flag**
  (Task 2), not baked globally — a non-masked poly using a texture whose `mask` marks index-0 texels
  must not render holes. Route `GET /api/level/{level}/atlas` (RGBA bytes / PNG + the index-keyed
  manifest). The client maps a poly's `tex_index` → rect directly.

- [ ] Test: the atlas manifest has one rect per `texture_table` entry, keyed by index; every poly's
  `tex_index` in the scene resolves to a rect; the alpha channel carries each entry's `mask`. (The
  per-poly `masked` gate is exercised in Task 6's material.) FAIL → implement → PASS → commit.

### Task 4: trunk watcher + WebSocket live-reload

**Files:** Create `uedcli/serve/watch.py`; Test `uedcli/tests/test_serve_watch.py`.

**Interfaces:**
- Produces: `TrunkWatcher(level_dir, on_change)` — debounced (default 400 ms) coalescing watcher;
  WS route `GET /ws` broadcasting `{"type":"reload","level":...}` on a settled change.

- [ ] Test: N rapid writes within the debounce window fire `on_change` exactly once, with the
  post-burst state. FAIL → implement (a filesystem watcher + debounce timer) → PASS → commit.

### Task 5: frontend scaffold + typed API client

**Files:** Create `web/` (Vite React-TS), `web/src/api.ts`. Test `web/src/api.test.ts` (vitest).

**Interfaces:**
- Produces: `fetchScene(level)`, `fetchAtlas(level)`, `openReloadSocket(onReload)` typed against the
  backend payloads. Vite dev server proxies `/api` + `/ws` to uvicorn.

- [ ] Boot the scaffold; a vitest test mocks `/api/level/x/scene` and asserts `fetchScene` returns
  the typed payload. Commit `chore: web scaffold + typed api client`.

### Task 6: perspective viewport with faithful camera

**Files:** Create `web/src/scene/Viewport3D.tsx`, `web/src/scene/camera.ts`. Test
`web/src/scene/camera.test.ts`.

**Interfaces:**
- Consumes: `ScenePayload`, `Atlas`.
- Produces: `<Viewport3D scene atlas />` drawing **textured, unlit** polys — build a `BufferGeometry`
  per poly (or a merged mesh) with the base-UV set mapped through the atlas rect for its `tex_index`;
  a single `MeshBasicMaterial` sampling the atlas (unlit = `MeshBasicMaterial`, no lights, no
  lightmap). Apply the atlas alpha test **only for polys whose `masked` flag is set**, via a
  **two-group material split** (one masked material with `alphaTest`, one plain), so non-masked polys
  never key out on index-0 texels. The `lightmap`
  field is ignored in Slice 1. Camera controller: LMB dolly+turn / RMB look
  / LMB+RMB pan / scroll zoom / Alt-drag orbit-around-selection.

- [ ] Unit-test the camera controller's transform math (a right-drag yaws by the expected angle; a
  left-drag dollies along forward; Alt-drag orbits about the pivot) against known inputs. Then wire
  the unlit textured mesh from the payload (base-UV × atlas rect). Verify by exercising the app per
  `building-features.md` (load the fixture level, confirm it renders textured and navigates). Commit.

### Task 7: selection + read-only inspector

**Files:** Create `web/src/panels/Inspector.tsx`, selection state in `web/src/scene/`. Test
`web/src/panels/Inspector.test.ts`.

**Interfaces:**
- Produces: click-to-select (raycast; LMB tap below the camera-fly drag threshold); `<Inspector
  actor />` rendering name/class/transform/folder/labels/order_value + raw props (collapsible).

- [ ] Test: selecting an actor id sets selection and the inspector renders its property rows from a
  fixture actor. Verify the tap-vs-drag threshold gates selection vs camera. Commit.

### Task 8: live-reload wiring (keep-stale-until-ready)

**Files:** Modify `web/src/api.ts` consumer + app root. Test `web/src/reload.test.ts`.

**Interfaces:**
- Produces: on a WS `reload`, refetch the scene and swap it in only once ready (the prior scene stays
  visible meanwhile).

- [ ] Test: a `reload` event triggers a scene refetch; the displayed scene is replaced only after the
  new payload resolves (assert no blank intermediate). Commit.

**Slice 1 exit:** `uedcli serve <fixture-level>` renders + navigates + selects + inspects, and an
external `actor` edit to the trunk live-reloads the viewport. One subagent review; then advance.

---

## Slice 2 — full viewer (quad, shading, ortho, org panel, level picker)

Milestone outline (own detailed plan when scheduled):

- Quad layout (Top/Front/Side ortho + Perspective) + double-click maximize; shared selection.
- Ortho viewports: 2D projection of the scene, drag-pan + both-drag/scroll zoom, marquee select,
  adaptive Unreal-Units grid + cursor coordinate readout.
- Shading modes per pane: textured+lit / unlit / flat / wireframe (`1`–`4`); the instant cold-open
  raw-brush wireframe (drawn from trunk brush geometry with no solve).
- **Lit rendering (deferred from Slice 1, C2):** per poly, derive a second (lightmap) UV set from its
  `lightmap` patch frame (`origin`/`u_step`/`v_step`/`u_size`/`v_size`), pack the per-poly lightmap
  RGB patches into a **lightmap atlas** (parallel to the base atlas), and multiply base×lightmap in
  the material. This is what turns the already-carried `lightmap` field into the "textured+lit" mode.
- **Photo endpoint (`uedcli/serve/photo.py`, deferred from Slice 1, I3):** a pose → `render_frame`
  passthrough returning a pixel-identical `--native` still (`render_frame` reached via
  `preview_native.render_shots`). This is the pixel-level DRY proof the live viewport approximates.
- Non-brush actor meshes (via the `--native` mesh path) with class-coloured box/sprite fallback.
- Organization panel: folder tree + label filter facets + find box (mirrors `actor find`), incl.
  "(no folder)"/"(no label)". Level enumeration endpoint (`uedcli/serve/levels.py`) + in-GUI picker.
- Textures-first delivery; theme (dark-first + light toggle) + the semantic-colour tokens.

## Slice 3 — audit (snapshots, timeline, diff, compare viz)

- `uedcli/serve/snapshots.py`: content-addressed dedup store (hash-keyed compressed blobs +
  per-snapshot manifest) under `.uedcli/`; the debounced watcher (Task 4) takes one snapshot per
  settled burst; disk-budget LRU prune. (`safety.md` GUI exemption applies.)
- `uedcli/serve/diff.py`: per-actor semantic diff between two states — categories added / removed /
  prop-changed(incl. moved) / poly-changed(incl. retextured) / order / folder / label / `other`
  catch-all; invariant: 100% of the text delta maps to an entry (test-enforced).
- Timeline (snapshot lane) + A/B pickers; change list grouped by category (folder/actor toggles);
  compare viz auto by change type (onion / flip / split), click → auto-frame union bbox, next/prev.

## Slice 4 — read-only git layer

- `uedcli/serve/gitread.py`: `git log`, tree-at-ref, author attribution — read-only; absent cleanly
  when no repo.
- Timeline commit lane + content-hash cross-link to snapshots ("committed as `<sha>`"); diff against
  a commit reads its trees from git on demand (works with no snapshot for that commit).
- NEVER drives git (no branch/worktree/merge) — owner ruling.

---

## Open (P1, undecided — resolve during planning of the owning slice)

Empty/error/loading state specifics (no level, solve failure, no snapshots yet, no git, missing
texture) and inspector niceties (jump to referenced actor via `Base`/`Owner`, texture thumbnails,
copy value). Not blockers for Slice 1.

## Verification (pre-merge, per `building-features.md` + `tests.md`)

- Python: the repo's formatter/linter/type-checker + scoped `bin/test -k serve` (full suite once).
- Frontend (under `web/`, isolated from pytest): `tsc --noEmit`, `eslint`, and `vitest run`. These
  are part of the pre-merge "check it" step for any task that touches `web/`.
- Exercise the app (`building-features.md` step): `uedcli serve <fixture>` renders + navigates +
  selects + inspects + live-reloads.

## Self-review

- Spec coverage: every spec "settled details" area maps to a slice (stack/layout/camera/selection →
  S1–S2; textured render → S1, **lit render → S2**, other shading/actors → S2; loading/perf →
  S1–S2; structure/nav → S2; **photo endpoint → S2**; audit/snapshots/timeline → S3–S4;
  look&feel → S2). ✔
- Placeholders: Slice 1 tasks carry concrete tests/interfaces; Slices 2–4 are explicitly outlines
  pending their own plans. ✔
- Type consistency: `ScenePayload` (with `texture_table`, per-poly `tex_index`) and the index-keyed
  `Atlas` produced in Tasks 2–3 are consumed by name in Tasks 5–6. ✔
