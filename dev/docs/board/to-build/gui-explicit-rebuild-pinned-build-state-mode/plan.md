# Plan — GUI explicit rebuild (pinned build state, Load, Rebuild, mode gating)

Plans spec sections 1–4 only (`spec.md`): the persisted/in-memory build pin, the Load action, the
Rebuild action, and render-mode gating/bootstrap. Section 5 (fullbright overlay) is P2-only per the
spec — not planned here.

> **For agentic workers:** use `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement task-by-task. Follow `dev/docs/rules/building-features.md`
> (worktree, verify, review, squash-merge).

**Spec:** `dev/docs/board/to-spec/gui-explicit-rebuild-pinned-build-state-mode/spec.md` — read it in
full before building; this plan argues from its CURRENT text (post both review passes), not its
revision history. Also read `dev/docs/board/to-spec/uedcli-serve-share-one-in-process-scene-cache/
spec.md` **in full, including its "Generation guard" design section** — this plan builds ON TOP of
that spec's `_LoadedTrunk`/`_BuiltGeometry` two-slot mechanism, assumed already merged to master by
the time this plan is built, and Task 2 below makes a real, deliberate change to that mechanism's
geometry-access half (removes its auto-build path). See "Sequencing / pre-flight check" below —
**do not skip it**.

## Sequencing / pre-flight check (read before Task 1)

**Corrected twice during review (2026-09-14):**

**First correction** — this plan's first draft was written against a stale checkout of
`uedcli/preview_native.py`/`uedcli/serve/scene.py` (the main checkout, which lacks today's
uncommitted worktree changes — brush picking, sprite rendering, `bHiddenEd` filtering). Re-verified
directly against the actual current worktree files:

**Confirmed to ALREADY EXIST, today, as real working code** (not merely drafted in the scene-cache
spec — the first draft wrongly treated these as not-yet-built):
- `preview_native.build_scene(level, search_files, index, *, defaults, project=None,
  level_name=None, visibility: Literal["gameplay","editor"]="gameplay") -> tuple[list, list, list]`
  — returns **`(polys, texture_table, actor_names_by_poly)`**, a 3-tuple. The third element is
  exactly the "owner" join needed for click-to-select: `owners` IS `actor_names_by_poly`, one entry
  per render poly, `None` for a poly joined to no source actor. `serve/scene.py::build_scene_payload`
  already zips it onto `ScenePoly.owner` today. **No open question remains here.**
- `preview_native.resolve_actor_sprites`, `serve/scene.py`'s `ActorSprite`, `BrushHighlight`,
  `SceneActor.brush`/`SceneActor.sprite`, `ScenePoly.owner`, and `visibility="editor"` — all real,
  already wired into `/scene`, `/atlas`, `/lightmap` in the current `serve/app.py`. `BrushHighlight`
  in particular matters to Task 2 below: it's a brush actor's own AUTHORED pre-CSG shape, already
  carried on every `SceneActor` regardless of whether solved geometry exists — this is what lets
  wireframe mode render with **zero dependency on `_BuiltGeometry`** (see Task 2).
- `preview_cache.load_scene`/`store_scene` already store/return the 3-tuple
  `(polys, texture_table, actor_names_by_poly)` (`_CACHE_VERSION` bumped to 2 for this shape change).

**Confirmed to still NOT exist**, in this same current worktree: `_LoadedTrunk`, `_BuiltGeometry`,
`_trunk_ref`, `_geometry_ref`, `_get_trunk`, `_get_geometry` appear nowhere in `serve/app.py` — the
scene-cache spec's two-slot mechanism genuinely has not been built yet, in the worktree or the main
checkout. Before starting Task 1, the executor MUST re-read whatever `uedcli/serve/app.py`/`scene.py`
look like AT THAT TIME (this mechanism is being built by a separate, earlier effort) and confirm:

- The exact field names/types on `_LoadedTrunk` and `_BuiltGeometry` (this plan assumes the spec's
  literal draft: `_LoadedTrunk{level, ranks, folders, sprite_table, actor_sprites}`,
  `_BuiltGeometry{geom_hash, light_hash, polys, texture_table, owners}` — given `owners` is now
  confirmed as `build_scene`'s own `actor_names_by_poly`, expect `_BuiltGeometry.owners` to just be
  that list carried through unchanged; confirm the merged code actually does this rather than
  re-deriving it differently).
- The exact signatures of `_get_trunk()` / `_get_geometry()` (as merged) and whether they're free
  functions in `app.py`'s `create_app` closure (as drafted) or moved to their own module.
- **How the (geom_hash, light_hash) pair reaches `_BuiltGeometry` — confirmed by reading
  `build_scene`'s actual body, not guessed:** `build_scene` computes
  `geom_hash, light_hash = _scene_hashes(level, {n for n, *_ in lights})` locally (then suffixes
  `geom_hash += "e" if visibility == "editor" else "g"` before ever touching `preview_cache`), but
  **never returns either value** — both its return points (the early cache-hit `return cached_scene`
  and the final `return polys, texture_table, actor_names_by_poly`) omit them even though both are
  already in local scope at that point. `_scene_hashes` itself is module-private and additionally
  needs `gather_lights(level, defaults=defaults)`'s output to call at all, so a caller outside
  `build_scene` can't cheaply recompute the pair without duplicating that light-gathering step too.
  **Smallest fix:** extend `build_scene`'s return to a 5-tuple —
  `return polys, texture_table, actor_names_by_poly, geom_hash, light_hash` at the final return, and
  the equivalent at the cache-hit early return (`cached_scene` is the stored 3-tuple; splice the
  already-locally-known `geom_hash, light_hash` onto it there too) — no new computation, just
  surfacing values already computed. When `project`/`level_name` are absent (`cache=False`), both
  come back `None`, matching the existing `geom_hash = light_hash = None` initialization. **Treat the
  returned `geom_hash` as opaque** — it carries the visibility-mode suffix baked in; whoever writes
  it into the in-memory pin (Task 6) or later the on-disk pointer (P2/Save) must round-trip that
  exact string, never recompute or strip the suffix independently. This return-shape change is
  itself a small piece of production code Task 6 needs — or, if the merged scene-cache code already
  made an equivalent change for `_get_geometry()`'s own reasons, Task 6 should reuse that instead of
  making a second one — confirm which is true against the actually-merged code first.

**Second correction (this revision)** — a review of the corrected plan found a real, build-blocking
architectural gap in how it wired the geometry slot into `/scene`/`/atlas`/`/lightmap`, described in
full in Task 2 below. Read the sibling spec's **"Generation guard"** design section in full before
building Task 2 or Task 6 — it is quoted/referenced extensively there and this plan's Rebuild action
must reuse its discipline, not just its data structure.

If any of the above turns out materially different from this plan's assumptions, adjust the affected
task's implementation accordingly; the task's *behavior* (what test passes) should not need to
change, only how it's wired to the merged slot mechanism.

## Global constraints (carried over, unchanged)

- No Python exception reaches the user; every new route returns structured JSON errors via the
  existing `error_to_status` handler.
- No back-compat shims — one code path (`direction/conventions.md`).
- Read-only invariant for P1 still holds: **Rebuild is not a trunk write.** It only recomputes and
  re-pins solved geometry from the current in-memory trunk view; it never touches the maps directory.
  The only new disk write in this plan's scope is none — the on-disk pointer file is Save-owned (P2,
  doesn't exist yet), so this plan's code only ever *reads* `.uedcli/build/<level>/current.json`,
  never writes it (see Task 1).
- **Rebuild is the ONLY code path in this plan (or in the merged scene-cache mechanism, after Task 2
  lands) that ever calls `build_scene()`.** No route may trigger a CSG/lighting solve as a side
  effect of being fetched — this is the whole point of the spec (§4) and the specific gap Task 2
  exists to close. `/scene`, `/atlas`, `/lightmap` read whatever is already pinned (possibly
  nothing) and never solve on demand.
- Tests: `bin/test -k serve` scoped to the change; full suite once before merge.

## File structure delta

| File | Change |
|---|---|
| `uedcli/serve/build_pin.py` | **new** — on-disk pointer read + resolve-against-`preview_cache`-with-degrade (Task 1) |
| `uedcli/serve/app.py` | **modify** — removes the auto-build geometry path (Task 2); watcher callback stops clearing slots (Task 3); adds `/load`, `/rebuild`, `/status` routes (Tasks 4–6) |
| `uedcli/tests/test_serve_build_pin.py` | **new** — Task 1 unit tests |
| `uedcli/tests/test_serve_app.py` | **modify** — extended for the geometry-access split and the new routes (Tasks 2–6) |
| `uedcli/tests/test_serve_load_rebuild.py` | **new** — Task 7's cross-cutting independent-axes tests |

No frontend (`web/`) changes in this plan's scope — the render-mode picker UI itself is Slice 2's own
build (spec non-goals); this plan only adds the backend gating *signal* it will eventually read.

---

## Task 1: on-disk pointer store — format, location, read + degrade

**Files:** Create `uedcli/serve/build_pin.py`. Test `uedcli/tests/test_serve_build_pin.py`.

**Interfaces:**
- `pointer_path(project, level_name: str) -> Path` — `config.state_subdir(project.root, "build",
  create=False) / level_name / "current.json"`. Read-only helper; does **not** create the `build`
  subdir (nothing in this plan's scope ever writes it — see Global constraints).
- `load_pointer(project, level_name: str) -> tuple[str, str] | None` — reads and JSON-parses the
  pointer file; returns `(geom_hash, light_hash)` or `None` if the file is absent. A malformed/
  corrupt file (partial write, hand-edited garbage) also returns `None` rather than raising — same
  "a cache/pointer miss is always survivable, never an error" posture `preview_cache.py`'s own
  `_load` uses for corrupt `marshal` blobs (broad-except there is deliberate and documented; this
  mirrors it for JSON). **Flagged open question:** the spec doesn't explicitly rule on corrupt-file
  handling — this is this plan's own inferred-consistent choice, not a literal spec requirement;
  confirm it's acceptable before relying on it in Task 1's test.
- `resolve_pin(project, level_name: str, pin: tuple[str, str]) -> tuple | None` — given a
  `(geom_hash, light_hash)` pair (from `load_pointer` or an already-held in-memory pin), calls
  `preview_cache.load_scene(project, level_name, geom_hash, light_hash)` and returns its result
  (the cached `(polys, texture_table, actor_names_by_poly)` 3-tuple — confirmed against the real
  current `preview_cache.load_scene`/`store_scene`, `_CACHE_VERSION` 2) or `None` on a miss (the
  eviction case, spec §1's "Eviction caveat"). Does not itself decide what "degraded" means to a
  caller (that's Task 2/4's job) — it's a pure lookup wrapper, kept separate so Task 1's tests can
  exercise the miss path without spinning up the whole app.

- [ ] **Step 1: failing tests** —
  - `load_pointer` returns `None` when no `.uedcli/build/<level>/current.json` exists.
  - `load_pointer` returns `(geom_hash, light_hash)` for a hand-written valid JSON file (test writes
    it directly via `tmp_path`, matching the format `{"geom_hash": "...", "light_hash": "..."}`
    from spec §1).
  - `load_pointer` returns `None` for a hand-written corrupt/truncated file (not an exception).
  - `resolve_pin` returns `None` when the pointed-to hash pair has no `preview_cache` entry (a
    pointer naming hashes that were never stored, or evicted) — spec's eviction caveat, unit-level.
  - `resolve_pin` returns the cached payload when `preview_cache.store_scene` was called first with
    the same project/level/hashes (a real hit, using `preview_cache`'s own test fixtures/pattern).
- [ ] **Step 2:** run, verify FAIL (no `build_pin.py`).
- [ ] **Step 3:** implement `build_pin.py` per the interfaces above.
- [ ] **Step 4:** run, verify PASS.
- [ ] **Step 5:** commit `feat: on-disk build-pin pointer read + resolve-with-degrade`.

---

## Task 2: split geometry access — remove the auto-build path, add read-only + build-and-publish

**This is the task that fixes a review-found, build-blocking gap** (found against this plan's
second draft): as originally planned, `/scene`/`/atlas`/`/lightmap` would call the sibling
scene-cache mechanism's `_get_geometry()`, which **unconditionally auto-builds** (calls
`build_scene()`) whenever `_geometry_ref[0] is None`. That's correct for the sibling spec's OWN
scope (P1, before this spec's triggers exist — it's just sharing work that already happens
automatically today). But left wired that way, the very first GUI page load — which always fires
`/scene` — would still silently run a full CSG+lighting solve regardless of whether anyone ever
clicked Rebuild, defeating this spec's central goal (§4: cold-open "stays wireframe-only until the
user explicitly Rebuilds"). This task is the concrete mechanics of spec §0's "supersedes the
trigger": it changes the scene-cache mechanism's geometry half so that **only Rebuild can ever
trigger a build.**

**Files:** Modify `uedcli/serve/app.py`, `uedcli/serve/scene.py` (the `/scene` route's response
assembly needs a "no geometry yet" path). Test: extend `uedcli/tests/test_serve_app.py`.

**Design decision (stated explicitly, per the review request): `_get_geometry()` is REMOVED, not
kept alongside a new pair of functions.** This spec's whole point is "nothing auto-builds"; once
Task 2 lands, `_get_geometry()` has no remaining caller and no remaining reason to exist — keeping it
around unused (or worse, still reachable from somewhere) is exactly the kind of latent footgun that
caused this gap in the first place. It is replaced by exactly two operations:

- `_read_geometry() -> _BuiltGeometry | None` — `return _geometry_ref[0]`. Pure read, **never**
  calls `build_scene()`, needs no lock (a single list-index read of a cell only ever replaced by a
  single atomic assignment — same "single-reference-swap is atomic" reasoning the sibling spec
  already relies on for the slot itself). Called by `/scene`, `/atlas`, `/lightmap`, and by
  `/status` (Task 4).
- `_build_and_publish_geometry() -> _BuiltGeometry` — the actual `build_scene()`-invoking logic,
  extracted from the sibling's `_get_geometry()` sketch **minus its "already cached? return early"
  short-circuit** (Rebuild always wants to actually run the solve pipeline — spec §3.3, "never
  accumulates," meaning it unconditionally re-derives, even though `build_scene`'s own internal
  `preview_cache` lookup makes a same-hash repeat a cheap cache hit rather than genuinely re-solving
  — this is what satisfies spec test #4). Still takes `solve_lock` around the whole build+publish
  critical section (serializes concurrent callers against `preview_cache`'s write, same as today).
  Still uses `_get_trunk()`'s `level` as `build_scene`'s input (unchanged from the sibling's design —
  `_get_trunk()` itself is untouched by this task; its own automatic-lazy-build behavior is
  *intentional* here, unlike geometry's, and stays exactly as the sibling spec drafted it). **Called
  ONLY by the Rebuild route (Task 6)** — no other code path may call it.

  **Generation-guard discipline, reused (not reinvented) from the sibling spec — re-read its
  "Generation guard" section before writing this):** capture `gen_before = _generation[0]` before
  starting the (possibly slow) `build_scene()` call; after it returns, check `_generation[0] ==
  gen_before` before publishing to `_geometry_ref[0]`. If generation moved during the solve, discard
  the built result and retry (recurse into `_build_and_publish_geometry()` again, exactly the
  sibling's own retry-via-recursion pattern) rather than publish something computed against a state
  that's since been superseded. **What still bumps `_generation[0]` in this spec's world:** the
  watcher's settle callback (Task 3) keeps bumping it even though — per spec §0 — it no longer
  clears either slot; the counter is simply repurposed from "guard against a stale *automatic*
  build" to "guard against a stale *Rebuild* publish that was mid-flight when something changed."
  **Flagged design choice, not literally spec-mandated** (see Open Questions): this plan does NOT
  additionally bump generation from the Load route (Task 5) — only the watcher does. A geometry
  build racing a concurrent Load is a real but narrower scenario; see Open Questions for why this
  plan doesn't chase it further right now.

**Route changes — the "no geometry yet" response, exercising `BrushHighlight` instead of solved
polys:**
- `/scene`: calls `_get_trunk()` (unchanged) and `_read_geometry()` (new). Builds `actors` from the
  trunk exactly as today (each `SceneActor.brush` already carries the AUTHORED pre-CSG shape,
  confirmed real/existing code per the pre-flight check — this is what lets a client draw wireframe
  with zero dependency on solved geometry). When `_read_geometry()` returns `None`: `polys: []`
  (there is no solved geometry — genuinely empty, not an error) and a new top-level
  `"geometry_pinned": false` field so a client reading `/scene` alone (without a second `/status`
  fetch) can already tell "wireframe-only, this isn't a levelwith-zero-brushes." When
  `_read_geometry()` returns a value: `polys` from it, `"geometry_pinned": true`.
- `/atlas`: when `_read_geometry()` returns `None`, build the atlas from **only** `trunk.sprite_table`
  (sprites are Load-owned, unaffected by whether geometry is pinned — a point actor's icon should
  still show in wireframe mode) — skip `geometry.texture_table` entirely rather than erroring or
  returning an empty atlas. When geometry IS pinned, atlas = `geometry.texture_table +
  trunk.sprite_table` (unchanged from today).
- `/lightmap`: when `_read_geometry()` returns `None`, there are no lit polys to pack — return a
  degenerate/empty response (`{"width": 0, "height": 0, "intensity": ..., "manifest": {},
  "png_base64": ""}` or equivalent) rather than calling `build_lightmap_atlas([])` blind. **Flagged
  open point:** confirm whether `build_lightmap_atlas` already handles an empty poly list gracefully
  (in which case just call it with `[]`) or needs an explicit early-return added here — check its
  actual current implementation at build time, don't assume either way.

- [ ] **Step 1: failing tests — this is the test the review specifically asked for, the one that
  would have caught the original gap:**
  - `GET /scene` on a freshly created app (no on-disk pointer ever written, `/rebuild` never called)
    returns `{"polys": [], "geometry_pinned": false, "actors": [...]}` (actors still populated, each
    carrying its `brush`/`sprite` fields) — **and a spy on `build_scene` records ZERO calls.** This
    is the review's exact reproduction case.
  - `GET /atlas` cold (same fresh-app conditions) returns 200 with a valid atlas built from only the
    trunk's sprite table, and the SAME `build_scene` spy records zero calls.
  - `GET /lightmap` cold returns a valid degenerate/empty response, zero `build_scene` calls.
  - `_read_geometry()` called directly (unit-level) never calls `build_scene` regardless of
    `_geometry_ref[0]`'s state (both when `None` and when pre-populated via a test fixture).
  - `_build_and_publish_geometry()` called directly populates `_geometry_ref[0]` and DOES call
    `build_scene` (contrast case, confirming the split isn't just "nothing ever builds").
- [ ] **Step 2:** run, verify FAIL against the plan's PRE-Task-2 wiring (i.e. write this test before
  removing `_get_geometry()`'s call sites, to prove it actually catches the gap — then implement).
- [ ] **Step 3:** implement: delete `_get_geometry()` and every call site; add `_read_geometry()`/
  `_build_and_publish_geometry()`; rewire the three routes per the "Route changes" above.
- [ ] **Step 4:** run, verify PASS.
- [ ] **Step 5:** commit `fix: /scene, /atlas, /lightmap no longer auto-build geometry — Rebuild is
  the only build trigger`. Call out in the commit body that this removes `_get_geometry()` entirely
  and is a deliberate behavior change to the sibling scene-cache mechanism, not an addition alongside
  it.

---

## Task 3: watcher stops clearing slots, flips a "changes available" flag instead

**Files:** Modify `uedcli/serve/app.py`. Test: extend `uedcli/tests/test_serve_app.py`.

Per spec §0: the watcher's settle callback (currently, per the scene-cache spec's own P1 scope,
clearing both `_trunk_ref[0]` and `_geometry_ref[0]` before broadcasting a WS reload) must instead
leave both slots untouched and only flip a signal. This task changes ONLY that callback's body — it
does not touch `_LoadedTrunk`/`_BuiltGeometry`'s shape or the double-checked-locking mechanism (per
spec §0), and it does NOT remove the generation bump (Task 2 above repurposes it, doesn't retire it).

**Interfaces:**
- `_changes_available: list[bool] = [False]` — a single-cell flag in `create_app`'s closure, same
  convention as `_trunk_ref`/`_geometry_ref`/`_generation`.
- The watcher's `on_change` callback (currently `_broadcast_reload` per the merged scene-cache code —
  confirm its exact current name/body against merged `app.py` first) is changed to: **bump
  `_generation[0]`** (unchanged from the sibling spec — still needed, now for Task 2's Rebuild-guard
  purpose rather than an auto-build guard), set `_changes_available[0] = True`, then broadcast a WS
  message. **The broadcast message's `type` changes from `"reload"` to `"changes_available"`** (the
  client's job, Slice 2+, is to show a banner/badge, not auto-refetch — spec §2, superseding the old
  auto-reload). Existing `test_serve_ws_reload.py`/`test_serve_app.py` assertions on the `"reload"`
  message type will need updating to match — **not a silent behavior regression**, call it out in
  the commit message since it changes an already-tested wire format.
- Both `_trunk_ref[0]` and `_geometry_ref[0]` are left as-is by this callback — no clearing.

- [ ] **Step 1: failing test** — a trunk change (simulate via calling the watcher's `on_change`
  directly, matching `test_serve_watch.py`'s `TrunkWatcher` test style, or by driving the real
  watcher against `tmp_path` per `test_serve_app.py`'s existing fixtures) leaves an already-populated
  `_trunk_ref[0]`/`_geometry_ref[0]` **unchanged** (same object identity, not just equal value — the
  point is nothing was cleared/rebuilt), bumps `_generation[0]` by exactly 1, and sets
  `_changes_available[0]` to `True` — exposed on `app.state` for the test the way
  `app.state.connections`/`app.state.broadcast_reload` already are.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: watcher signals changes-available instead of auto-clearing serve
  cache slots`.

