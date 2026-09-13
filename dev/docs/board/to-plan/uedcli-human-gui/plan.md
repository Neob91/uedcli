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
| `uedcli/cli/commands/serve.py` | the `serve` verb: arg parse (level, host/port), launch uvicorn |
| `uedcli/serve/app.py` | FastAPI app factory + route registration + structured error handler |
| `uedcli/serve/scene.py` | trunk → scene payload (wraps `preview_native` solve + `preview_cache`; assembles actor metadata) |
| `uedcli/serve/textures.py` | texture atlas assembly from `utexture` decode |
| `uedcli/serve/photo.py` | pose → `render_frame` passthrough (pixel-identical `--native` still) |
| `uedcli/serve/watch.py` | trunk file-watcher; debounced WS "reload" broadcast |
| `uedcli/serve/levels.py` | enumerate the project's levels for the picker |
| `uedcli/serve/snapshots.py` | content-addressed dedup snapshot store (Slice 3) |
| `uedcli/serve/diff.py` | semantic per-actor diff (Slice 3) |
| `uedcli/serve/gitread.py` | read-only git adapter: log, tree-at-ref, author (Slice 4) |

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
textured+lit, with click-select, a read-only inspector, and live reload when the trunk changes.
Proves the `serve → scene → WebGL` DRY seam.

### Task 1: `serve` verb + FastAPI app skeleton

**Files:** Create `uedcli/serve/app.py`, `uedcli/cli/commands/serve.py`; Test
`uedcli/tests/test_serve_app.py`. Modify the CLI dispatch to register `serve`.

**Interfaces:**
- Produces: `create_app(project, level: str) -> FastAPI` (registers routes, a JSON error handler);
  `serve` verb `uedcli serve <level> [--host 127.0.0.1] [--port N]`.

- [ ] **Step 1: Failing test** — `create_app` returns an app whose `GET /api/health` returns
  `{"status":"ok","level":<name>}`; and an endpoint raising a `LookupError` returns HTTP 4xx JSON
  `{"error": "...offending value..."}`, not a 500 traceback.

```python
def test_health_and_structured_errors():
    app = create_app(fake_project, "TestLevel")
    c = TestClient(app)
    assert c.get("/api/health").json()["level"] == "TestLevel"
    # a route wired to raise a domain error returns structured JSON, no traceback
    r = c.get("/api/_boom")  # test-only route raising ActorNotFound("Foo")
    assert r.status_code == 422 and "Foo" in r.json()["error"]
```

- [ ] **Step 2:** run it, verify FAIL (no `create_app`).
- [ ] **Step 3:** implement `create_app` with the health route and an exception handler mapping the
  library's error types to structured JSON (reuse the CLI's existing error taxonomy). Implement the
  `serve` verb to build the app and run uvicorn bound to `--host` (default `127.0.0.1`).
- [ ] **Step 4:** run, verify PASS.
- [ ] **Step 5:** commit `feat: uedcli serve verb + FastAPI app skeleton`.

### Task 2: scene endpoint

**Files:** Create `uedcli/serve/scene.py`; Test `uedcli/tests/test_serve_scene.py`.

**Interfaces:**
- Consumes: `preview_native.build_scene` / `solve_world_surfaces`, `preview_cache`.
- Produces: `build_scene_payload(project, level) -> ScenePayload` (frozen dataclass): `polys`
  (verts, uv frame, texture index, flags, lightmap), `actors` (name, class, bbox, location, rotation,
  folder, labels, order_value), `textures` (atlas manifest: index → {w,h,name}). Route `GET
  /api/level/{level}/scene`.

- [ ] **Step 1: Failing test** — a small fixture level produces a payload with ≥1 poly and the
  expected actor entries (name/class/bbox present); a second call is a `preview_cache` hit (no
  re-solve — assert via a solve-call spy/timing).
- [ ] **Step 2:** FAIL. **Step 3:** implement, reusing the `preview_native` solve and joining actor
  metadata (from `model`/`t3dtree`) that the cache does not hold. **Step 4:** PASS. **Step 5:** commit.

### Task 3: texture atlas endpoint

**Files:** Create `uedcli/serve/textures.py`; Test `uedcli/tests/test_serve_textures.py`.

**Interfaces:**
- Consumes: `utexture.TextureResolver` / `DecodedTexture` (`rgb`+`mask`).
- Produces: `build_atlas(project, level) -> Atlas` (RGBA bytes + `{name → {x,y,w,h}}` rects). Route
  `GET /api/level/{level}/atlas` (binary RGBA + a JSON manifest, or a PNG).

- [ ] Test: a level's textures decode and pack into an atlas whose manifest covers every texture the
  scene references; a masked texture's alpha follows its `mask`. FAIL → implement → PASS → commit.

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
- Produces: `<Viewport3D scene atlas />` drawing textured+lit polys; camera controller implementing
  LMB dolly+turn / RMB look / LMB+RMB pan / scroll zoom / Alt-drag orbit-around-selection.

- [ ] Unit-test the camera controller's transform math (a right-drag yaws by the expected angle; a
  left-drag dollies along forward; Alt-drag orbits about the pivot) against known inputs. Then wire
  the R3F mesh from the payload. Verify by exercising the app per `building-features.md` (load the
  fixture level, confirm it renders and navigates). Commit.

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

## Self-review

- Spec coverage: every spec "settled details" area maps to a slice (stack/layout/camera/selection →
  S1–S2; shading/actors → S2; loading/perf → S1–S2; structure/nav → S2; audit/snapshots/timeline →
  S3–S4; look&feel → S2). ✔
- Placeholders: Slice 1 tasks carry concrete tests/interfaces; Slices 2–4 are explicitly outlines
  pending their own plans. ✔
- Type consistency: `ScenePayload`/`Atlas` produced in Tasks 2–3 are consumed by name in Tasks 5–6. ✔
