# Plan — share one in-process scene cache across `/scene`, `/atlas`, `/lightmap`

> For agentic workers: follow `dev/docs/rules/building-features.md` (worktree, verify, review,
> squash-merge) and `dev/docs/rules/tests.md` (scoped `bin/test -k serve`, full suite once
> pre-merge). Granularity/style follows `dev/docs/board/to-plan/uedcli-human-gui/plan.md`'s Slice 1:
> numbered tasks, each with Files/Interfaces, a failing-test-first TDD sequence, verify, commit.

**Spec:** `dev/docs/board/to-spec/uedcli-serve-share-one-in-process-scene-cache/spec.md` — read it
in full; this plan argues from its Design and Testing sections and does not re-derive their
reasoning. The spec now includes a generation-guard design and a documented games-config-restart
trade-off (added after a review of an earlier draft of this plan found a real race) — both are
carried through below.

**Correction history:**
- A first draft of this plan was written against a stale read of `uedcli/serve/{app,scene}.py` /
  `preview_native.py` and wrongly concluded `resolve_actor_sprites`/`ActorSprite`/per-poly ownership
  didn't exist. Re-verified directly against the current tree — they do; see "Verified current
  signatures" below.
- A second review (of the corrected plan) found a real, unaddressed race in the double-checked-
  locking sketch: a slow build in flight when an invalidation lands can publish a stale result over
  the fresh `None`, indefinitely. This revision adds the generation guard (Task 1), the invalidation
  callback's generation bump (Task 2), a dedicated test forcing that exact race window open (Task 2),
  the games-config trade-off note (below), a concretely-wired concurrency test (Task 6), an explicit
  callout on the `actor_sprites` type deviation (Task 1), a note on Task 4/5's correctness coupling,
  and a consistent parameter order for `_get_trunk`/`_get_geometry`'s shared params.

## Verified current signatures (re-read directly from the tree, not from a stale checkout)

- `uedcli/preview_native.py:594` —
  `build_scene(level, search_files, index, *, defaults, project=None, level_name=None,
  visibility: Literal["gameplay", "editor"] = "gameplay") -> tuple[list, list, list]` — returns
  **`(polys, texture_table, actor_names_by_poly)`**, a 3-tuple. `actor_names_by_poly` is a list
  parallel to `polys` giving each poly's owning actor name (`None` for an out-of-range CSG join) —
  real, existing per-poly ownership data. `visibility="editor"` is what `uedcli serve` always passes.
- `uedcli/preview_native.py:380` —
  `resolve_actor_sprites(level, index, search_files) -> tuple[list[tuple[int,int,bytes,bytes]],
  dict[str, tuple[int, float, float]]]` — real, exists today. Returns `(extra_table, actor_sprites)`:
  `actor_sprites` maps actor name → `(local_tex_index, width_uu, height_uu)`, NOT yet offset into the
  combined atlas — the caller adds `len(texture_table)`.
- `uedcli/serve/scene.py` already has `ActorSprite` (frozen dataclass: `tex_index`, `width`,
  `height`), `BrushHighlight`, `ScenePoly.owner: str | None`, `SceneActor.sprite: ActorSprite |
  None`, `SceneActor.brush: BrushHighlight | None`. `build_scene_payload` (today's signature:
  `(project, level_name, index, defaults, search_files) -> ScenePayload`) already: reads the trunk,
  calls `build_scene(..., visibility="editor")`, zips `owners` onto `ScenePoly.owner`, calls
  `resolve_actor_sprites` and wraps its result into `SceneActor.sprite`, drops `bHiddenEd` actors
  (`_is_hidden_ed`), and computes `_brush_highlight` per brush actor.
- `uedcli/serve/app.py`'s current `/atlas` route already calls `resolve_actor_sprites` itself and
  appends its table onto `_build_scene`'s own — this is the spec Background's confirmed redundancy
  (called once in `build_scene_payload` for `/scene`, called again independently in `/atlas`), real
  and present.
- `web/src/scene/selection.ts` already does real per-poly-ownership picking
  (`resolveHitActor`/`ScenePoly.owner`), with actor-bbox picking (`pickActor`) kept only as the
  fallback for a tap that hits no triangle. `_BuiltGeometry.owners` is consumed by a real feature.

## Open question — still stands (unaffected by the generation-guard revision)

