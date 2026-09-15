"""`uedcli serve`'s scene endpoint assembly (plan Task 2): trunk → `ScenePayload`, reusing
`preview_native.build_scene` + `preview_cache` for the solve and joining actor metadata fresh.
Mirrors `test_preview_native.py`'s fixture pattern: a `ClassDefaults`/`ClassIndex` over the
git-tracked `uned/UED22/*.u`, skipped when that corpus is absent."""
from __future__ import annotations

import glob
import os
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from uedcli import config, trunk
from uedcli.classdefaults import ClassDefaults
from uedcli.classindex import ClassIndex
from uedcli.model import Actor, Level
from uedcli.preview_native import build_scene, resolve_actor_sprites
from uedcli.tests.conftest import cube_room

uedcli_native = pytest.importorskip("uedcli_native")

FIXTURES = Path(__file__).parent / "fixtures"
UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"

pytestmark = pytest.mark.skipif(
    not (UED22 / "Engine.u").is_file(),
    reason="committed UED22/Engine.u not present (build_scene's lighting needs real class schemas)")


def _defaults_resolver(name: str) -> str | None:
    p = UED22 / f"{name}.u"
    return str(p) if p.is_file() else None


DEFAULTS = ClassDefaults(_defaults_resolver)


def _ued22_index() -> ClassIndex:
    """A real `ClassIndex` over the committed UED22 corpus — needed for every `build_scene_payload`
    call (not just a level with a non-brush actor): `movers.is_mover` (used to classify brush actors
    for the selection highlight) and `resolve_actor_sprites`/`build_scene`'s own class resolution
    need a real resolver, which the offline `StubClassIndex` doesn't implement."""
    files = [(os.path.splitext(os.path.basename(f))[0], f) for f in glob.glob(str(UED22 / "*.u"))]
    return ClassIndex.from_files(files)


def _write_fixture_trunk(tmp_path) -> tuple:
    """A tiny project (`<tmp>/proj/maps/TestLevel/`) holding one subtract room brush — the
    small/already-cached fixture the plan calls for (NOT UNATCO: a cold solve is ~24s)."""
    root = tmp_path / "proj"
    maps_dir = root / "maps" / "TestLevel"
    maps_dir.mkdir(parents=True)
    room = cube_room()
    level = Level(actors={room.name: room}, order=[room.name])
    trunk.write_level(maps_dir, level, {room.name: "m"})
    project = SimpleNamespace(root=str(root), maps=None)
    return project, "TestLevel"


def _load_and_build_for(project, level_name, index, defaults, search_files):
    """Task 3: `build_scene_payload` no longer loads or builds anything itself -- it takes an
    already-built `_LoadedTrunk`/`_BuiltGeometry` pair. This does, by hand, exactly what `app.py`'s
    `_get_trunk()`/`_get_geometry()` do in production, so these tests still exercise the real
    `trunk.read_level_with_bodies` / `build_scene` / `resolve_actor_sprites` call chain, just via
    the pre-built-pieces call site the shared cache uses."""
    from uedcli.serve.scene import _BuiltGeometry, _LoadedTrunk

    maps_dir = Path(config.project_maps_dir(project))
    level, ranks, _bodies, folders = trunk.read_level_with_bodies(maps_dir / level_name)
    polys, texture_table, owners = build_scene(level, search_files, index, defaults=defaults,
                                               project=project, level_name=level_name,
                                               visibility="editor")
    sprite_table, actor_sprites = resolve_actor_sprites(level, search_files, defaults)
    trunk_state = _LoadedTrunk(level=level, ranks=ranks, folders=folders,
                               sprite_table=sprite_table, actor_sprites=actor_sprites)
    geometry = _BuiltGeometry(geom_hash=None, light_hash=None, polys=polys,
                              texture_table=texture_table, owners=owners)
    return trunk_state, geometry


