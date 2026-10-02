# Plan — share class-defaults and texture-decode caches across `/load`'s mesh/Mover loop

Implements [`spec.md`](spec.md) (reviewed 8 rounds — see spec's own commit history for the fix
trail). Ephemeral scratch; nothing here needs folding into a durable doc afterward (a self-contained
perf fix, not new architecture or a UnrealEd finding).

Two independent changes, per the spec's own split:

- **Universal, no signature change from any external caller's view**: `resolve_mesh_actor_polys`
  builds ONE shared `TextureResolver` for its whole call instead of `resolve_skins` building a
  fresh one per actor. Applies to `uedcli serve`'s `/load` AND `build_scene`'s `level photo
  --native` path automatically.
- **Scoped, new required parameter on the two `uedcli serve`-specific entry points**: a shared
  `ClassDefaults` threads down to `_mesh_actor_polys`/`resolve_mover_actor_polys`'s `_hidden`
  closure, replacing their bare `resolve_class_defaults(...)` calls. `build_scene`'s own calls pass
  none (an optional param there), keeping today's per-actor behavior for `level photo --native`.

All line numbers below are current as of this plan's own commit (spec at `5b7f9d34`+ fixups through
`dfc3cc8a`, all in this same worktree's history).

## Build order (each step: write/extend the test, watch it fail, implement, watch it pass, commit)

### Step 0 — `resolve_skins` accepts a pre-built resolver

**Files:** Modify `uedcli/meshrender.py:106-150`.

Change:

```python
def resolve_skins(mesh, pkg, defaults, search_files, *, class_fqcn: str, class_index=None) -> dict:
```

to:

```python
def resolve_skins(mesh, pkg, defaults, search_files, *, class_fqcn: str, class_index=None,
                  resolver=None) -> dict:
```

and change line 150:

```python
    resolver = utexture.TextureResolver(list(search_files), class_index=class_index)
```

to:

```python
    if resolver is None:
        resolver = utexture.TextureResolver(list(search_files), class_index=class_index)
```

Add one sentence to the docstring (after the existing `search_files` paragraph, ~line 137): "`resolver`,
if given, is used AS-IS instead of building a new one — the caller's own shared `TextureResolver`
across a whole mesh-actor loop, so N actors referencing the same texture decode it once, not once
per actor (board `load-resolves-mesh-class-defaults-and-texture`)."

No test of its own — covered by step 1's test (this function has exactly two call sites,
`preview_native.py:360` and `cli/commands/classes.py:212`; the second passes no `resolver`, so it
is unaffected — verify this after step 1, not here in isolation).

- [ ] **Step 0.1: implement the signature + gate change above.**
- [ ] **Step 0.2: run `uedcli/tests/test_meshrender.py` (the file with `resolve_skins`'s own direct
  tests) to confirm no regression from the signature change alone.**

  Run: `bin/test uedcli/tests/test_meshrender.py -q`
  Expected: all green, unchanged — no test there passes `resolver=`, so every one hits the
  `if resolver is None` branch exactly as before.

- [ ] **Step 0.3: commit.**

```bash
git add uedcli/meshrender.py
git commit -m "meshrender: resolve_skins accepts a pre-built TextureResolver"
```

### Step 1 — `_mesh_actor_polys` accepts a shared `class_defaults` and `texture_resolver`

**Files:** Modify `uedcli/preview_native.py:294-360`.

**Interfaces:**
- Consumes: `resolve_skins`'s new `resolver=` kwarg (step 0).
- Produces: `_mesh_actor_polys(actor, index, search_files, *, hidden_prop="bhidden",
  class_defaults=None, texture_resolver=None)` — the two new params, both optional, both `None`
  by default (identical behavior to today when omitted).

Change the signature (line 294):

```python
def _mesh_actor_polys(actor, index, search_files, *, hidden_prop: str = "bhidden"
                      ) -> tuple[list, dict, object, tuple[str, str] | None, dict]:
```

to:

```python
def _mesh_actor_polys(actor, index, search_files, *, hidden_prop: str = "bhidden",
                      class_defaults=None, texture_resolver=None
                      ) -> tuple[list, dict, object, tuple[str, str] | None, dict]:
```

Add to the docstring (after the existing `hidden_prop` paragraph): "`class_defaults`, if given (a
`classdefaults.ClassDefaults`), resolves this actor's class defaults through its shared per-class
memo instead of a fresh `resolve_class_defaults` call — the same substitution
`resolve_actor_sprites` already makes (`preview_native.py:612`). `texture_resolver`, if given, is
forwarded to `resolve_skins` as its own new `resolver` param — one `TextureResolver` shared across
every actor `resolve_mesh_actor_polys` calls this for, instead of a fresh one per actor. Both
default to `None` (today's per-actor-fresh behavior) for `build_scene`'s own callers, which pass
neither (board `load-resolves-mesh-class-defaults-and-texture`)."

Change line 327:

```python
    defaults = resolve_class_defaults(actor.cls, resolver=index.resolver())
```

to:

```python
    defaults = (class_defaults.for_class(actor.cls).defaults if class_defaults is not None
               else resolve_class_defaults(actor.cls, resolver=index.resolver()))
```

Change the `resolve_skins` call (lines 360-361):

```python
        skins = meshrender.resolve_skins(mesh, pkg, skin_defaults, search_files,
                                         class_fqcn=actor.cls, class_index=index)
```

to:

```python
        skins = meshrender.resolve_skins(mesh, pkg, skin_defaults, search_files,
                                         class_fqcn=actor.cls, class_index=index,
                                         resolver=texture_resolver)
```

- [ ] **Step 1.1: write the failing tests.**

Add to `uedcli/tests/test_preview_native.py` (this file already imports `ClassDefaults`,
`ClassIndex`, has `MESH_CLASS`/`_ued22_index`/`_mesh_sf`/`DEFAULTS`/`_defaults_resolver` — reuse
them):

```python
def test_mesh_actor_polys_reuses_a_shared_class_defaults_when_given():
    """`_mesh_actor_polys` must resolve through the caller's `ClassDefaults` memo when given one,
    not re-derive its own -- the exact substitution `resolve_actor_sprites` already makes."""
    from uedcli import uprops
    index = _ued22_index()
    fresh_defaults = ClassDefaults(_defaults_resolver)
    crate = Actor(name="Crate", cls=MESH_CLASS, location=(Decimal(0), Decimal(0), Decimal(0)))
    tris, _skins, _mesh, _ref, defaults = pn._mesh_actor_polys(
        crate, index, _mesh_sf(index), class_defaults=fresh_defaults)
    assert tris
    assert fresh_defaults.resolutions == 1
    # a second actor of the SAME class reuses the memo -- resolutions stays at 1
    crate2 = Actor(name="Crate2", cls=MESH_CLASS, location=(Decimal(200), Decimal(0), Decimal(0)))
    pn._mesh_actor_polys(crate2, index, _mesh_sf(index), class_defaults=fresh_defaults)
    assert fresh_defaults.resolutions == 1
    # the returned defaults dict is the SAME shape resolve_class_defaults returns directly
    assert defaults == uprops.resolve_class_defaults(MESH_CLASS, resolver=index.resolver())


def test_mesh_actor_polys_reuses_a_shared_texture_resolver_when_given():
    """A shared `TextureResolver` passed in must be the one `resolve_skins` actually uses, not
    discarded in favor of building its own -- proven by a spy on `TextureResolver.resolve`."""
    from uedcli import utexture
    index = _ued22_index()
    resolver = utexture.TextureResolver(_mesh_sf(index), class_index=index)
    calls = []
    real_resolve = utexture.TextureResolver.resolve
    def _spy(self, ref):
        if self is resolver:
            calls.append(ref)
        return real_resolve(self, ref)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(utexture.TextureResolver, "resolve", _spy)
        crate = Actor(name="Crate", cls=MESH_CLASS, location=(Decimal(0), Decimal(0), Decimal(0)))
        _tris, skins, _mesh, _ref, _defaults = pn._mesh_actor_polys(
            crate, index, _mesh_sf(index), texture_resolver=resolver)
    assert skins            # sanity: the crate really has a resolvable skin
    assert calls            # the SHARED resolver's own .resolve was actually hit
```

- [ ] **Step 1.2: run them, verify they fail.**

Run: `bin/test uedcli/tests/test_preview_native.py -k "reuses_a_shared" -q`
Expected: `test_mesh_actor_polys_reuses_a_shared_class_defaults_when_given` FAILS
(`TypeError: _mesh_actor_polys() got an unexpected keyword argument 'class_defaults'`) — same for
the texture-resolver test with `texture_resolver` — or both skip cleanly if the committed corpus is
missing on this host, in which case treat the code review + full-suite run as the real gate.

- [ ] **Step 1.3: implement the three changes above (signature, docstring, the two call-site
  edits).**
- [ ] **Step 1.4: run the tests again, verify they pass.**

Run: `bin/test uedcli/tests/test_preview_native.py -k "reuses_a_shared" -q`
Expected: both PASS.

- [ ] **Step 1.5: commit.**

```bash
git add uedcli/preview_native.py uedcli/tests/test_preview_native.py
git commit -m "preview_native: _mesh_actor_polys accepts a shared class_defaults/texture_resolver"
```

### Step 2 — `resolve_mesh_actor_polys` builds one shared resolver, unconditionally, for every caller

**Files:** Modify `uedcli/preview_native.py:369-402`.

**Interfaces:**
- Produces: `resolve_mesh_actor_polys(level, index, search_files, *, hidden_prop, textures,
  in_solid=None, class_defaults=None)` — one new optional param (`class_defaults`); the
  `TextureResolver` hoist below is NOT a new parameter, it is purely internal.

Change the signature (line 369):

```python
def resolve_mesh_actor_polys(level, index, search_files, *, hidden_prop: str, textures: _TextureTable,
                             in_solid=None) -> list[tuple[tuple, tuple[str, None]]]:
```

to:

```python
def resolve_mesh_actor_polys(level, index, search_files, *, hidden_prop: str, textures: _TextureTable,
                             in_solid=None, class_defaults=None
                             ) -> list[tuple[tuple, tuple[str, None]]]:
```

Add to the docstring (after the `in_solid` paragraph): "Builds ONE shared `TextureResolver` for the
whole call (when `search_files` is non-empty), matching `resolve_actor_sprites`'s own one-resolver-
per-call pattern (`preview_native.py:602`) instead of `resolve_skins` building a fresh one per
actor — applies to EVERY caller unconditionally (`build_scene` included), since this needs no
external dependency beyond `search_files`, which this function already takes. `class_defaults`, if
given, forwards into every `_mesh_actor_polys` call — `build_scene`'s own calls pass none, keeping
today's per-actor `resolve_class_defaults` behavior there (board
`load-resolves-mesh-class-defaults-and-texture`)."