---

## Task 4: status endpoint — changes-available + mode-gating signal

**Files:** Modify `uedcli/serve/app.py`. Test: extend `uedcli/tests/test_serve_app.py`.

Built before Load/Rebuild (Tasks 5–6) so those tasks' tests have something to assert against. Per
spec's own "What is open" list, the exact route shape is a planning-time choice (not a spec fork) —
this plan folds both signals (Load's "changes available" and Rebuild's mode-gating) into one route
rather than two, since they're cheap, closely related, and a client showing either banner needs both
at once anyway. **Flagged as this plan's design choice, not a spec mandate — revisit if the
executing agent finds a reason the two should be separate.** Note this signal is now redundant with
`/scene`'s own `geometry_pinned` field (Task 2) for the gating half specifically — kept as a
separate route anyway since `changes_available` has no natural home on `/scene` (it's a Load-axis
concern, not a geometry-axis one) and a client may want either signal without fetching the whole
scene payload.

**Interfaces:**
- `GET /api/level/{level_name}/status` → `{"changes_available": bool, "geometry_pinned": bool,
  "build_status": "built" | "no_build" | "evicted"}`.
  - `changes_available` = current `_changes_available[0]`.
  - `geometry_pinned` = `_read_geometry() is not None` — the literal mode-gate condition from spec
    §4 ("no in-memory geometry pin currently held"), now expressed through Task 2's read-only
    accessor rather than a raw `_geometry_ref[0]` check (same value, correct call site).
  - `build_status`: `"built"` if `geometry_pinned`; `"no_build"` if never populated and no on-disk
    pointer exists (or none was resolvable); `"evicted"` if an on-disk pointer exists but the last
    bootstrap attempt (Task 5) found no matching `preview_cache` entry — the spec's explicit "clear
    status" requirement for the degraded case (§1, §4). This means the status route needs to
    remember *why* the pin is empty, not just that it is — a small addition beyond a pure
    `_read_geometry() is not None` check; Task 5 sets/clears an internal
    `_build_status: list[str] = ["no_build"]` cell alongside populating/leaving-empty
    `_geometry_ref[0]`, and this route just reads it back (`"built"` is derived, not stored
    separately, to avoid the two disagreeing).