def test_build_scene_payload_has_polys_and_actors(tmp_path):
    from uedcli.serve.scene import build_scene_payload

    project, level_name = _write_fixture_trunk(tmp_path)
    # A real index, not `IDX` (`StubClassIndex`): every actor's `bHiddenEd` now resolves its class
    # default when unstated (owner ruling 2026-09-14's GUI filter, `scene.py::_is_hidden_ed`), even
    # a plain brush -- `StubClassIndex` has no `.resolver()`.
    index = _ued22_index()
    trunk_state, geometry = _load_and_build_for(project, level_name, index, DEFAULTS, [])
    payload = build_scene_payload(trunk_state, geometry, index, DEFAULTS)

    assert payload.polys
    for poly in payload.polys:
        assert poly.tex_index == -1 or poly.tex_index >= 0    # -1: untextured (flat grey), else in range

    names = {a.name for a in payload.actors}
    assert names == {"Room"}
    room_actor = next(a for a in payload.actors if a.name == "Room")
    assert room_actor.cls == "Engine.Brush" or "Brush" in room_actor.cls
    assert room_actor.bbox_lo != room_actor.bbox_hi           # a real, non-degenerate box
    assert room_actor.order_value == "m"
    assert isinstance(room_actor.props, list)                 # the inspector's raw T3D property set
    assert all(len(p) == 2 for p in room_actor.props)

    # Bug 2: every brush actor ships its own authored (pre-CSG) polys + CSG colour for the
    # selection highlight -- `cube_room()` is a plain CSG_Subtract room, so "subtract"/gold.
    assert room_actor.brush is not None
    assert room_actor.brush.csg_class == "subtract"
    assert room_actor.brush.color == (225, 170, 40)
    assert room_actor.brush.polys and all(len(p) % 3 == 0 and len(p) >= 9 for p in room_actor.brush.polys)

    # Bug 1: every poly is joined back to its owning actor (not anonymous) -- the fixture has
    # exactly one brush actor, so every poly's owner is "Room".
    assert {p.owner for p in payload.polys} == {"Room"}


def test_build_scene_payload_categories_stub_index_fallback():
    """The offline-index fallback path (plan Task 1): `StubClassIndex` has no `.resolver()` at all,
    so `_class_category_map` returns None and every one of the actor's stored props degrades to
    `_FALLBACK_CATEGORY` ("Uncategorized") -- never a crash. `build_scene_payload` is pure (Task 3
    of the shared-cache plan already merged to master), so this hand-builds a minimal
    `_LoadedTrunk`/`_BuiltGeometry` pair instead of running a real CSG solve -- no geometry is
    needed to exercise the categorization path. `defaults` is the real UED22 `ClassDefaults`
    (unrelated to `index`: `_is_hidden_ed` resolves off `defaults`, never `index`), so this isolates
    the index-only fallback the plan means to test."""
    from uedcli.serve.scene import _BuiltGeometry, _FALLBACK_CATEGORY, _LoadedTrunk, build_scene_payload
    from uedcli.tests.conftest import StubClassIndex

    room = cube_room()
    level = Level(actors={room.name: room}, order=[room.name])
    trunk_state = _LoadedTrunk(level=level, ranks={room.name: "m"}, folders={room.name: None},
                               sprite_table=[], actor_sprites={})
    geometry = _BuiltGeometry(geom_hash=None, light_hash=None, polys=[], texture_table=[], owners=[])

    payload = build_scene_payload(trunk_state, geometry, StubClassIndex(), DEFAULTS)

    room_actor = next(a for a in payload.actors if a.name == "Room")
    assert room_actor.props                              # non-empty, else the next assert is vacuous
    assert len(room_actor.categories) == len(room_actor.props)
    assert all(c == _FALLBACK_CATEGORY for c in room_actor.categories)


def test_build_scene_payload_categories_from_real_schema(tmp_path):
    """A resolvable class's stored props get their real UnrealEd categories, live-verified against
    the committed `uned/UED22` corpus. `cube_room()`'s actual stored props are `CsgOper`/`Brush`
    (`make_brush_actor` only appends `PolyFlags` `if poly_flags:`, default 0 -- `PolyFlags` is never
    stored). `CsgOper` resolves to `Engine.Brush`'s own bare-`var()` category `"Brush"`; `Brush` is a
    plain (non-`var()`) property on `Engine.Actor` with no category (`Prop.category is None`), so it
    falls back to `_FALLBACK_CATEGORY`."""
    from uedcli.serve.scene import _FALLBACK_CATEGORY, build_scene_payload

    project, level_name = _write_fixture_trunk(tmp_path)
    index = _ued22_index()
    trunk_state, geometry = _load_and_build_for(project, level_name, index, DEFAULTS, [])
    payload = build_scene_payload(trunk_state, geometry, index, DEFAULTS)

    room_actor = next(a for a in payload.actors if a.name == "Room")
    assert [k for k, _ in room_actor.props] == ["CsgOper", "Brush"]
    assert room_actor.categories == ["Brush", _FALLBACK_CATEGORY]