Change the body (lines 394-402):

```python
    from . import meshworld, typedprops
    from .transform import DegenerateTransformError, flip_winding, reject_degenerate

    out: list[tuple[tuple, tuple[str, None]]] = []
    for actor in level.actors.values():
        if actor.brush is not None:
            continue                                     # brushes/movers handled by the caller
        tris, skins, mesh, mesh_ref, mesh_class_defaults = _mesh_actor_polys(
            actor, index, search_files, hidden_prop=hidden_prop)
```

to:

```python
    from . import meshworld, typedprops
    from .transform import DegenerateTransformError, flip_winding, reject_degenerate

    shared_resolver = (TextureResolver(list(search_files), class_index=index)
                      if search_files else None)
    out: list[tuple[tuple, tuple[str, None]]] = []
    for actor in level.actors.values():
        if actor.brush is not None:
            continue                                     # brushes/movers handled by the caller
        tris, skins, mesh, mesh_ref, mesh_class_defaults = _mesh_actor_polys(
            actor, index, search_files, hidden_prop=hidden_prop, class_defaults=class_defaults,
            texture_resolver=shared_resolver)
```

(`TextureResolver` is already imported at module level, `preview_native.py:42` — no new import.)

- [ ] **Step 2.1: write the failing test.**

Add to `uedcli/tests/test_preview_native.py`:

```python
def test_resolve_mesh_actor_polys_decodes_a_shared_skin_once_not_per_actor():
    """The whole point of the fix: TWO actors of the same class/mesh in ONE
    `resolve_mesh_actor_polys` call must decode the shared skin texture once, not twice."""
    from collections import Counter
    from uedcli import utexture
    index = _ued22_index()
    calls: list[str] = []
    real_decode = utexture.TextureResolver._decode_ref
    def _counting_decode(self, ref):
        calls.append(ref)
        return real_decode(self, ref)
    textures = pn._TextureTable(resolver=None)
    one = Actor(name="Crate1", cls=MESH_CLASS, location=(Decimal(0), Decimal(0), Decimal(0)))
    two = Actor(name="Crate2", cls=MESH_CLASS, location=(Decimal(200), Decimal(0), Decimal(0)))
    level = _level(one, two)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(utexture.TextureResolver, "_decode_ref", _counting_decode)
        resolved = pn.resolve_mesh_actor_polys(level, index, _mesh_sf(index),
                                               hidden_prop="bhiddened", textures=textures)
    assert resolved                              # sanity: both actors actually contributed triangles
    counts = Counter(calls)
    assert counts and max(counts.values()) == 1  # every distinct ref decoded exactly once
```

- [ ] **Step 2.2: run it, verify it fails** (today: `max(counts.values()) == 2`, one decode per
  actor for the shared skin).

Run: `bin/test uedcli/tests/test_preview_native.py -k decodes_a_shared_skin_once -q`

- [ ] **Step 2.3: implement the signature/docstring/body changes above.**
- [ ] **Step 2.4: run it again, verify it passes.**
- [ ] **Step 2.5: run the full `test_preview_native.py` file — this function is `build_scene`'s own
  mesh path too, so a regression here would show up broadly.**

Run: `bin/test uedcli/tests/test_preview_native.py -q`
Expected: all green, including `test_two_instances_of_one_mesh_class_share_one_texture_slot` (the
existing test this change's docstring explicitly targets — still must pass unchanged, since the
TEXTURE TABLE dedup it tests is a different, already-correct layer from the DECODE dedup this fix
adds).

- [ ] **Step 2.6: commit.**

```bash
git add uedcli/preview_native.py uedcli/tests/test_preview_native.py
git commit -m "preview_native: resolve_mesh_actor_polys shares one TextureResolver for its whole call"
```

### Step 3 — `resolve_mover_actor_polys`'s `_hidden` closure accepts a shared `class_defaults`

**Files:** Modify `uedcli/preview_native.py:222-249`.

Change the signature (line 222):

```python
def resolve_mover_actor_polys(level, index, *, textures: _TextureTable,
                              hidden_prop: str | None = None
                              ) -> list[tuple[tuple, tuple[str, int]]]:
```

to:

```python
def resolve_mover_actor_polys(level, index, *, textures: _TextureTable,
                              hidden_prop: str | None = None, class_defaults=None
                              ) -> list[tuple[tuple, tuple[str, int]]]:
```

Add one sentence to the docstring (after the `hidden_prop` paragraph): "`class_defaults`, if given,
resolves a hidden Mover's class default through the shared memo instead of a fresh
`resolve_class_defaults` call per Mover — `build_scene`'s own call passes none (board
`load-resolves-mesh-class-defaults-and-texture`)."

Change `_hidden` (lines 242-249) — note the LOCAL variable renames from `class_defaults` to
`defaults` to avoid shadowing the new outer parameter of the same name:

```python
    def _hidden(actor) -> bool:
        if hidden_prop is None:
            return False
        class_defaults = resolve_class_defaults(actor.cls, resolver=index.resolver())
        instance = {k.casefold(): v for k, v in actor.props}
        value = instance[hidden_prop] if hidden_prop in instance else class_defaults.get(
            (hidden_prop, 0))
        return str(value or "False").strip() == "True"
```