- **OQ1 — `_BuiltGeometry.geom_hash`/`light_hash` have no return path from `build_scene`.**
  `build_scene` computes `geom_hash, light_hash = _scene_hashes(...)` (line 656, only when
  `project`/`level_name` given), uses them purely to key its own two `preview_cache` lookups, and
  **does not return them** — its two return statements are the early cache-hit `return cached_scene`
  (line 663) and the final `return polys, texture_table, actor_names_by_poly` (line 890). Both hashes
  are still in local scope at both points, so returning them too is mechanically a two-line change —
  **but every existing caller unpacks a fixed-width tuple**, and widening it breaks all of them:
  `uedcli/preview_native.py:990` (`render_shots`), `uedcli/serve/scene.py:188`, and **~30+ unpacking
  call sites in `uedcli/tests/test_preview_native.py`**. Two ways to resolve, spec owner's call:
  1. **Do it now, as part of Task 1** — widen `build_scene`'s return, fix every call site, populate
     `_BuiltGeometry.geom_hash`/`.light_hash` for real.
  2. **Defer** — store `geom_hash=None, light_hash=None` for now (this spec's own routes never read
     them either way), let the sibling explicit-rebuild spec widen `build_scene`'s signature when it
     actually starts consuming these fields.
  This plan writes Task 1 to default to **option 2** (smallest change that solves *this* spec's
  problem) but flags it as the spec owner's decision, not a unilateral one.

**Placement decision:** `_LoadedTrunk`/`_BuiltGeometry` go in `scene.py`, next to the existing
`ScenePoly`/`SceneActor`/`ScenePayload`/`ActorSprite`/`BrushHighlight`. `app.py` already does
`from .scene import build_scene_payload`; adding `_LoadedTrunk, _BuiltGeometry` to that same import
keeps the existing dependency direction with no new cycle. The `_ref` holders, `_generation` counter,
`_get_trunk()`/`_get_geometry()` getters, and locks live in `app.py`'s `create_app` closure.

**Parameter-order convention (review fix, item 5):** `_get_trunk` and `_get_geometry` share two
parameters (`search_files`, `index`); the earlier draft ordered them inconsistently
(`_get_trunk(index, search_files)` vs. `_get_geometry(search_files, index, defaults)`) — a
transposition trap at call sites. This plan fixes both to **`(search_files, index, ...)`**,
matching `_scene_inputs()`'s own return order `(search_files, index, defaults)` — one order to
remember, everywhere: `_get_trunk(search_files, index)`, `_get_geometry(search_files, index,
defaults)`.

**Games-config-restart trade-off (must be documented, not silently shipped — review item 1):** the
spec's Design section now states this explicitly, quoted here so it isn't lost between spec and
code: *"per-request games-config changes no longer take effect without a restart, once the geometry
cache is warm. `_scene_inputs`'s existing docstring documents today's behavior: config is recomputed
fresh every request 'so a `--project`'s on-disk games config can change without a `serve` restart.'
Under this cache, `_scene_inputs` is still called fresh every request, but a warm `_get_geometry()`
returns the cached build without ever consulting the freshly-recomputed config — so a games-config
edit has no effect until an unrelated trunk change invalidates the cache, or the process restarts.
Accepted because games-config edits are rare... a `serve` restart is a reasonable workaround."*
**Task 1 must update `_scene_inputs`'s docstring** to add this caveat — leaving its current "no
restart needed" claim unqualified would make it actively misleading once the cache lands.

---

## Task 1: `_LoadedTrunk` / `_BuiltGeometry` dataclasses + atomic-swap holders + generation-guarded, double-checked-locked getters

**Files:** Modify `uedcli/serve/scene.py` (add the two dataclasses), `uedcli/serve/app.py` (add the
holders + getters inside `create_app`, exposed on `app.state` for tests only — same existing
convention as `app.state.connections` / `app.state.broadcast_reload`; update `_scene_inputs`'s
docstring per the trade-off note above). Test: extend `uedcli/tests/test_serve_app.py`.

**Interfaces:**