def test_build_scene_payload_filters_bhiddened_actors_and_keeps_bhidden_ones(tmp_path):
    """Owner ruling 2026-09-14: the GUI hides `bHiddenEd` actors and ignores `bHidden` entirely --
    the opposite of `level photo --native`. Both test actors are bare POINT actors (no brush, no
    mesh) so this proves the filter covers `ScenePayload.actors` itself, not just rendered geometry
    -- `markers.ts` builds its fallback markers straight off this list, so an excluded actor here
    means no marker in the GUI either."""
    from uedcli.serve.scene import build_scene_payload

    root = tmp_path / "proj"
    maps_dir = root / "maps" / "TestLevel"
    maps_dir.mkdir(parents=True)
    room = cube_room()
    hidden_ed = Actor(name="HiddenEdLight", cls="Engine.Light",
                      location=(Decimal(0), Decimal(0), Decimal(0)), props=[("bHiddenEd", "True")])
    hidden_gameplay_only = Actor(name="GameplayHiddenLight", cls="Engine.Light",
                                 location=(Decimal(0), Decimal(0), Decimal(0)),
                                 props=[("bHidden", "True")])
    level = Level(actors={room.name: room, hidden_ed.name: hidden_ed,
                         hidden_gameplay_only.name: hidden_gameplay_only},
                 order=[room.name, hidden_ed.name, hidden_gameplay_only.name])
    trunk.write_level(maps_dir, level,
                      {room.name: "m", hidden_ed.name: "n", hidden_gameplay_only.name: "o"})
    project = SimpleNamespace(root=str(root), maps=None)

    index = _ued22_index()
    trunk_state, geometry = _load_and_build_for(project, "TestLevel", index, DEFAULTS, [])
    payload = build_scene_payload(trunk_state, geometry, index, DEFAULTS)

    names = {a.name for a in payload.actors}
    assert "HiddenEdLight" not in names             # bHiddenEd: dropped from the GUI entirely
    assert "GameplayHiddenLight" in names           # bHidden alone: the GUI still shows it


def test_build_scene_payload_resolves_actor_sprite_from_real_texture(tmp_path):
    """A non-brush actor's `DT_Sprite` `Texture` resolves into `SceneActor.sprite` -- the real
    icon texture (here a fixture `.utx` export), not the client's invented per-class marker colour.
    `tex_index` lands in the SAME atlas table every world poly uses (`build_scene_payload` offsets
    it by `len(texture_table)`)."""
    from uedcli.serve.scene import build_scene_payload

    root = tmp_path / "proj"
    maps_dir = root / "maps" / "TestLevel"
    maps_dir.mkdir(parents=True)
    room = cube_room()
    light = Actor(name="Light0", cls="Engine.Light", location=(Decimal(0), Decimal(0), Decimal(0)),
                  props=[("DrawType", "DT_Sprite"),
                        ("Texture", "Texture'LUM_InfoPortraits.ArthurCallaway'"),
                        ("DrawScale", "1.0")])
    level = Level(actors={room.name: room, light.name: light}, order=[room.name, light.name])
    trunk.write_level(maps_dir, level, {room.name: "m", light.name: "n"})
    project = SimpleNamespace(root=str(root), maps=None)

    index = _ued22_index()
    search_files = [str(FIXTURES / "LUM_InfoPortraits.utx")]
    trunk_state, geometry = _load_and_build_for(project, "TestLevel", index, DEFAULTS, search_files)
    payload = build_scene_payload(trunk_state, geometry, index, DEFAULTS)

    light_actor = next(a for a in payload.actors if a.name == "Light0")
    assert light_actor.sprite is not None
    assert light_actor.sprite.tex_index >= 0
    assert (light_actor.sprite.width, light_actor.sprite.height) == (64.0, 64.0)

    room_actor = next(a for a in payload.actors if a.name == "Room")
    assert room_actor.sprite is None            # a brush actor never carries a sprite