to:

```python
    def _hidden(actor) -> bool:
        if hidden_prop is None:
            return False
        defaults = (class_defaults.for_class(actor.cls).defaults if class_defaults is not None
                   else resolve_class_defaults(actor.cls, resolver=index.resolver()))
        instance = {k.casefold(): v for k, v in actor.props}
        value = instance[hidden_prop] if hidden_prop in instance else defaults.get(
            (hidden_prop, 0))
        return str(value or "False").strip() == "True"
```

- [ ] **Step 3.1: write the failing test.**

Add to `uedcli/tests/test_preview_native.py`:

```python
def test_resolve_mover_actor_polys_reuses_a_shared_class_defaults_for_hidden_check():
    """Two Movers of the same class must resolve that class's defaults once, not once per Mover,
    when a shared `ClassDefaults` is given -- `_hidden` computes `defaults` unconditionally for
    EVERY actor it's asked about, whether or not that actor ends up actually hidden (its own
    instance-vs-class-default check happens after, `preview_native.py:247-248`), so this holds even
    though both Movers here are hidden via an INSTANCE override, never touching the class default's
    own value."""
    index = _ued22_index()
    fresh_defaults = ClassDefaults(_defaults_resolver)
    m1 = make_brush_actor("Mover1", cube(64.0, 64.0, 64.0), mover_class="Engine.Mover")
    set_prop(m1, "bHiddenEd", "True")
    m2 = make_brush_actor("Mover2", cube(64.0, 64.0, 64.0), mover_class="Engine.Mover")
    set_prop(m2, "bHiddenEd", "True")
    level = _level(m1, m2)
    textures = pn._TextureTable(resolver=None)
    pn.resolve_mover_actor_polys(level, index, textures=textures, hidden_prop="bhiddened",
                                 class_defaults=fresh_defaults)
    assert fresh_defaults.resolutions == 1
```

(Mirrors `test_movers_are_out_of_world_csg_but_rendered`'s own `make_brush_actor(..., mover_class=
"Engine.Mover")` construction, already used elsewhere in this file, and `set_prop` from
`uedcli.tests.conftest`, already imported at this file's top — both verified present, not new
dependencies.)

- [ ] **Step 3.2-3.5: same fail → implement → pass → commit cycle as steps 1-2.**

```bash
git add uedcli/preview_native.py uedcli/tests/test_preview_native.py
git commit -m "preview_native: resolve_mover_actor_polys accepts a shared class_defaults"
```

### Step 4 — thread `class_defaults` through the two `uedcli serve` entry points

**Files:** Modify `uedcli/preview_native.py:268-291` (`resolve_mover_scene_polys`) and
`uedcli/preview_native.py:457-480` (`resolve_mesh_scene_polys`). Also fix the one existing
production call site that will break: `uedcli/tests/test_serve_scene.py:87-89`
(`_load_and_build_for`'s own calls).

**Interfaces:**
- Produces: `resolve_mesh_scene_polys(level, index, search_files, class_defaults, *,
  hidden_prop="bhiddened")` and `resolve_mover_scene_polys(level, index, search_files,
  class_defaults, *, hidden_prop="bhiddened")` — `class_defaults` REQUIRED (positional, no
  default): these two functions have exactly two real callers in the whole codebase
  (`uedcli/serve/app.py`'s `/load` handler and `_get_trunk`'s bootstrap branch, plus the one test
  helper below) and both already have a `ClassDefaults` in hand — a silent optional default here
  would let a future caller forget to pass it with no error, the exact class of bug this whole item
  exists to fix. Required, not optional, matches this project's "no silent half-answers" convention.

Change `resolve_mover_scene_polys`'s signature (line 268):

```python
def resolve_mover_scene_polys(level, index, search_files, *, hidden_prop: str = "bhiddened"
                              ) -> tuple[list[tuple], list[tuple[str, int]], list[tuple]]:
```

to:

```python
def resolve_mover_scene_polys(level, index, search_files, class_defaults, *,
                              hidden_prop: str = "bhiddened"
                              ) -> tuple[list[tuple], list[tuple[str, int]], list[tuple]]:
```

and its call to `resolve_mover_actor_polys` (line 288):

```python
    resolved = resolve_mover_actor_polys(level, index, textures=textures, hidden_prop=hidden_prop)
```

to:

```python
    resolved = resolve_mover_actor_polys(level, index, textures=textures, hidden_prop=hidden_prop,
                                         class_defaults=class_defaults)
```

Change `resolve_mesh_scene_polys`'s signature (line 457):

```python
def resolve_mesh_scene_polys(level, index, search_files, *, hidden_prop: str = "bhiddened"
                             ) -> tuple[list[tuple], list[tuple[str, None]], list[tuple]]:
```

to:

```python
def resolve_mesh_scene_polys(level, index, search_files, class_defaults, *,
                             hidden_prop: str = "bhiddened"
                             ) -> tuple[list[tuple], list[tuple[str, None]], list[tuple]]:
```

and its call to `resolve_mesh_actor_polys` (lines 476-477):

```python
    resolved = resolve_mesh_actor_polys(level, index, search_files, hidden_prop=hidden_prop,
                                        textures=textures)
```

to:

```python
    resolved = resolve_mesh_actor_polys(level, index, search_files, hidden_prop=hidden_prop,
                                        textures=textures, class_defaults=class_defaults)
```

Add one sentence to each docstring's opening paragraph noting the new required `class_defaults`
param and pointing at `load-resolves-mesh-class-defaults-and-texture`.

**Fix the one call site this breaks**, `uedcli/tests/test_serve_scene.py:87-89`:

```python
    mesh_polys, mesh_owners, mesh_texture_table = resolve_mesh_scene_polys(level, index, search_files)
    mover_polys, mover_owners, mover_texture_table = resolve_mover_scene_polys(
        level, index, search_files)
```

to:

```python
    mesh_polys, mesh_owners, mesh_texture_table = resolve_mesh_scene_polys(
        level, index, search_files, defaults)
    mover_polys, mover_owners, mover_texture_table = resolve_mover_scene_polys(
        level, index, search_files, defaults)
```

(`_load_and_build_for` already takes `defaults` as its own parameter — this is a pure
call-site-signature fix, no new object needed.)

- [ ] **Step 4.1: run the FULL `test_serve_scene.py` file first, before any change, to establish
  which tests currently pass through `_load_and_build_for`** (so step 4.3's "still all green" claim
  is checked against a real baseline, not assumed).

Run: `bin/test uedcli/tests/test_serve_scene.py -q`

- [ ] **Step 4.2: implement the four signature/call-site changes above (both functions' signatures,
  both functions' inner calls, the one test-helper call site).**
- [ ] **Step 4.3: run `test_serve_scene.py` again — must still be fully green** (this step changes
  no behavior, only threads an already-available object through; any new failure here is this
  step's own bug, not an expected/acceptable change).

Run: `bin/test uedcli/tests/test_serve_scene.py -q`
Expected: identical pass/skip counts to step 4.1's baseline.

- [ ] **Step 4.4: commit.**

```bash
git add uedcli/preview_native.py uedcli/tests/test_serve_scene.py
git commit -m "preview_native: resolve_mesh_scene_polys/resolve_mover_scene_polys require class_defaults"
```

### Step 5 — wire `/load`'s already-built `defaults` through in `uedcli/serve/app.py`

**Files:** Modify `uedcli/serve/app.py:277-280` (`_get_trunk`'s bootstrap branch) and
`uedcli/serve/app.py:551-554` (`/load`'s handler).

Change (line 277-280):

```python
                mesh_polys, mesh_owners, mesh_texture_table = resolve_mesh_scene_polys(
                    lvl, index, search_files)
                mover_polys, mover_owners, mover_texture_table = resolve_mover_scene_polys(
                    lvl, index, search_files)
```

to:

```python
                mesh_polys, mesh_owners, mesh_texture_table = resolve_mesh_scene_polys(
                    lvl, index, search_files, defaults)
                mover_polys, mover_owners, mover_texture_table = resolve_mover_scene_polys(
                    lvl, index, search_files, defaults)