```python
# scene.py, alongside ScenePoly/SceneActor/ScenePayload/ActorSprite/BrushHighlight
@dataclass(frozen=True, kw_only=True)
class _LoadedTrunk:
    level: Level
    ranks: dict[str, str]
    folders: dict[str, str | None]
    sprite_table: list[tuple[int, int, bytes, bytes]]    # resolve_actor_sprites's extra_table
    actor_sprites: dict[str, tuple[int, float, float]]   # ** DELIBERATE, STATED DEVIATION from the
        # spec's literal `dict[str, ActorSprite]` ** -- resolve_actor_sprites returns the RAW
        # (local_tex_index, width_uu, height_uu) tuple, not wrapped `ActorSprite` objects, because
        # wrapping requires `tex_offset = len(geometry.texture_table)` -- a GEOMETRY-slot value, not
        # knowable while only the trunk slot is being built. The tex_offset + ActorSprite wrap still
        # happens in build_scene_payload (Task 3) once both slots are available, exactly like
        # today's code. Flagged explicitly so a reviewer diffing spec-vs-plan doesn't read this as an
        # accidental miss.

@dataclass(frozen=True, kw_only=True)
class _BuiltGeometry:
    geom_hash: str | None    # OQ1 — None until/unless build_scene's signature is widened (see above)
    light_hash: str | None   # OQ1 — ditto
    polys: list[tuple]       # build_scene()'s raw 9-tuples, unconverted
    texture_table: list[tuple]
    owners: list[str | None] # build_scene()'s 3rd return value, actor_names_by_poly, verbatim
```

- Produces (in `app.py`, inside `create_app`, alongside the existing `solve_lock`):
  ```python
  _generation = [0]                                   # bumped by every invalidation (Task 2)
  _trunk_lock = threading.Lock()
  _trunk_ref: list[_LoadedTrunk | None] = [None]
  _geometry_ref: list[_BuiltGeometry | None] = [None]

  def _get_trunk(search_files, index) -> _LoadedTrunk:
      while True:
          cached = _trunk_ref[0]
          if cached is not None:
              return cached
          with _trunk_lock:
              cached = _trunk_ref[0]
              if cached is not None:
                  return cached
              gen_before = _generation[0]
              lvl, ranks, _bodies, folders = trunk.read_level_with_bodies(maps_root / level)
              sprite_table, actor_sprites = resolve_actor_sprites(lvl, index, search_files)
              if _generation[0] != gen_before:
                  continue    # invalidated mid-build: discard, loop back and retry from the top
              built = _LoadedTrunk(level=lvl, ranks=ranks, folders=folders,
                                   sprite_table=sprite_table, actor_sprites=actor_sprites)
              _trunk_ref[0] = built
              return built

  def _get_geometry(search_files, index, defaults) -> _BuiltGeometry:
      while True:
          cached = _geometry_ref[0]
          if cached is not None:
              return cached
          with solve_lock:
              cached = _geometry_ref[0]
              if cached is not None:
                  return cached
              gen_before = _generation[0]
              trunk_state = _get_trunk(search_files, index)
              polys, texture_table, owners = _build_scene(trunk_state.level, search_files, index,
                                                          defaults=defaults, project=project,
                                                          level_name=level, visibility="editor")
              if _generation[0] != gen_before:
                  continue    # invalidated mid-build: discard, loop back and retry from the top
              built = _BuiltGeometry(geom_hash=None, light_hash=None,   # OQ1 placeholders
                                     polys=polys, texture_table=texture_table, owners=owners)
              _geometry_ref[0] = built
              return built
  ```
  **Deliberate departure from the spec's illustrative pseudocode (important, not cosmetic):** the
  spec's Design section sketches the generation-guard retry as `return _get_geometry()` — a
  *recursive* call made from **inside** the `with solve_lock:` block. `threading.Lock` is **not
  reentrant**: a recursive call attempting `with solve_lock:` again on the same thread, before the
  outer `with` has exited, **deadlocks**. (`return` normally triggers `__exit__` before unwinding,
  but the recursive call's body — including its own `with solve_lock:` — executes *before* that
  `return` completes, i.e. while the outer lock is still held.) This plan uses a `while True:` +
  `continue` loop instead: `continue` from inside a `with` block runs `__exit__` (releasing the lock)
  *before* control returns to the top of the loop, so the retry's re-acquisition of the same lock
  never contends with itself. Same fix applies to `_get_trunk`/`_trunk_lock`. If the spec owner wants
  the literal recursive form preserved for readability, `solve_lock`/`_trunk_lock` would need to be
  `threading.RLock()` instead — either is correct; this plan picks the loop since it also avoids
  unbounded recursion depth under a rapid-edit storm.
  `_get_trunk(search_files, index)` needs both because `resolve_actor_sprites` does. `_get_geometry`
  captures `gen_before` before calling `_get_trunk()` too, so an invalidation landing during EITHER
  the nested trunk fetch or the `_build_scene` call is caught by the same check.