def test_build_scene_payload_actor_sprite_none_without_dt_sprite(tmp_path):
    """A non-brush actor whose (instance) `DrawType` isn't `DT_Sprite` gets `sprite: None` --
    the client falls back to its generic grey marker dot for it."""
    from uedcli.serve.scene import build_scene_payload

    root = tmp_path / "proj"
    maps_dir = root / "maps" / "TestLevel"
    maps_dir.mkdir(parents=True)
    room = cube_room()
    plain = Actor(name="Note0", cls="Engine.Light", location=(Decimal(0), Decimal(0), Decimal(0)),
                 props=[("DrawType", "DT_None")])
    level = Level(actors={room.name: room, plain.name: plain}, order=[room.name, plain.name])
    trunk.write_level(maps_dir, level, {room.name: "m", plain.name: "n"})
    project = SimpleNamespace(root=str(root), maps=None)

    index = _ued22_index()
    trunk_state, geometry = _load_and_build_for(project, "TestLevel", index, DEFAULTS, [])
    payload = build_scene_payload(trunk_state, geometry, index, DEFAULTS)

    plain_actor = next(a for a in payload.actors if a.name == "Note0")
    assert plain_actor.sprite is None


def test_is_hidden_ed_checks_instance_then_class_default_memo_and_degrades_on_failure():
    """Finding 1/2/3 unit-level pin for `scene._is_hidden_ed` directly (no full CSG solve needed):
    instance override wins; else it reads the class default off the SHARED `ClassDefaults`-shaped
    `defaults` object (`.for_class(cls).defaults`, not a fresh per-actor resolve); an unresolvable
    class degrades to "not hidden" (fail open) with a stderr-ready note, never a raised exception --
    mirrors `cli/rendering.py::_is_hidden_ed`'s own convention."""
    from uedcli.serve.scene import _is_hidden_ed
    from uedcli.uprops import SchemaError

    explicit_hidden = Actor(name="A", cls="Engine.Light", props=[("bHiddenEd", "True")])
    assert _is_hidden_ed(explicit_hidden, None) == (True, None)          # never touches `defaults`

    explicit_visible = Actor(name="B", cls="Engine.Light", props=[("bHiddenEd", "False")])
    assert _is_hidden_ed(explicit_visible, None) == (False, None)

    default_hidden = Actor(name="C", cls="Engine.LevelInfo")
    info = SimpleNamespace(defaults={("bhiddened", 0): "True"})
    fake_defaults = SimpleNamespace(for_class=lambda cls: info)
    assert _is_hidden_ed(default_hidden, fake_defaults) == (True, None)

    unresolvable = Actor(name="D", cls="Engine.Light")
    failing_defaults = SimpleNamespace(
        for_class=lambda cls: (_ for _ in ()).throw(SchemaError("no .u")))
    hidden, note = _is_hidden_ed(unresolvable, failing_defaults)
    assert hidden is False
    assert "D" in note and "schema unavailable" in note and "assuming visible" in note


def test_build_scene_payload_hides_a_bhiddened_add_brushs_own_surfaces(tmp_path):
    """Finding 1: an ADD brush's own rendered CSG surfaces are safe to drop when it's `bHiddenEd` --
    they're that brush's own solid contribution, same disposition as deleting it. The enclosing
    SUBTRACT room is unaffected."""
    from uedcli.builders import cube, make_brush_actor
    from uedcli.serve.scene import build_scene_payload

    root = tmp_path / "proj"
    maps_dir = root / "maps" / "TestLevel"
    maps_dir.mkdir(parents=True)
    room = cube_room()                                            # subtract, not hidden
    pillar = make_brush_actor("Pillar", cube(64.0, 64.0, 64.0), csg="add")
    pillar.props = pillar.props + [("bHiddenEd", "True")]
    level = Level(actors={room.name: room, pillar.name: pillar}, order=[room.name, pillar.name])
    trunk.write_level(maps_dir, level, {room.name: "m", pillar.name: "n"})
    project = SimpleNamespace(root=str(root), maps=None)

    index = _ued22_index()
    trunk_state, geometry = _load_and_build_for(project, "TestLevel", index, DEFAULTS, [])
    payload = build_scene_payload(trunk_state, geometry, index, DEFAULTS)

    assert "Pillar" not in {a.name for a in payload.actors}
    owners = {p.owner for p in payload.polys}
    assert "Pillar" not in owners                                 # its own solid faces are dropped
    assert "Room" in owners                                       # the enclosing room is unaffected