```

Change (line 551-554):

```python
        mesh_polys, mesh_owners, mesh_texture_table = resolve_mesh_scene_polys(
            lvl, index, search_files)
        mover_polys, mover_owners, mover_texture_table = resolve_mover_scene_polys(
            lvl, index, search_files)
```

to:

```python
        mesh_polys, mesh_owners, mesh_texture_table = resolve_mesh_scene_polys(
            lvl, index, search_files, defaults)
        mover_polys, mover_owners, mover_texture_table = resolve_mover_scene_polys(
            lvl, index, search_files, defaults)
```

(Both sites already have `defaults` in scope from `_scene_inputs(project)`, and both already pass
it to their neighboring `resolve_actor_sprites(lvl, search_files, defaults)` call one line above —
this is the exact same object, just also threaded to the two calls that were missing it.)

- [ ] **Step 5.1: write the regression test.**

Add to `uedcli/tests/test_serve_load_rebuild.py` (this file already has `_require_ued22`,
`_write_fixture_trunk`, `_index_and_defaults`, `serve_app`, `SimpleNamespace`, `TestClient`,
`cube_room`):

```python
def test_load_resolves_mesh_class_defaults_through_the_shared_memo(tmp_path, monkeypatch):
    """Board `load-resolves-mesh-class-defaults-and-texture`: /load must pass its own already-built
    `defaults` into resolve_mesh_scene_polys/resolve_mover_scene_polys, not let them go without --
    a spy on `ClassDefaults.for_class` proves the SHARED instance actually gets used, not just that
    /load succeeds (which it would even with the old, unfixed signature erroring differently)."""
    from uedcli.classdefaults import ClassDefaults
    _require_ued22()
    index, defaults = _index_and_defaults()
    calls = []
    real_for_class = ClassDefaults.for_class
    def _spy(self, fqcn):
        if self is defaults:
            calls.append(fqcn)
        return real_for_class(self, fqcn)
    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], index, defaults))
    monkeypatch.setattr(ClassDefaults, "for_class", _spy)

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    assert c.post("/api/level/TestLevel/load").status_code == 200
    # `calls` stays empty here, and NOT because cube_room() has no mesh/mover actors -- the mocked
    # `_scene_inputs` above returns `search_files=[]`, and `resolve_mesh_scene_polys`/
    # `resolve_mover_scene_polys` both short-circuit to `return [], [], []` BEFORE their per-actor
    # loop whenever `search_files` is falsy (`preview_native.py:473-474`/`285-286`) -- so
    # `class_defaults.for_class` is never reached regardless of what actors the level has. Adding a
    # mesh actor alone would NOT strengthen this test; it would also need a real, non-empty
    # `search_files` (e.g. the real index's own `package_paths()`), which is a materially bigger
    # fixture change (a real corpus-backed mesh/skin, not just an actor). Deliberately left as a
    # narrower "wiring didn't crash" guard: the real assertion this test makes is that /load's now-
    # required `class_defaults` argument is actually wired at both call sites (app.py:277-280/
    # 551-554) -- a TypeError there would 500, not 200, and the domain-error handler would report
    # it, not silently succeed.
