# Plan — stop rebuilding `(search_files, index, defaults)` on every `/scene`/`/atlas`/`/lightmap`

Implements [`spec.md`](spec.md) (reviewed twice — see spec history). Ephemeral scratch; nothing here
needs folding into a durable doc afterward (this is a self-contained perf fix inside
`uedcli/serve/app.py`, not new architecture or a UnrealEd finding).

One new process-level cache slot, `_scene_inputs_ref`, whose lifetime is tied to `_trunk_ref`'s own
lifetime (not the process's). `/scene`, `/atlas`, `/lightmap` read from it via a new
`_current_scene_inputs()` accessor instead of calling `_scene_inputs(project)` themselves. `/load`
and `/rebuild` are **not touched** — they keep calling `_scene_inputs(project)` fresh, unconditionally,
exactly as today (spec §3: they genuinely consume a fresh `index`/`defaults` to re-derive real state,
where a stale one could silently produce a wrong result, not just a slow one).

All line numbers below are current as of `f6fda0cd` (the merged spec commit) — `uedcli/serve/app.py`
has not changed since.

## Build order (each step: write the test, watch it fail, implement, watch it pass, commit)

### Step 0 — add the cache slot

**File:** `uedcli/serve/app.py`. No test of its own (a bare list cell); folded into step 1's test.

Insert right after the existing `_trunk_ref` declaration (line 156):

```python
    _trunk_ref: list[_LoadedTrunk | None] = [None]
```

becomes:

```python
    _trunk_ref: list[_LoadedTrunk | None] = [None]
    # `_scene_inputs_ref` caches `(search_files, index, defaults)` for the THREE READ ROUTES ONLY
    # (`/scene`, `/atlas`, `/lightmap`) -- board `gui-serve-rebuilds-classindex-on-every-request`
    # spec's "Proposed fix". Its lifetime is tied to `_trunk_ref`'s, not the process's: stashed
    # only where `_trunk_ref[0]` itself gets (re)assigned (`/load`'s handler, `_get_trunk`'s
    # once-only bootstrap branch below), read by `_current_scene_inputs()`. `/load` and `/rebuild`
    # deliberately do NOT read from this slot -- they call `_scene_inputs()` fresh every time,
    # unchanged, because they genuinely consume a fresh `index`/`defaults` to re-derive real state
    # (the trunk itself; the CSG/lighting solve) where a stale one could silently produce a
    # different, wrong result -- not merely a slower-but-correct one (spec §3).
    _scene_inputs_ref: list[tuple | None] = [None]
```

(No type parameter on the tuple — matches `_get_trunk`'s own `search_files, index, defaults`
parameters two lines below, which are likewise untyped in this file.)

### Step 1 — the accessor, and `_get_trunk`'s bootstrap stash

**Files:**
- Modify: `uedcli/serve/app.py:202-247` (`_get_trunk`, add the accessor just before it)
- Test: `uedcli/tests/test_serve_load_rebuild.py` (new tests, alongside its existing `/load`/`/rebuild`
  coverage — same file, same `_require_ued22()`/`_index_and_defaults()`/`_write_fixture_trunk`
  helpers it already has)

**Interfaces:**
- Produces: `_current_scene_inputs() -> tuple` — a closure inside `create_app`, callable with no
  arguments, returning `(search_files, index, defaults)`. Consumed by step 2's three route edits.

- [ ] **Step 1.1: write the failing tests**

Add to `uedcli/tests/test_serve_load_rebuild.py` (this file already imports `serve_app`, `SimpleNamespace`,
`TestClient`, `cube_room`, and already defines `_require_ued22`, `_write_fixture_trunk`,
`_index_and_defaults` — reuse them, don't redefine):

```python
def test_scene_route_reuses_load_s_scene_inputs_instead_of_rebuilding(tmp_path, monkeypatch):
    """Board `gui-serve-rebuilds-classindex-on-every-request`: /scene must NOT rebuild
    `(search_files, index, defaults)` once /load already built a trunk to pair them with -- a
    plain Reload (POST /load then GET /scene+/atlas+/lightmap) used to call `_scene_inputs()` 4
    times; after the fix it's called exactly once, by /load."""
    _require_ued22()
    index, defaults = _index_and_defaults()
    calls = []

    def _counting_scene_inputs(project):
        calls.append(1)
        return [], index, defaults

    monkeypatch.setattr(serve_app, "_scene_inputs", _counting_scene_inputs)

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    assert c.post("/api/level/TestLevel/load").status_code == 200
    assert len(calls) == 1

    assert c.get("/api/level/TestLevel/scene").status_code == 200
    assert c.get("/api/level/TestLevel/scene").status_code == 200
    assert c.get("/api/level/TestLevel/atlas").status_code == 200
    assert c.get("/api/level/TestLevel/lightmap").status_code == 200

    assert len(calls) == 1   # still just the one call /load made


def test_scene_route_as_the_very_first_request_bootstraps_and_seeds_the_cache(tmp_path, monkeypatch):
    """No /load or /rebuild has ever run -- /scene itself triggers `_get_trunk`'s once-only
    bootstrap branch. That ONE call still rebuilds `_scene_inputs()` (nothing to reuse yet, not a
    regression), but stashes its result so the immediately-following /atlas does NOT."""
    _require_ued22()
    index, defaults = _index_and_defaults()
    calls = []

    def _counting_scene_inputs(project):
        calls.append(1)
        return [], index, defaults

    monkeypatch.setattr(serve_app, "_scene_inputs", _counting_scene_inputs)

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    assert c.get("/api/level/TestLevel/scene").status_code == 200
    assert len(calls) == 1

    assert c.get("/api/level/TestLevel/atlas").status_code == 200
    assert len(calls) == 1   # reused what /scene's own bootstrap just stashed
```

- [ ] **Step 1.2: run them, verify both fail**

Run: `bin/test -k "test_scene_route_reuses_load_s_scene_inputs_instead_of_rebuilding or test_scene_route_as_the_very_first_request_bootstraps_and_seeds_the_cache"`
Expected: both FAIL — `len(calls) == 1` assertions see `4` and `2` respectively (today's
call-every-time behavior), or both skip cleanly if `uedcli_native`/the committed corpus is missing
on this host (`_require_ued22()`), in which case treat the code review + step-4 full-suite run as
the real gate instead of trusting a local pass here.

- [ ] **Step 1.3: implement**

In `uedcli/serve/app.py`, insert the accessor right before `def _get_trunk(...)` (currently line 202):

```python
    def _current_scene_inputs():
        """`(search_files, index, defaults)` for `/scene`/`/atlas`/`/lightmap` only -- reuses
        whatever was built alongside the CURRENT `_trunk_ref[0]` instead of rebuilding a fresh,
        memo-less `ClassIndex`/`ClassDefaults` on every read (board
        `gui-serve-rebuilds-classindex-on-every-request`). Safe because these three routes only
        ever CONSUME an already-cached trunk/payload once warm (`_get_trunk`/`_get_payload` return
        before touching their `index`/`defaults` argument at all) -- reusing the pairing an
        already-warm trunk was built with is exactly as fresh as what they already effectively run
        against today. `/load`/`/rebuild` never call this -- they call `_scene_inputs()` directly,
        unconditionally (see the `_scene_inputs_ref` cache-slot comment above).

        Cold path (`_trunk_ref[0]` still `None` -- nothing to pair with yet, e.g. the very first
        request in the process is one of these three routes, before any `/load`): builds fresh via
        `_scene_inputs()`, same cost as today; not a regression, since there is nothing to reuse
        yet. `_get_trunk`'s own bootstrap branch stashes ITS result into `_scene_inputs_ref` once
        it wins `_trunk_lock`, so a second read route racing behind it reuses that instead of also
        building its own."""
        cached = _scene_inputs_ref[0]
        if cached is not None and _trunk_ref[0] is not None:
            return cached
        return _scene_inputs(project)
```

Then, inside `_get_trunk`'s bootstrap branch, change:

```python
                _trunk_ref[0] = built
                # The AUTOMATIC INITIAL LOAD (spec §"Two independent axes"): this branch only ever
```

to:

```python
                _trunk_ref[0] = built
                _scene_inputs_ref[0] = (search_files, index, defaults)   # seeds _current_scene_inputs too
                # The AUTOMATIC INITIAL LOAD (spec §"Two independent axes"): this branch only ever
```

- [ ] **Step 1.4: run the tests, verify they pass**

Run: `bin/test -k "test_scene_route_reuses_load_s_scene_inputs_instead_of_rebuilding or test_scene_route_as_the_very_first_request_bootstraps_and_seeds_the_cache"`
Expected: both PASS (or both skip, per step 1.2's caveat — not yet a real signal either way until
`/load` is wired in step 2, since the first test's middle assertion needs `/load` to also stash).

- [ ] **Step 1.5: commit**

```bash
git add uedcli/serve/app.py uedcli/tests/test_serve_load_rebuild.py
git commit -m "serve: add _scene_inputs_ref cache slot + _current_scene_inputs accessor"
```

### Step 2 — wire `/load` and the three read routes

**Files:** Modify `uedcli/serve/app.py:481-613` (the `/load`, `/scene`, `/atlas`, `/lightmap` route
bodies) and `uedcli/serve/app.py:413-459` (`switch_level`). No new test file — extends step 1's tests
(the first one only fully passes once `/load` stashes) and adds two more to
`uedcli/tests/test_serve_load_rebuild.py`.

**Interfaces:**
- Consumes: `_current_scene_inputs()` from step 1.

- [ ] **Step 2.1: write the two remaining failing tests**

Add to `uedcli/tests/test_serve_load_rebuild.py`:

```python
def test_rebuild_route_always_calls_scene_inputs_fresh_not_cached(tmp_path, monkeypatch):
    """Guards the deliberate exclusion the spec calls for: unlike /scene/atlas/lightmap, /rebuild
    must keep calling `_scene_inputs()` fresh on every invocation -- it feeds `index`/`defaults`
    straight into a real CSG/lighting solve (`_build_scene`), where a stale schema could silently
    produce a wrong result, not just a slow one. A future change that accidentally routes /rebuild
    through `_current_scene_inputs()` would fail this test."""
    _require_ued22()
    index, defaults = _index_and_defaults()
    calls = []

    def _counting_scene_inputs(project):
        calls.append(1)
        return [], index, defaults

    monkeypatch.setattr(serve_app, "_scene_inputs", _counting_scene_inputs)

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    assert c.post("/api/level/TestLevel/rebuild").status_code == 200
    assert len(calls) == 1
    assert c.post("/api/level/TestLevel/rebuild").status_code == 200
    assert len(calls) == 2   # a second Rebuild calls it again -- never reused


def test_switch_level_clears_the_scene_inputs_cache_too(tmp_path, monkeypatch):
    """`_scene_inputs_ref` must be cleared alongside `_trunk_ref`/`_geometry_ref`/`_payload_ref` on
    a level switch -- otherwise a stale pairing from the OLD level's trunk would leak into the new
    one's first read (it would still be a HARMLESS reuse in practice -- see spec's "Not tied to
    PUT /api/level" -- but this pins the simpler, obviously-correct behavior actually chosen)."""
    _require_ued22()
    index, defaults = _index_and_defaults()
    calls = []

    def _counting_scene_inputs(project):
        calls.append(1)
        return [], index, defaults

    monkeypatch.setattr(serve_app, "_scene_inputs", _counting_scene_inputs)

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    _write_fixture_trunk(root, "Other", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    assert c.post("/api/level/TestLevel/load").status_code == 200
    assert len(calls) == 1

    assert c.put("/api/level", json={"level": "Other"}).status_code == 200
    assert c.get("/api/level/Other/scene").status_code == 200
    assert len(calls) == 2   # the old level's cached pairing was cleared, not reused for the new one
```

- [ ] **Step 2.2: run all four new tests, verify they fail (or the first one's middle assertion does)**

Run: `bin/test -k "test_scene_route_reuses_load_s_scene_inputs_instead_of_rebuilding or test_scene_route_as_the_very_first_request_bootstraps_and_seeds_the_cache or test_rebuild_route_always_calls_scene_inputs_fresh_not_cached or test_switch_level_clears_the_scene_inputs_cache_too"`

Expected: `test_rebuild_route_...` and `test_switch_level_...` FAIL (or skip per the corpus caveat);
`test_scene_route_reuses_...`'s FIRST assertion (`len(calls) == 1` right after `/load`) already
passes from step 1, but its FINAL assertion still fails (`/scene`/`/atlas`/`/lightmap` still each
call `_scene_inputs` themselves, since they're not wired to the accessor yet).

- [ ] **Step 2.3: implement**

In `uedcli/serve/app.py`'s `/load` handler, change:

```python
        _trunk_ref[0] = _LoadedTrunk(level=lvl, ranks=ranks, folders=folders,
                                     sprite_table=sprite_table, actor_sprites=actor_sprites,
                                     mesh_polys=mesh_polys, mesh_owners=mesh_owners,
                                     mesh_texture_table=mesh_texture_table,
                                     mover_polys=mover_polys, mover_owners=mover_owners,
                                     mover_texture_table=mover_texture_table)
        _changes_available[0] = False
```

to:

```python
        _trunk_ref[0] = _LoadedTrunk(level=lvl, ranks=ranks, folders=folders,
                                     sprite_table=sprite_table, actor_sprites=actor_sprites,
                                     mesh_polys=mesh_polys, mesh_owners=mesh_owners,
                                     mesh_texture_table=mesh_texture_table,
                                     mover_polys=mover_polys, mover_owners=mover_owners,
                                     mover_texture_table=mover_texture_table)
        _scene_inputs_ref[0] = (search_files, index, defaults)   # seeds /scene, /atlas, /lightmap
        _changes_available[0] = False
```

In `switch_level`, change:

```python
        _trunk_ref[0] = None
        _geometry_ref[0] = None
        _payload_ref[0] = None
        _changes_available[0] = False
```

to:

```python
        _trunk_ref[0] = None
        _geometry_ref[0] = None
        _payload_ref[0] = None
        _scene_inputs_ref[0] = None
        _changes_available[0] = False
```

In each of `scene()`, `atlas()`, `lightmap()`, change:

```python
        search_files, index, defaults = _scene_inputs(project)
```

to:

```python
        search_files, index, defaults = _current_scene_inputs()
```

**Do NOT touch `/load`'s or `/rebuild`'s own `search_files, index, defaults = _scene_inputs(project)`
line** (lines 491 and 522) — this is the whole point of the exclusion (spec §3); a code reviewer
should flag it as a regression if either changes.

- [ ] **Step 2.4: run all four tests, verify they pass**

Run: `bin/test -k "test_scene_route_reuses_load_s_scene_inputs_instead_of_rebuilding or test_scene_route_as_the_very_first_request_bootstraps_and_seeds_the_cache or test_rebuild_route_always_calls_scene_inputs_fresh_not_cached or test_switch_level_clears_the_scene_inputs_cache_too"`
Expected: all four PASS.

- [ ] **Step 2.5: run the full serve test files this change touches**

Run: `bin/test -k "test_serve_load_rebuild or test_serve_scene or test_serve_switch_level or test_serve_app"`
Expected: all green — no existing test in these files asserts a specific `_scene_inputs` call COUNT
today (only that it gets called, via the `lambda p: (...)` monkeypatches already in the file), so
none should regress; this run is confirming that, not guessing it.

- [ ] **Step 2.6: commit**

```bash
git add uedcli/serve/app.py uedcli/tests/test_serve_load_rebuild.py
git commit -m "serve: /scene, /atlas, /lightmap reuse /load's scene inputs instead of rebuilding"
```

### Step 3 — full suite + exercise it for real

- [ ] Run the whole offline suite once: `bin/test`. Expected: green, modulo the two pre-existing
  reds `NATIVE-MATERIALIZE.md`/campaign docs already note as unrelated
  (`test_doc_links`/`test_native_lit_room_ships_light_export_refs`) if those are still red on this
  worktree's base — do not chase them here.
- [ ] Exercise it for real (the `verify` step `dev/docs/rules/building-features.md` calls for): start
  `uedcli serve` against a real project with a level of nontrivial actor count, open the GUI, click
  Reload once to warm the process, then click Reload again and confirm (via a browser network
  panel, or a quick `time curl` against `/api/level/<level>/scene` right after a `POST .../load`)
  that the second Reload's `/scene`+`/atlas`+`/lightmap` return fast — not exhaustive profiling, just
  confirming the fix actually holds outside the unit tests, per this repo's own verification
  convention for the several no-agent-time GUI fixes already landed this way (e.g. `RadiiOverlays`
  above in `GUI-PARITY.md`, `dev/docs/rules/building-features.md` step 2).

### Step 4 — review, land

Follow `dev/docs/rules/building-features.md` steps 3-4 exactly: one subagent review of
`git diff master...HEAD` using `dev/docs/rules/reviewer-brief.md` as its context pack (not the full
`CLAUDE.md` — this is code, not a process-rule artifact); fix confirmed findings, re-test; `git mv`
this item to `done/` and cut its `overview.md`/`spec.md`/`plan.md` down to a one-line record; update
the base to `origin`'s latest and squash-merge as one commit; delete the worktree.

## Self-review against the spec

- Spec's "What this fixes": ✅ steps 1-2 make `/scene`/`/atlas`/`/lightmap` reuse `/load`'s
  `_scene_inputs()` result — test 1 in step 1 pins the 4-calls-to-1 reduction directly.
  Spec's "What this doesn't fix": ✅ `/load`/`/rebuild` untouched (step 2's rebuild test pins it);
  the first-cold-request cost is unavoidable (step 1's bootstrap test pins that it's still paid
  once, not eliminated, not doubled).
- Spec's `switch_level` clearing: ✅ step 2, pinned by its own test.
- Spec's "open question" (whether `/rebuild` should opportunistically refresh the cache): **not
  implemented** — a deliberate YAGNI call (smallest change that solves the observed problem;
  CLAUDE.md "Don't over-engineer"), not an oversight. If a future session wants it, it's a single
  added line in `/rebuild`'s handler (`_scene_inputs_ref[0] = (search_files, index, defaults)` right
  after its own `_scene_inputs()` call) — not planned here.
- Spec's concurrency note (benign TOCTOU race on the shared `ClassIndex`/`ClassDefaults` memo dicts
  when `/scene`+`/atlas`+`/lightmap` fire concurrently): the spec judged this not worth a lock, only
  a comment. Not added as a separate code comment in the implementation above — folded into
  `_current_scene_inputs()`'s own docstring instead (via "reusing the pairing... is exactly as fresh
  as what they already effectively run against today"), which is where a future reader would look;
  flagging here so a reviewer can judge whether that's enough or wants an explicit standalone note.
- Placeholder scan: none — every step above has literal, complete code (no "add validation" or
  "similar to step N" placeholders).
- Type consistency: `_current_scene_inputs()` returns the same 3-tuple shape
  (`search_files, index, defaults`) every one of the three read routes already unpacks — no rename
  needed at the call sites beyond swapping the right-hand side.