def test_build_scene_payload_keeps_a_bhiddened_subtracts_own_surfaces(tmp_path):
    """Finding 1's flagged risk: a `bHiddenEd` SUBTRACT brush's own surfaces are the WALLS of the
    volume it carved, not a separate solid -- dropping them would open a hole in the built geometry
    with no other brush to supply that face. Only the actor-list entry (and so the selection
    highlight/marker) is hidden; the walls keep rendering."""
    from uedcli.serve.scene import build_scene_payload

    root = tmp_path / "proj"
    maps_dir = root / "maps" / "TestLevel"
    maps_dir.mkdir(parents=True)
    room = cube_room()
    room.props = room.props + [("bHiddenEd", "True")]
    level = Level(actors={room.name: room}, order=[room.name])
    trunk.write_level(maps_dir, level, {room.name: "m"})
    project = SimpleNamespace(root=str(root), maps=None)

    index = _ued22_index()
    trunk_state, geometry = _load_and_build_for(project, "TestLevel", index, DEFAULTS, [])
    payload = build_scene_payload(trunk_state, geometry, index, DEFAULTS)

    assert "Room" not in {a.name for a in payload.actors}         # dropped from the actor list...
    assert payload.polys and {p.owner for p in payload.polys} == {"Room"}   # ...but its walls stay


def test_build_scene_payload_hides_a_bhiddened_movers_own_surfaces(tmp_path):
    """A Mover carries no `CsgOper` prop at all (it never participates in world CSG), so
    `hidden_add_owners`'s `.get("CsgOper", "CSG_Add") == "CSG_Add"` default buckets it with a
    CSG_Add brush -- correctly, since a Mover's own surfaces are its own solid contribution, not a
    wall some other actor's geometry depends on. Only the actor-list/selection/marker visibility
    differs from the CSG_Add case: a Mover renders as its own extra_polys (`_mover_world_polys`),
    not a joined CSG surface, but it's still owner-tagged the same way and still dropped."""
    from uedcli.builders import cube, make_brush_actor
    from uedcli.serve.scene import build_scene_payload

    root = tmp_path / "proj"
    maps_dir = root / "maps" / "TestLevel"
    maps_dir.mkdir(parents=True)
    room = cube_room()                                            # subtract, not hidden
    door = make_brush_actor("Door", cube(64.0, 64.0, 64.0), mover_class="Engine.Mover")
    door.props = door.props + [("bHiddenEd", "True")]
    level = Level(actors={room.name: room, door.name: door}, order=[room.name, door.name])
    trunk.write_level(maps_dir, level, {room.name: "m", door.name: "n"})
    project = SimpleNamespace(root=str(root), maps=None)

    index = _ued22_index()
    trunk_state, geometry = _load_and_build_for(project, "TestLevel", index, DEFAULTS, [])
    payload = build_scene_payload(trunk_state, geometry, index, DEFAULTS)

    assert "Door" not in {a.name for a in payload.actors}
    owners = {p.owner for p in payload.polys}
    assert "Door" not in owners                                   # its own surfaces are dropped
    assert "Room" in owners                                       # the enclosing room is unaffected