```

- [ ] **Step 5.2: run it, verify it fails.** At this point in the build order, step 4 has already
  landed (`resolve_mesh_scene_polys`/`resolve_mover_scene_polys` now require `class_defaults`) but
  `app.py`'s two call sites haven't been updated yet (that's this step) — so the 3-arg calls there
  now raise `TypeError`, surfaced as a non-200 status through the domain-error handler.

- [ ] **Step 5.3: implement the two call-site edits above.**
- [ ] **Step 5.4: run it again, verify 200.**
- [ ] **Step 5.5: commit.**

```bash
git add uedcli/serve/app.py uedcli/tests/test_serve_load_rebuild.py
git commit -m "serve: /load threads its ClassDefaults into mesh/Mover resolution"
```

### Step 6 — full suite + re-profile

- [ ] Run the whole offline suite once: `bin/test`. Expected: green, modulo the same pre-existing,
  already-catalogued reds this project's other campaign docs track (unrelated board-schema issues
  from concurrent sessions, `test_doc_links`, etc.) — do not chase those here.
- [ ] Re-run `dev/docs/spikes/2026-09-20-mesh-load-perf-profile/profile_load.py` against
  `showcase_bar` and record the new numbers in that spike's `findings.md`, in a new dated section
  below the original (don't overwrite the "before" numbers — they're the baseline this fix is
  measured against). Expected: `resolve_class_defaults`'s ~453 calls collapse toward the level's
  real distinct-class count, `resolve_skins`'s texture-decode calls collapse toward its real
  distinct-skin count, and `/load`'s total wall time drops well below the measured 13.3s baseline
  (exact target not pre-committed here — record whatever the real number is, honestly, even if it's
  a smaller win than hoped; the spec's own "What this fixes and what it doesn't" already flags that
  `class_export_index`/`casefold` overhead may not fully disappear).

### Step 7 — review, land

Follow `dev/docs/rules/building-features.md` steps 3-4: one subagent review of
`git diff master...HEAD` using `dev/docs/rules/reviewer-brief.md` as its context pack; fix confirmed
findings, re-test; `git mv` this item to `done/` and cut its `overview.md`/`spec.md`/`plan.md` down
to a short reference; update the base to `origin`'s latest and squash-merge as one commit; delete
the worktree. Per the user's own instruction for this item: loop review until clean before merging,
same as the spec stage.

## Self-review against the spec

- Spec's "Proposed fix," bullet 1 (`class_defaults` substitution, drop-in shape): ✅ steps 1/3
  implement it exactly as specified, with the `_hidden` closure's local-variable rename the spec
  didn't need to call out but this plan does (a real implementation detail the spec correctly left
  to the plan).
- Spec's bullet 2 (`resolve_skins`'s optional `resolver`): ✅ step 0, both real call sites
  (`preview_native.py:360`, `cli/commands/classes.py:212`) accounted for — the second untouched, as
  specified.
- Spec's bullet 3 (unconditional `TextureResolver` hoist in `resolve_mesh_actor_polys`, universal,
  no external signature change): ✅ step 2 — the internal `_mesh_actor_polys` parameter this
  requires (step 1) is the "internal, not external" distinction the spec's own review history
  insisted on stating plainly; this plan states it in both step 1 and step 2's docstring text.
- Spec's bullets 4-5 (`class_defaults` required on the two `serve` entry points, `/load` wiring):
  ✅ steps 4-5, including the one test-helper call site (`test_serve_scene.py`) the spec's own
  "Where to look" didn't name but this plan found by grepping for every real call site before
  writing the signature change — a plan-stage discovery, not a spec gap (the spec's job was the
  design, not enumerating every test call site).
- Spec's explicit non-goals (build_scene's `class_defaults` half untouched, `/rebuild`'s
  `_build_and_publish_geometry` moot via its own `include_meshes=False`/`include_movers=False`,
  `class preview` untouched by either half, `find_sky_actor`/`render_shots` out of scope): ✅ no
  step above touches any of these; step 2's `TextureResolver` hoist is the one deliberately
  UNIVERSAL change and applies to `build_scene` too, exactly as specified.
- Placeholder scan: none — step 2.1's test went through a self-review pass during this plan's own
  drafting (an earlier version had loose/redundant assertions; replaced with the tight
  `Counter`-based version now in the plan, no scratch left behind). Step 3.1's Mover fixture
  (`make_brush_actor(..., mover_class="Engine.Mover")` + `set_prop`) is verified against this
  file's own existing `test_movers_are_out_of_world_csg_but_rendered` and confirmed both helpers
  are already imported — no open fixture question left for the executor.
- Type/shape consistency: `resolve_mesh_scene_polys`/`resolve_mover_scene_polys`'s new
  `class_defaults` parameter is positional (not keyword-only) in both, consistently, and both call
  sites (steps 4/5) pass it positionally the same way.