- **Trunk-lock decision** (spec left this open, "decide at plan time"): use a **dedicated
  `_trunk_lock`**, not `solve_lock`, but the *same* double-checked-locking + generation-guard shape
  as `_get_geometry()`. Rationale: correctness doesn't strictly require a lock here (a plain
  null-check race just risks a redundant harmless re-read), but two functions doing the identical job
  with two different concurrency idioms is more to reason about than one uncontended `Lock()`
  acquisition costs.
- Expose for testing only: `app.state.get_trunk = _get_trunk`, `app.state.get_geometry =
  _get_geometry`.
- Update `_scene_inputs`'s docstring (see "Games-config-restart trade-off" above) to add the caveat
  sentence once `_get_geometry` is warm.

- [ ] **Step 1: failing test** — in `test_serve_app.py`, write a tiny fixture trunk (reuse
  `test_serve_scene.py`'s `_write_fixture_trunk`/`_ued22_index` pattern — `_get_trunk` needs a real
  index since `resolve_actor_sprites` calls `resolve_class_defaults` per actor). Spy on
  `uedcli.trunk.read_level_with_bodies`, call `app.state.get_trunk([], index)` twice, assert the spy
  fired once and both calls returned the *same object* (`is`, not `==`).
- [ ] **Step 2:** run, verify FAIL (`app.state.get_trunk` doesn't exist).
- [ ] **Step 3:** implement the two dataclasses in `scene.py` and the holders/getters/`app.state`
  exposure + `_scene_inputs` docstring update in `app.py`, per the sketches above (OQ1's
  `geom_hash`/`light_hash` as `None` unless the spec owner picked option 1 above).
- [ ] **Step 4:** run, verify PASS. Add the matching `_get_geometry` test (spy on
  `uedcli_native.build_geometry_bspcsg`, same one/two-call pattern
  `test_build_scene_payload_second_call_is_a_cache_hit` used) — this covers the NON-racing
  double-checked-locking behavior only; the generation guard's own race-handling gets its dedicated
  test in Task 2 (needs the invalidation callback to exist first).
- [ ] **Step 5:** commit `feat: add _LoadedTrunk/_BuiltGeometry cache holders with a generation guard`.

## Task 2: watcher settle callback bumps generation + clears both slots before broadcasting

**Files:** Modify `uedcli/serve/app.py`. Test: extend `uedcli/tests/test_serve_app.py`.

**Interfaces:**
- Replace the `TrunkWatcher(maps_root / level, _broadcast_reload)` wiring with a new
  `_on_trunk_settled()` that the watcher calls instead:
  ```python
  async def _on_trunk_settled() -> None:
      # Order matters (spec, "Invalidation ordering"): bump the generation and clear BOTH slots
      # before broadcasting. The bump/clear order between themselves doesn't matter (no lock, no
      # other code reads `_generation` except a build checking it after its own slow work) -- what
      # matters is that ALL THREE happen before the WS broadcast, and that none of them takes
      # solve_lock (event-loop-freeze hazard, same reasoning as before). The bump is what makes a
      # build already in flight when this fires discard itself instead of publishing stale data
      # (Task 1's generation guard).
      _generation[0] += 1
      _trunk_ref[0] = None
      _geometry_ref[0] = None
      await _broadcast_reload()

  watcher = TrunkWatcher(maps_root / level, _on_trunk_settled)
  ```
  Expose `app.state.on_trunk_settled = _on_trunk_settled` (test-only) so a test can fire it directly.
- [ ] **Step 1: failing test** — populate both refs directly (via `app.state.get_trunk(...)` /
  `app.state.get_geometry(...)`, from Task 1), call `app.state.on_trunk_settled()`
  (`asyncio.run(...)`), assert a fresh `app.state.get_trunk(...)` call afterwards triggers a new
  `trunk.read_level_with_bodies` call (spy count 2). Also assert the reload broadcast still fires
  (reuse `test_broadcast_reload_survives_a_connection_change_mid_broadcast`'s `FakeWS` pattern).
- [ ] **Step 2:** FAIL (`_on_trunk_settled` doesn't exist / refs don't clear).
- [ ] **Step 3:** implement as above.
- [ ] **Step 4:** PASS.
- [ ] **Step 5 — the dedicated generation-guard test (spec Testing bullet, review-mandated,
  concretely wired, not prose):** this is the test that actually forces the race window from Task 1's
  code comment open — `_build_scene` is gated with a `threading.Event` so the block is deterministic,
  not timing-dependent:
  ```python
  def test_generation_guard_discards_a_build_invalidated_mid_flight(tmp_path, monkeypatch):
      """A slow _get_geometry() build in flight for the PRE-edit trunk must discard its result and
      rebuild against the POST-edit state when an invalidation lands mid-build, never publish the
      stale result. Task 6's concurrency test can't exercise this -- its fixture solves near-
      instantly, so the invalidation never actually lands DURING a build."""
      import threading
      from types import SimpleNamespace
      from uedcli import trunk as trunk_module
      from uedcli.model import Level
      from uedcli.serve import app as serve_app
      from uedcli.tests.conftest import cube_room
      from uedcli.tests.test_serve_scene import DEFAULTS, _ued22_index

      root = tmp_path / "proj"
      maps_dir = root / "maps" / "TestLevel"
      maps_dir.mkdir(parents=True)
      room = cube_room(name="Room")
      trunk_module.write_level(maps_dir, Level(actors={room.name: room}, order=[room.name]),
                               {room.name: "m"})
      project = SimpleNamespace(root=str(root), maps=None)

      monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], _ued22_index(), DEFAULTS))
      app = serve_app.create_app(project, "TestLevel")

      real_build_scene = serve_app._build_scene
      build_entered = threading.Event()
      release_build = threading.Event()

      def gated_build_scene(*a, **kw):
          build_entered.set()
          release_build.wait(timeout=5)
          return real_build_scene(*a, **kw)

      monkeypatch.setattr(serve_app, "_build_scene", gated_build_scene)

      result: dict = {}

      def call_get_geometry():
          search_files, index, defaults = serve_app._scene_inputs(project)
          result["geometry"] = app.state.get_geometry(search_files, index, defaults)

      t = threading.Thread(target=call_get_geometry)
      t.start()
      assert build_entered.wait(timeout=5)          # the slow build is now genuinely in flight

      room2 = cube_room(name="Room2")                # the "real edit" landing mid-build
      trunk_module.write_level(maps_dir, Level(actors={room2.name: room2}, order=[room2.name]),
                               {room2.name: "m"})
      asyncio.run(app.state.on_trunk_settled())       # bumps generation, clears both refs

      release_build.set()                             # let the stale (pre-edit) build finish
      t.join(timeout=10)

      assert set(result["geometry"].owners) == {"Room2"}   # never the discarded "Room" result
  ```
  Walk-through: `_get_trunk()` reads the PRE-edit ("Room") trunk before the gate blocks (it only
  gates `_build_scene`), so the in-flight `_get_geometry()` call captured `gen_before` and a
  pre-edit `trunk_state` already. `on_trunk_settled()` bumps the generation and clears both refs
  while that build is still parked on `release_build.wait()`. Once released, `_build_scene` returns
  its (now-stale) result, the generation check fails, and the `while True` loop retries: `_get_trunk`
  re-reads the trunk (now "Room2" on disk) and rebuilds, `_build_scene` runs again (the gate is
  already `.set()`, so no second block), and the FRESH result publishes. The test never sees the
  discarded intermediate value — only the correct end state — which is exactly what "discarded, not
  published" means operationally.
- [ ] **Step 6:** commit `feat: bump generation on trunk settle; add generation-guard race test`.

## Task 3: refactor `build_scene_payload` to take already-built pieces

**Files:** Modify `uedcli/serve/scene.py`. Test: modify `uedcli/tests/test_serve_scene.py`.

**Interfaces:**
- New signature: `build_scene_payload(trunk: _LoadedTrunk, geometry: _BuiltGeometry, index) ->
  ScenePayload` — drops `project, level_name, defaults, search_files`. **`index` stays a
  parameter** — `_is_hidden_ed(actor, index)` and `_brush_highlight(actor, index)` both resolve
  class defaults per actor on every call, independent of either cached slot; cheap enough (no CSG, no
  texture decode) that there's no reason to cache them, they just need `index` passed through.
- The function body becomes otherwise pure: reads `geometry.polys`/`geometry.texture_table` instead
  of calling `build_scene()`, `trunk.level`/`trunk.ranks` instead of calling
  `trunk.read_level_with_bodies()`, and `trunk.sprite_table`/`trunk.actor_sprites` instead of calling
  `resolve_actor_sprites()` (the `tex_offset = len(texture_table)` combine step moves here unchanged
  from today's code, now reading `len(geometry.texture_table)`). Remove the now-unused
  `resolve_actor_sprites` import from `scene.py` (it's called only from `app.py`'s `_get_trunk` now).
- **Keep reading `actor.folder` directly off `trunk.level.actors[name]` for `SceneActor.folder`,
  exactly as today** — do NOT switch to `trunk.folders[name]` (today's code already discards the
  `read_level_with_bodies` folders return in favor of the model's own `actor.folder`; that map exists
  for the write-side diff, not reads).
- Because `build_scene_payload` is now pure, delete `test_build_scene_payload_second_call_is_a_cache_
  hit` from `test_serve_scene.py` (nothing left to cache-hit against; Task 1's `_get_geometry()` test
  already covers that intent).
- [ ] **Step 1: failing test** — rewrite every existing `test_serve_scene.py` test that calls
  `build_scene_payload(project, level_name, index, defaults, search_files)` —
  `test_build_scene_payload_has_polys_and_actors`,
  `test_build_scene_payload_filters_bhiddened_actors_and_keeps_bhidden_ones`,
  `test_build_scene_payload_resolves_actor_sprite_from_real_texture`,
  `test_build_scene_payload_actor_sprite_none_without_dt_sprite` — to instead: call
  `trunk.read_level_with_bodies`, `build_scene(..., visibility="editor")`, and
  `resolve_actor_sprites` directly, wrap the results into a `_LoadedTrunk(...)`/`_BuiltGeometry(
  geom_hash=None, light_hash=None, ...)`, then call `build_scene_payload(trunk_obj, geometry_obj,
  index)`. Assert the exact same outcomes each test already asserts.
- [ ] **Step 2:** FAIL (old signature still in place).
- [ ] **Step 3:** implement the refactor; delete the obsolete cache-hit test.
- [ ] **Step 4:** PASS. `test_scene_route_returns_200_with_a_json_safe_payload` is HTTP-level; leave
  it as-is here, re-verify in Task 4.
- [ ] **Step 5:** commit `refactor: build_scene_payload takes pre-built trunk/geometry`.

---

**Note — Tasks 4 and 5 are correctness-coupled (review item 4).** Rewiring the routes onto the shared
cache (Task 4) without also tightening `_require_level` (Task 5) leaves a real gap: with a genuine
single-level cache in place, an untightened `_require_level` would let a request for a second,
still-valid-on-disk level name silently read the FIRST level's cached `_LoadedTrunk`/`_BuiltGeometry`
— wrong data, not a crash, so nothing would fail loudly. This never actually ships as an intermediate
state (the whole plan squash-merges as one commit per `building-features.md`), but if these two tasks
are ever reviewed or landed independently, Task 5 must not be deferred past Task 4.

## Task 4: rewire `/scene`, `/atlas`, `/lightmap` onto the shared holders

**Files:** Modify `uedcli/serve/app.py`. Test: modify/extend `uedcli/tests/test_serve_scene.py`,
`uedcli/tests/test_serve_textures.py`, add a new shared-cache test (either file, or a new
`test_serve_cache.py`).

**Interfaces:**
```python
@app.get("/api/level/{level_name}/scene")
def scene(level_name: str) -> dict:
    _require_level(level_name)
    search_files, index, defaults = _scene_inputs(project)
    trunk_state = _get_trunk(search_files, index)
    geometry = _get_geometry(search_files, index, defaults)
    payload = build_scene_payload(trunk_state, geometry, index)
    return {"polys": [asdict(p) for p in payload.polys],
            "actors": [asdict(a) for a in payload.actors]}

@app.get("/api/level/{level_name}/atlas")
def atlas(level_name: str) -> dict:
    _require_level(level_name)
    search_files, index, defaults = _scene_inputs(project)
    trunk_state = _get_trunk(search_files, index)
    geometry = _get_geometry(search_files, index, defaults)
    # Appending trunk_state.sprite_table (not just geometry.texture_table) is what keeps the spec's
    # Non-goal ("no change to what data any endpoint returns") true -- today's /atlas ALREADY returns
    # sprite rects via its own resolve_actor_sprites call; dropping the append would be the actual
    # regression, not adding it.
    texture_table = geometry.texture_table + trunk_state.sprite_table
    png_bytes, manifest, width, height = build_atlas(texture_table)
    return {"width": width, "height": height, "manifest": manifest,
            "png_base64": base64.b64encode(png_bytes).decode("ascii")}

@app.get("/api/level/{level_name}/lightmap")
def lightmap(level_name: str) -> dict:
    _require_level(level_name)
    search_files, index, defaults = _scene_inputs(project)
    geometry = _get_geometry(search_files, index, defaults)
    png_bytes, manifest, width, height, intensity = build_lightmap_atlas(geometry.polys)
    return {"width": width, "height": height, "intensity": intensity, "manifest": manifest,
            "png_base64": base64.b64encode(png_bytes).decode("ascii")}
```
`atlas`/`lightmap` no longer call `trunk.read_level_with_bodies`, `_build_scene`, or
`resolve_actor_sprites` directly — all three now come from `_get_trunk()`/`_get_geometry()` alone.
Remove the now-unused `resolve_actor_sprites` import from `app.py` only if nothing else calls it
directly outside `_get_trunk`. `_require_level` still runs first in every route.

- [ ] **Step 1: failing test — spec Testing bullet 1**: spy on `uedcli.trunk.read_level_with_bodies`,
  `uedcli_native.build_geometry_bspcsg`, and `resolve_actor_sprites` (patch
  `uedcli.serve.app.resolve_actor_sprites`, its only call site post-refactor). Call `GET /scene`,
  `GET /atlas`, `GET /lightmap` in that order against an unchanged fixture trunk. Assert all three
  spies fired exactly once across the three requests.
- [ ] **Step 2:** FAIL (routes still independently reload/rebuild/re-resolve sprites).
- [ ] **Step 3:** implement the route bodies above.
- [ ] **Step 4:** PASS the shared-cache test.
- [ ] **Step 5 — spec Testing bullet 2, end-to-end half**: extend the same test: after the three
  initial requests, rewrite the fixture trunk's actor file and call `app.state.on_trunk_settled()`
  (or let a real `TrunkWatcher.notify()` + `debounce_s` elapse) — then `GET /scene` again and assert
  all three spies incremented, and the returned payload reflects the edit.
- [ ] **Step 6:** re-run `test_scene_route_returns_200_with_a_json_safe_payload`,
  `test_atlas_route_returns_200_with_a_json_safe_payload`,
  `test_every_poly_tex_index_resolves_to_a_manifest_rect` — fix any breakage (expected: none).
- [ ] **Step 7:** commit `feat: wire /scene, /atlas, /lightmap onto the shared trunk/geometry cache`.

## Task 5: tighten `_require_level`

**Files:** Modify `uedcli/serve/app.py`. Test: extend `uedcli/tests/test_serve_app.py`.

(See the correctness-coupling note above Task 4 — this task closes the gap Task 4's cache wiring
opens; do not defer it past Task 4 even though both land in one squash-merged commit.)

**Interfaces:**
```python
def _require_level(level_name: str) -> None:
    if ("/" in level_name or level_name in ("", ".", "..")
            or level_name != level
            or not (maps_root / level_name).is_dir()):
        raise CommandError(f"level not found: {level_name!r}")
```

- [ ] **Step 1: failing test — spec Testing bullet 4**: create a project with **two** real level
  directories under `maps/` (`TestLevel`, `OtherLevel`), `create_app(project, "TestLevel")`,
  `GET /api/level/OtherLevel/scene` → assert the same clean "level not found" 4xx `CommandError`
  shape, and assert it does NOT silently return `TestLevel`'s cached data (spy on
  `trunk.read_level_with_bodies`, assert it never fires for `OtherLevel`).
- [ ] **Step 2:** FAIL (today's `_require_level` accepts `OtherLevel`).
- [ ] **Step 3:** implement the one-line fix above.
- [ ] **Step 4:** PASS.
- [ ] **Step 5:** commit `fix: reject a syntactically-valid but non-matching level name`.

## Task 6: concurrency test — no torn reads across a racing invalidation

**Files:** Test only: extend `uedcli/tests/test_serve_app.py` (or a new
`uedcli/tests/test_serve_concurrency.py`). No production code change expected.

**Interfaces / test design** (mirrors `uedcli/tests/test_schema_cache.py`'s
`test_parallel_writers_produce_a_valid_entry`), with the fixture mutation concretely wired at a point
relative to `barrier.wait()` that guarantees real interleaving (review item 2 — the earlier draft
only described this in prose):

```python
def test_concurrent_requests_never_see_a_torn_trunk_or_geometry_slot(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from uedcli import trunk as trunk_module
    from uedcli.model import Level
    from uedcli.serve import app as serve_app
    from uedcli.tests.conftest import cube_room
    from uedcli.tests.test_serve_scene import DEFAULTS, _ued22_index

    root = tmp_path / "proj"
    maps_dir = root / "maps" / "TestLevel"
    maps_dir.mkdir(parents=True)
    room = cube_room(name="Room")
    trunk_module.write_level(maps_dir, Level(actors={room.name: room}, order=[room.name]),
                             {room.name: "m"})
    project = SimpleNamespace(root=str(root), maps=None)

    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], _ued22_index(), DEFAULTS))
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)
    c.get("/api/level/TestLevel/scene")           # warm both slots once, deterministically

    barrier = threading.Barrier(8)
    results: list[dict] = []
    errors: list[Exception] = []

    def worker(i: int):
        try:
            barrier.wait()
            if i == 0:
                # The mutation + invalidation happen HERE, right after the barrier releases all 8
                # threads together -- guarantees this races the other 7 threads' GETs, not a vacuous
                # "invalidate before anyone reads" sequence.
                room2 = cube_room(name="Room2")
                trunk_module.write_level(maps_dir, Level(actors={room2.name: room2},
                                                         order=[room2.name]), {room2.name: "m"})
                asyncio.run(app.state.on_trunk_settled())
            else:
                r = c.get("/api/level/TestLevel/scene")
                results.append(r.json())
        except Exception as e:                              # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert not errors
    # No torn read WITHIN a slot: every response's actor set is internally self-consistent -- from
    # ONE trunk generation, never a mix of pre- and post-edit data. Do NOT assert the two slots agree
    # with each other across responses (spec: incidental to this spec's scope, not a guarantee here).
    for body in results:
        actor_names = {a["name"] for a in body["actors"]}
        assert actor_names in ({"Room"}, {"Room2"})   # whichever generation, never a MIX
```

- [ ] **Step 1: failing test** — write it after Tasks 1/2/4 land and confirm it currently PASSES (the
  atomic-swap + generation-guard design should already make this hold) — if it does not fail on
  demand, prove the test is sound by temporarily breaking the swap (e.g. mutating `_trunk_ref[0]`'s
  fields in place instead of replacing the reference, or skipping the generation check) and
  confirming the test catches it, then revert the deliberate breakage.
- [ ] **Step 2:** confirm PASS against the real implementation from Tasks 1/2/4.
- [ ] **Step 3:** commit `test: concurrent requests never see a torn trunk/geometry read`.

Note this test alone does NOT exercise the generation-guard race (its fixture solves fast enough that
an invalidation can't land mid-build) — that's Task 2 Step 5's dedicated, gated test.

---

## Verification (pre-merge)

- `bin/test -k serve` (scoped, per `dev/docs/rules/tests.md`); full `bin/test` once before merge.
- Formatter/linter/type-checker, per `building-features.md`.
- Read the diff; run the new behavior (the `verify` skill / `building-features.md` step 2).
- **Live, per the spec's own Verification section** — against the real WanChai level, not a fixture:
  1. Restart `uedcli serve` against WanChai (cold). Record the first `/scene`'s time as the baseline
     solve cost (unaffected by this fix).
  2. Immediately fetch `/atlas` and `/lightmap`. Record their time — should drop sharply vs. today's
     ~2m44s `/atlas` figure.
  3. Make a real trunk edit (`actor move` or similar) and confirm all three endpoints serve correct,
     non-stale post-edit data.

## Self-review — spec Testing-section coverage

- "One trunk-read + one build_scene/resolve_actor_sprites call each, three routes, unchanged trunk"
  → Task 4 Step 1.
- "A trunk change invalidates BOTH slots, next request rebuilds both fully" → Task 2 Step 1 (slot-
  level) + Task 4 Step 5 (end-to-end HTTP level).
- "Concurrency test... no torn read within a slot" → Task 6.
- "Generation-guard test — stale mid-build result discarded, not published" → Task 2 Step 5.
- "`_require_level` rejects a syntactically-valid but non-matching level name" → Task 5 Step 1.
- "Existing tests pass with `build_scene_payload`'s new signature" → Task 3 Steps 1/3, Task 4 Step 6.