- [ ] **Step 1: failing test** — a freshly created app (no on-disk pointer, no prior Rebuild) reports
  `{"changes_available": False, "geometry_pinned": False, "build_status": "no_build"}` from
  `/status` — this is spec test #1 ("fresh process → wireframe-only / gate reflects wire-only"),
  now doubly covered since Task 2 also proves the corollary (no solve happened to produce that
  state).
- [ ] **Step 2:** FAIL. **Step 3:** implement (route only; `_build_status` cell wiring is exercised
  fully once Task 5 exists — for this task it's simplest to hardcode "no_build" until
  `_read_geometry()` is non-None, deferring the "evicted" distinction's plumbing to Task 5, and come
  back to add the assertion once Task 5 lands). **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: add /status route for changes-available + mode-gating signal`.

---

## Task 5: the Load action — route, automatic-initial-Load, bootstrap-from-disk-pointer

**Files:** Modify `uedcli/serve/app.py`. Test: extend `uedcli/tests/test_serve_app.py` +
`uedcli/tests/test_serve_load_rebuild.py`.

Per spec §2 (P1 scope: no staging, so Load is a plain refresh, no conflict handling) and §4 (initial
Load is automatic; a Load — including the automatic initial one — bootstraps the geometry pin from
the on-disk pointer if the geometry slot is currently empty).

**Design note on "automatic initial Load":** the existing `_get_trunk()` double-checked-lock
convention (`_trunk_ref[0] is None` → build and populate) already IS the automatic initial Load —
the very first access to `_get_trunk()` from any route, whether that's `/scene`, `/status`,
`/rebuild`, or an explicit `/load` call, performs exactly the "nothing to pull in over yet" load the
spec describes. **This task does not need a separate "run this at startup" hook** — it needs (a) an
explicit `POST /load` route that *re-runs* the load (clears `_trunk_ref[0]` and repopulates it,
resetting `_changes_available[0]` to `False`), and (b) the disk-pointer-bootstrap check wired into
whichever code path populates `_geometry_ref[0]` from empty, run unconditionally whenever that
happens (so it fires exactly once per process for the automatic initial case, and is a no-op on any
later explicit Load once a Rebuild has already populated the slot — see spec §1's last bullet: an
on-disk pointer must never overwrite an in-memory pin a Rebuild already set this session).

**Note on Task 2's split:** bootstrap here does NOT go through `_build_and_publish_geometry()` — it
never calls `build_scene()`, it only reads an already-solved `preview_cache` entry named by the
on-disk pointer. It's a third, narrower way `_geometry_ref[0]` gets populated (bootstrap-from-disk),
alongside `_build_and_publish_geometry()` (Rebuild) — both write the same slot, neither reads through
`_read_geometry()`'s "never build" contract, since bootstrap doesn't build anything either; it just
loads bytes that already exist. No generation-guard is needed for bootstrap (it's not a slow
operation racing an invalidation — a `preview_cache` lookup is fast, and nothing else concurrently
writes `_geometry_ref[0]` from empty except a simultaneous second Load/Rebuild, a narrow enough race
that this plan doesn't add explicit locking for it beyond noting it in Open Questions).

**Interfaces:**
- `POST /api/level/{level_name}/load` →
  1. Re-reads the trunk (`trunk.read_level_with_bodies`), re-derives `_LoadedTrunk` (ranks, folders,
     sprite resolution — per spec §0, `resolve_actor_sprites`/`sprite_table`/`actor_sprites` belong
     to this axis; confirm the merged scene-cache code's actual call site per the pre-flight check
     above), and swaps it into `_trunk_ref[0]`.
  2. Resets `_changes_available[0] = False`.
  3. **Runs the bootstrap check** (see below) if and only if `_read_geometry() is None` — i.e., this
     is the level's first-ever Load in this process (or geometry was never otherwise populated).
     Never overwrites an already-populated `_geometry_ref[0]`.
  4. Returns `{"status": "ok"}` (exact response shape is a planning-time detail per spec — no
     client depends on it yet since the picker UI is out of scope here).
- **Bootstrap check** (shared by the automatic initial Load and any Load that finds geometry still
  empty): `pin = build_pin.load_pointer(project, level_name)`; if `pin is None`, set
  `_build_status[0] = "no_build"`, leave `_geometry_ref[0]` empty. Else `resolved =
  build_pin.resolve_pin(project, level_name, pin)`; if `resolved is None` (evicted), set
  `_build_status[0] = "evicted"`, leave `_geometry_ref[0]` empty (spec §1's degrade-gracefully rule —
  **never raise, never silently pretend a build exists**). Else construct a `_BuiltGeometry` from
  `pin` + `resolved` (per the pre-flight check's confirmed shape: `resolved` is the
  `(polys, texture_table, owners)` 3-tuple) and populate `_geometry_ref[0]`; set
  `_build_status[0] = "built"`.

- [ ] **Step 1: failing tests:**
  - `POST /load` with no on-disk pointer and no prior Rebuild leaves `/status`'s `build_status` as
    `"no_build"` (bootstrap found nothing, correctly) and `/scene`'s `geometry_pinned` still `false`.
  - `POST /load` when a valid on-disk pointer (test writes `current.json` directly + populates
    `preview_cache` via `store_scene` for the same hashes) exists populates `_geometry_ref[0]` and
    `/status` reports `geometry_pinned: True`, `build_status: "built"` — **without a Rebuild ever
    being called, and without `build_scene` ever being called (spy assertion, reusing Task 2's
    spy)** — spec test #8 ("opening a level with an existing on-disk pointer... unlocks all modes on
    the very first `/scene` fetch — no Rebuild needed").
  - `POST /load` when the on-disk pointer names hashes with no matching `preview_cache` entry (write
    a `current.json` naming hashes that were never `store_scene`'d) leaves `geometry_pinned: False`,
    `build_status: "evicted"` — spec test #9.
  - `POST /load` resets `changes_available` to `False` even if it was `True` beforehand (simulate via
    Task 3's flag).
  - `POST /load` refreshes `_trunk_ref[0]` (a changed trunk on disk between two Loads produces a
    different actor set on the next `/scene` fetch) but leaves an already-populated
    `_geometry_ref[0]` **untouched** — this is half of spec test #5 (Load/Rebuild independence); the
    other half (Rebuild not moving on a Load-only actor) is Task 7.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: add explicit Load route + bootstrap geometry pin from on-disk
  pointer`.