def test_build_scene_payload_amortizes_class_resolution_over_repeated_classes(tmp_path):
    """Finding 2 perf regression guard: `_is_hidden_ed`/`resolve_actor_sprites` must resolve a
    repeated class through the SHARED `ClassDefaults` memo, not once per actor -- re-resolving the
    whole schema chain (a package load + Super-chain walk + defaults decode, ~0.1-0.3s cold) per
    actor instead of per DISTINCT class was the exact O(actors) regression this fix removes, and it
    fired even on a full CSG-cache hit."""
    from uedcli.serve.scene import build_scene_payload

    def _resolutions_for(n_lights: int) -> int:
        root = tmp_path / f"proj{n_lights}"
        maps_dir = root / "maps" / "TestLevel"
        maps_dir.mkdir(parents=True)
        room = cube_room()
        lights = [Actor(name=f"Light{i}", cls="Engine.Light",
                        location=(Decimal(0), Decimal(0), Decimal(0))) for i in range(n_lights)]
        level = Level(actors={room.name: room, **{a.name: a for a in lights}},
                     order=[room.name] + [a.name for a in lights])
        ranks = {room.name: "m", **{a.name: f"n{i:03d}" for i, a in enumerate(lights)}}
        trunk.write_level(maps_dir, level, ranks)
        project = SimpleNamespace(root=str(root), maps=None)
        fresh_defaults = ClassDefaults(_defaults_resolver)
        index = _ued22_index()
        trunk_state, geometry = _load_and_build_for(project, "TestLevel", index, fresh_defaults, [])
        build_scene_payload(trunk_state, geometry, index, fresh_defaults)
        return fresh_defaults.resolutions

    # Distinct classes touched (Engine.Brush + Engine.Light) never grows with actor count.
    assert _resolutions_for(5) == _resolutions_for(25)


def test_scene_route_returns_200_with_a_json_safe_payload(tmp_path, monkeypatch):
    """HTTP-level round-trip for the real `/api/level/{level}/scene` route — `build_scene_payload`
    alone (the test above) never round-trips through the actual HTTP/JSON layer, so a shape that
    the JSON encoder can't handle would slip past it. Includes a real light actor so at least one
    poly carries a non-None `lightmap` (a bare brush level never does — `gather_lights` finds
    nothing to bake): `bake_radiance`'s RGB buffer is a plain `list[float]`, already JSON-safe, but
    that is exactly the kind of assumption this test exists to keep honest against the real route
    rather than take on faith. `_scene_inputs` is monkeypatched to an offline (real `ClassIndex`,
    `ClassDefaults`) trio so the test stays hermetic (no real per-user games config needed).

    `/scene` no longer auto-solves (gui-explicit-rebuild plan, Task 2) — a Rebuild is simulated
    directly via `app.state.build_and_publish_geometry` (the same function `POST /rebuild` calls)
    before hitting the route, since this test's whole point is the SOLVED payload's JSON shape."""
    from fastapi.testclient import TestClient

    from uedcli.serve import app as serve_app

    root = tmp_path / "proj"
    maps_dir = root / "maps" / "TestLevel"
    maps_dir.mkdir(parents=True)
    room = cube_room()
    light = Actor(name="Light0", cls="Engine.Light", location=(Decimal(0), Decimal(0), Decimal(0)))
    level = Level(actors={room.name: room, light.name: light}, order=[room.name, light.name])
    trunk.write_level(maps_dir, level, {room.name: "m", light.name: "n"})
    project = SimpleNamespace(root=str(root), maps=None)

    index = _ued22_index()
    monkeypatch.setattr(serve_app, "_scene_inputs", lambda project: ([], index, DEFAULTS))
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    app.state.build_and_publish_geometry([], index, DEFAULTS)

    r = c.get("/api/level/TestLevel/scene")

    assert r.status_code == 200
    body = r.json()
    assert body["polys"] and body["actors"]
    lightmaps = [p["lightmap"] for p in body["polys"]]
    assert any(lm is not None for lm in lightmaps)   # the light actually produced baked radiance
    for lm in lightmaps:
        if lm is not None:
            # The frame only (RGB is stripped -- it ships in the lightmap atlas, not per-poly).
            assert set(lm) == {"origin", "u_step", "v_step", "u_size", "v_size"}
            assert len(lm["origin"]) == 3 and len(lm["u_step"]) == 3 and len(lm["v_step"]) == 3
            assert isinstance(lm["u_size"], int) and isinstance(lm["v_size"], int)
            assert "rgb" not in lm