---

## Task 6: the Rebuild action — route, in-memory-only pin update, one-current-build invariant

**Files:** Modify `uedcli/serve/app.py`. Test: extend `uedcli/tests/test_serve_app.py` +
`uedcli/tests/test_serve_load_rebuild.py`.

Per spec §3. **Confirm the hash-pair-provenance finding from "Sequencing / pre-flight check" before
writing this task's implementation**: as of this plan's writing, `build_scene()` computes
`(geom_hash, light_hash)` internally but does not return them — a small return-shape change
(5-tuple) is needed, either as new work in this task or (preferably, if it's landed by the time this
plan is built) by reusing whatever the scene-cache spec's `_get_geometry()`/`_build_and_publish_geometry()`
already did to solve the identical problem. This task's test list is written to be agnostic to which
of those two is true.

**Interfaces:**
- `POST /api/level/{level_name}/rebuild` →
  1. Calls `_build_and_publish_geometry()` (Task 2) — which itself reads the CURRENT `_trunk_ref[0]`
     (via `_get_trunk()` — performing the automatic initial Load if this is the very first route hit
     in the process at all, per spec §3 test #6's framing: "no Load first" still works, because
     there's always at least the implicit initial one), computes `(geom_hash, light_hash)`, runs
     `build_scene()` under `solve_lock`, and — honoring the generation guard described in Task 2 —
     either publishes into `_geometry_ref[0]` or discards+retries if `_generation[0]` moved mid-solve.
  2. On successful publish, sets `_build_status[0] = "built"`.
  3. Does **not** touch `build_pin`'s on-disk pointer file — confirm no code path in this task calls
     anything that writes to `.uedcli/build/<level>/`. That file is Save-owned (P2) and out of this
     plan's scope entirely.
  4. Returns a response — exact shape open (planning-time detail per spec); minimally
     `{"status": "ok", "geom_hash": ..., "light_hash": ...}` is enough for tests to assert against
     without inventing client-facing contract this plan doesn't own.

- [ ] **Step 1: failing tests:**
  - `POST /rebuild` populates `_geometry_ref[0]` (via `_build_and_publish_geometry()` — assert
    `build_scene` WAS called this time, contrasting Task 2's cold-`/scene` test); a subsequent
    `/scene` fetch serves poly data from it and reports `geometry_pinned: true`; the on-disk pointer
    file is verified **absent** (or, if a fixture pre-seeded one, byte-for-byte unchanged) immediately
    after — spec test #2.
  - Two `POST /rebuild` calls in a row with no trunk change between them hit `preview_cache` (spy on
    `preview_cache.load_scene`/`store_scene` or on the solve entry point — match whatever spy pattern
    `test_serve_scene.py`'s `test_build_scene_payload_second_call_is_a_cache_hit` already uses) — no
    wasted re-solve, same cached entry both times — spec test #4.
  - `POST /rebuild` called with **no prior explicit `/load`** still succeeds and rebuilds against the
    automatically-loaded trunk (not an error, not "nothing to build") — spec test #6.
  - A successful `POST /rebuild` flips `/status`'s `geometry_pinned` from `False` to `True` and
    `build_status` from `"no_build"` to `"built"` — spec test #7 (the review-flagged "must actually
    test the gate re-opening, not just the locked state").
  - **Generation-guard test:** with an artificially slowed `build_scene` (inject a delay, matching
    the sibling spec's own generation-guard test technique), fire `POST /rebuild`, bump
    `_generation[0]` mid-solve (simulate a settled trunk change landing via Task 3's callback), and
    assert the in-flight Rebuild's result is discarded and retried rather than published over
    whatever generation now expects — mirrors the sibling spec's own dedicated generation-guard test,
    now proven for the Rebuild path specifically (the review's core ask), not just the sibling's own
    automatic-path tests.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: add Rebuild route — in-memory-only geometry pin via
  _build_and_publish_geometry(), no disk write`.

---

## Task 7: cross-cutting independent-axes tests (Load and Rebuild don't leak into each other)

**Files:** `uedcli/tests/test_serve_load_rebuild.py` (new — these need both Load and Rebuild wired,
so they land after Tasks 5–6 rather than inside either).

These are the tests spec's Testing section frames as properties of the *interaction* between Load,
Rebuild, and the watcher — not of either route alone.

- [ ] **Test A (spec test #3):** Rebuild, then a trunk change (simulate the watcher firing / call
  the on_change callback directly per Task 3's pattern), then `/scene` still serves the SAME pinned
  geometry as right after the Rebuild — unchanged — until a second explicit `/rebuild`. (This also
  exercises that a mere `_generation[0]` bump with no actual Rebuild in flight is a no-op — nothing
  reads or reacts to generation except a build that's actively checking it.)
- [ ] **Test B (spec test #5, the other half of Task 5's partial coverage):** `/load` pulls in a
  newly-added actor (write a new actor into the trunk fixture between two `/load` calls) — the actor
  appears in `/scene`'s `actors` list — but the pinned `geom_hash`/`light_hash` (from `/rebuild`'s
  last response, or `/status` if it's extended to expose them — decide at implementation time which
  is cleaner) is **unchanged** until a separate `/rebuild` call picks up the new actor.
- [ ] Run FAIL → implement (should be zero new production code if Tasks 1–6 are correct — this task
  is pure verification of already-built behavior) → PASS → commit
  `test: cover Load/Rebuild independent-axes invariants`.

If any of these fail against otherwise-passing Tasks 1–6, that's a design gap in one of those tasks,
not a new task — fix the offending task and re-run its own tests too.

---

## Deferred to P2 (Save doesn't exist yet — not built now, tracked here as follow-ups)

The spec's Testing section marks two tests P2-only; do not attempt them now (there is no Save action
to test against). When P2/Save is planned:

- **Follow-up 1:** a test that Save writes the on-disk pointer file to match the in-memory pin at
  Save time, atomically with the trunk write, and that a process restart right after (no further
  Rebuild) still serves the SAVED build.
- **Follow-up 2:** a test that a Rebuild with no subsequent Save leaves the on-disk pointer file
  untouched, and a simulated restart falls back to the last SAVED pointer (or "no build" if none) —
  the discarded Rebuild leaves no trace on disk.

`build_pin.py`'s `load_pointer`/`resolve_pin` (Task 1) are written to be reusable as-is by whatever
writes the pointer at Save time — this plan deliberately does not add a `write_pointer` function
now, since nothing in P1's scope ever calls one (see Global constraints); P2's plan should add it
next to Save's own atomic trunk-write code, not resurrect it here.

## Verification (pre-merge, per `building-features.md` + `tests.md`)

- `bin/test -k serve` (scoped), then full `bin/test` once before merge.
- Read the diff; confirm no route in this plan's scope writes to the maps directory or to
  `.uedcli/build/` (grep the diff for `write_text`/`write_bytes`/`.replace(` touching either path —
  should find none).
- **Confirm `_get_geometry()` has zero remaining references anywhere in the diff/codebase** after
  Task 2 — grep for it; a leftover call site (e.g. in a test not updated, or a doc comment) is a sign
  the removal was incomplete.
- **Confirm `build_scene` is called from exactly one place in `serve/app.py`'s route surface**:
  inside `_build_and_publish_geometry()`, reached only from `POST /rebuild`. Grep for `build_scene(`
  in `app.py`/`scene.py` and account for every call site.
- Exercise the app (`building-features.md` step): `uedcli serve <fixture-level>`, hit `/scene` cold
  (expect empty `polys`, `geometry_pinned: false`, and — watch the process, not just the response —
  confirm no multi-second CSG solve runs), hit `/status` cold (expect `no_build`), `POST /rebuild`
  (now observe the solve happening), re-hit `/scene`/`/status` (expect populated polys,
  `geometry_pinned: true`, `built`), edit the trunk externally, confirm `/status`'s
  `changes_available` flips without the viewport auto-refetching (no more silent WS `"reload"` — a
  manual check, since the client-side banner UI itself is Slice 2's build, out of scope here).
- One subagent review (`reviewer-brief.md` as context pack) given this plan's size (7 tasks touching
  one file's route surface + one new module, including a removal of previously-merged code) — a
  single review pass is enough; escalate to a second reviewer only if the first raises unresolved
  cross-cutting concerns, particularly around Task 2's removal of `_get_geometry()`.

## Open questions (do not guess past these — confirm before/while building)

1. **The remaining items under "Sequencing / pre-flight check"** — exact merged shape of
   `_LoadedTrunk`/`_BuiltGeometry`/`_get_trunk` (still unbuilt as of this plan's writing), and
   whether `build_scene`'s needed 5-tuple return-shape change (to surface `geom_hash`/`light_hash`,
   confirmed missing today) is made by this plan's Task 6 or already made by the scene-cache spec's
   own geometry-build function. (`owners`' provenance is resolved — it's `build_scene`'s existing
   `actor_names_by_poly` third return value.) The single biggest remaining risk to this plan's Task 6.
2. **Corrupt on-disk pointer file handling** (Task 1) — this plan assumes "degrade like a miss,
   never raise," matching the codebase's general cache-corruption posture, but the spec doesn't
   state this explicitly. Low risk but worth a one-line confirmation.
3. **Route response shapes for `/load`, `/rebuild`, `/status`, and the new `geometry_pinned` field on
   `/scene`/`/atlas`** — this plan proposes concrete JSON shapes to make the tasks buildable/testable,
   but the spec explicitly leaves this open ("planning-time detail, not a design fork"). Treat this
   plan's shapes as a reasonable default, not a spec requirement.
4. **Whether `/status` is the right single-endpoint design** vs. two separate signals (Task 4) — also
   this plan's own choice, flagged for the same reason as #3.
5. **`POST /load`'s and `POST /rebuild`'s exact HTTP method/path spelling** — spec only gives an
   example for Rebuild (`POST /api/level/{level}/rebuild`); this plan mirrors that convention for
   Load and status but the spec doesn't pin these down either.
6. **Should a successful Load also bump `_generation[0]`, not just the watcher?** (New question from
   this revision.) Task 2's generation guard, as scoped, only protects a Rebuild's publish against a
   *watcher-detected external change* landing mid-solve — it does NOT specifically protect against a
   concurrent explicit *Load* changing `_trunk_ref[0]` while a Rebuild is mid-solve (a narrower, more
   precise race: Rebuild started against trunk-state-A, a Load lands and moves to trunk-state-B
   mid-solve, Rebuild's result — computed against stale state-A — would still currently publish,
   since only the watcher bumps generation, not Load). This plan deliberately does NOT add a
   Load-triggered generation bump, judging it a real but narrow edge case (a human clicking Load
   while a ~24s Rebuild solve is already in flight) not explicitly asked for by either spec or the
   review — but it's a legitimate follow-up hardening if the executor or a reviewer judges it worth
   closing now rather than later. Flagged rather than silently decided either way.
7. **Bootstrap-from-disk-pointer (Task 5) has no explicit lock around its
   check-then-populate-`_geometry_ref[0]`** — two concurrent first-ever `/load` (or `/scene`-via-
   auto-Load) calls on a level with a valid on-disk pointer could both read `pin is None` as false,
   both call `resolve_pin`, and both write `_geometry_ref[0]` — harmless (idempotent, same result
   either way) but redundant work. Not fixed here; flagged as a minor, low-priority hardening item.
