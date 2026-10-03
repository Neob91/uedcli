"""`serve/trunk_load.py`'s incremental Load (board `incremental-gui-reload-only-re-resolve-actors`).

The contract under test is equivalence: a Load that reuses the previous one must produce the SAME
`_LoadedTrunk` a cold Load of the same tree produces — same polys, same owners, same texture tables,
same table ORDER — after any kind of trunk edit. Everything else (which actors got re-resolved) is
an optimization that only matters because of that.

Fixture level: a subtract room (world CSG, not Load-owned), a `DT_Sprite` point actor, two DT_Mesh
crates sharing one skin, and two Movers carrying DIFFERENT real per-poly textures — one actor per
Load-owned resolver, a shared-texture pair so table dedup is exercised, and a second mover so a
removal can actually drop a texture row rather than leave it referenced."""
from __future__ import annotations

import glob
import os
from decimal import Decimal
from pathlib import Path

import pytest

from uedcli import trunk
from uedcli.classdefaults import ClassDefaults
from uedcli.classindex import ClassIndex
from uedcli.model import Actor, Level
from uedcli.preview_native import (resolve_actor_sprites, resolve_mesh_scene_polys,
                                   resolve_mover_scene_polys)
from uedcli.serve import trunk_load
from uedcli.tests.conftest import cube_room

FIXTURES = Path(__file__).parent / "fixtures"
UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"
MESH_CLASS = "DeusEx.CrateUnbreakableLarge"          # DT_Mesh, same class the preview tests use

pytestmark = pytest.mark.skipif(
    not (UED22 / "Engine.u").is_file(),
    reason="committed UED22/Engine.u not present (the Load-owned resolvers need real schemas)")


def _inputs() -> tuple:
    files = [(os.path.splitext(os.path.basename(f))[0], f) for f in glob.glob(str(UED22 / "*.u"))]
    index = ClassIndex.from_files(files)

    def resolver(name: str) -> str | None:
        p = UED22 / f"{name}.u"
        return str(p) if p.is_file() else None

    search_files = list(index.package_paths()) + [str(FIXTURES / "CoreTexWater.utx"),
                                                  str(FIXTURES / "LUM_InfoPortraits.utx")]
    return search_files, index, ClassDefaults(resolver)


def _crate(name: str, x: float) -> Actor:
    return Actor(name=name, cls=MESH_CLASS, location=(Decimal(x), Decimal(0), Decimal(0)))


def _sprite_actor(name: str = "Light0") -> Actor:
    return Actor(name=name, cls="Engine.Light", location=(Decimal(0), Decimal(0), Decimal(64)),
                 props=[("DrawType", "DT_Sprite"),
                        ("Texture", "Texture'LUM_InfoPortraits.ArthurCallaway'"),
                        ("DrawScale", "1.0")])


def _mover(name: str = "Door", texture: str = "CoreTexWater.dirtywater") -> Actor:
    from uedcli.builders import cube, make_brush_actor
    return make_brush_actor(name, cube(64, 8, 96, texture=texture), mover_class="Engine.Mover")


def _fixture_trunk(tmp_path, *, ranks: dict[str, str] | None = None) -> Path:
    """The fixture level. `ranks` overrides the default name-ordered order_values — pass reversed
    ones to make `level.order` disagree with `level.actors`, which is the only way the two walks in
    `_merge` are distinguishable."""
    d = tmp_path / "TestLevel"
    actors = [cube_room(), _sprite_actor(), _crate("Crate1", 0.0), _crate("Crate2", 96.0),
              _mover(), _mover("Hatch", "CoreTexWater.bluewater")]
    trunk.write_level(d, Level(actors={a.name: a for a in actors},
                               order=[a.name for a in actors]),
                      ranks or {a.name: f"n{i:03d}" for i, a in enumerate(actors)})
    return d


def _write_one(d: Path, actor: Actor, rank: str) -> None:
    """Write a single actor's dir, leaving every other actor's alone — what a uedcli verb does."""
    trunk.write_level(d, Level(actors={actor.name: actor}, order=[actor.name]),
                      {actor.name: rank}, only={actor.name})


def _assert_same_load(incremental, cold) -> None:
    assert list(incremental.level.actors) == list(cold.level.actors)
    assert incremental.level.order == cold.level.order
    assert incremental.ranks == cold.ranks
    assert incremental.folders == cold.folders
    assert incremental.sprite_table == cold.sprite_table
    assert incremental.actor_sprites == cold.actor_sprites
    assert incremental.mesh_polys == cold.mesh_polys
    assert incremental.mesh_owners == cold.mesh_owners
    assert incremental.mesh_texture_table == cold.mesh_texture_table
    assert incremental.mover_polys == cold.mover_polys
    assert incremental.mover_owners == cold.mover_owners
    assert incremental.mover_texture_table == cold.mover_texture_table
    assert incremental.mover_groups == cold.mover_groups


def _reload(d: Path, inputs: tuple, previous):
    """One incremental Load plus a cold Load of the same tree, for `_assert_same_load`."""
    incremental, cache = trunk_load.load_trunk(d, inputs=inputs, previous=previous)
    cold, _ = trunk_load.load_trunk(d, inputs=inputs, previous=None)
    _assert_same_load(incremental, cold)
    return incremental, cache


def test_cold_load_matches_the_resolvers_run_directly(tmp_path):
    """`_LoadedTrunk` must carry exactly what the three resolvers produce over the whole level —
    same rows, same ORDER — which is the reference `_assert_same_load` cannot be: that one compares
    two `_merge` results against each other, so a `_merge` that reordered everything consistently
    would still pass it. Ranks here reverse the actors\' name order, the only arrangement under
    which `_merge`\'s mesh walk (`level.actors`, name order) and its mover walk (`level.order`,
    rank order) are telling apart at all."""
    names = ["Crate1", "Crate2", "Door", "Hatch", "Light0", "Room"]
    reversed_ranks = {n: f"n{i:03d}" for i, n in enumerate(reversed(names))}
    d = _fixture_trunk(tmp_path, ranks=reversed_ranks)
    search_files, index, defaults = inputs = _inputs()

    loaded, _cache = trunk_load.load_trunk(d, inputs=inputs, previous=None)
    assert loaded.level.order == list(reversed(names)) != list(loaded.level.actors)

    level = loaded.level
    sprite_table, actor_sprites = resolve_actor_sprites(level, search_files, defaults)
    mesh_polys, mesh_owners, mesh_table, _g = resolve_mesh_scene_polys(
        level, index, search_files, defaults)
    mover_polys, mover_owners, mover_table, mover_groups = resolve_mover_scene_polys(
        level, index, search_files, defaults)

    assert loaded.sprite_table == sprite_table
    assert loaded.actor_sprites == actor_sprites
    assert loaded.mesh_polys == mesh_polys
    assert loaded.mesh_owners == mesh_owners
    assert loaded.mesh_texture_table == mesh_table
    assert loaded.mover_polys == mover_polys
    assert loaded.mover_owners == mover_owners
    assert loaded.mover_texture_table == mover_table
    assert loaded.mover_groups == mover_groups


def test_cold_load_resolves_every_load_owned_kind(tmp_path):
    """The fixture level really does exercise all three resolvers — otherwise every equivalence
    assertion below would pass on empty tables."""
    d = _fixture_trunk(tmp_path)
    loaded, cache = trunk_load.load_trunk(d, inputs=_inputs(), previous=None)

    assert loaded.actor_sprites and loaded.sprite_table
    assert loaded.mesh_polys and loaded.mesh_texture_table
    assert loaded.mover_polys and loaded.mover_texture_table
    assert {o[0] for o in loaded.mesh_owners} == {"Crate1", "Crate2"}
    assert {o[0] for o in loaded.mover_owners} == {"Door", "Hatch"}
    assert set(cache.renders) == set(loaded.level.actors)


def test_two_identical_crates_share_one_mesh_texture_row(tmp_path):
    """Table dedup is live: two instances of one mesh class resolve to the same skin rows, so the
    merged table is not one copy per actor."""
    d = _fixture_trunk(tmp_path)
    both, _ = trunk_load.load_trunk(d, inputs=_inputs(), previous=None)

    trunk.remove_actor(d, "Crate2")
    one, _ = trunk_load.load_trunk(d, inputs=_inputs(), previous=None)

    assert len(both.mesh_texture_table) == len(one.mesh_texture_table)
    assert len(both.mesh_polys) == 2 * len(one.mesh_polys)


def test_unchanged_reload_is_identical_and_reuses_every_render(tmp_path):
    """Nothing changed on disk: the second Load re-resolves nothing (every actor's render data is
    the SAME object) and still produces the same trunk a cold Load does."""
    d = _fixture_trunk(tmp_path)
    inputs = _inputs()
    _first, cache = trunk_load.load_trunk(d, inputs=inputs, previous=None)

    _second, cache2 = _reload(d, inputs, cache)

    for name in cache.renders:
        assert cache2.renders[name] is cache.renders[name]


def test_reload_after_moving_a_mesh_actor(tmp_path):
    """The moved actor's triangles are re-resolved and every other actor's are reused verbatim."""
    d = _fixture_trunk(tmp_path)
    inputs = _inputs()
    first, cache = trunk_load.load_trunk(d, inputs=inputs, previous=None)

    _write_one(d, _crate("Crate1", 512.0), "n002")
    second, cache2 = _reload(d, inputs, cache)

    assert cache2.renders["Crate1"] is not cache.renders["Crate1"]
    assert cache2.renders["Crate2"] is cache.renders["Crate2"]
    assert cache2.renders["Door"] is cache.renders["Door"]
    assert second.mesh_polys != first.mesh_polys          # the move really did land


def test_reload_after_adding_an_actor(tmp_path):
    d = _fixture_trunk(tmp_path)
    inputs = _inputs()
    first, cache = trunk_load.load_trunk(d, inputs=inputs, previous=None)

    _write_one(d, _crate("Crate3", 192.0), "n005")
    second, cache2 = _reload(d, inputs, cache)

    assert "Crate3" in second.level.actors
    assert cache2.renders["Crate2"] is cache.renders["Crate2"]
    assert len(second.mesh_polys) > len(first.mesh_polys)


def test_reload_after_removing_an_actor_drops_its_texture_rows(tmp_path):
    """A removed actor must leave nothing behind — including its texture-table rows, which a
    persistent append-only table would have stranded in the atlas. `Hatch` carries a different
    texture from `Door`, so dropping `Door` really does orphan a row rather than leave it
    referenced."""
    d = _fixture_trunk(tmp_path)
    inputs = _inputs()
    first, cache = trunk_load.load_trunk(d, inputs=inputs, previous=None)
    assert len(first.mover_texture_table) == 2

    trunk.remove_actor(d, "Door")
    second, cache2 = _reload(d, inputs, cache)

    assert "Door" not in second.level.actors
    assert "Door" not in cache2.renders
    assert {o[0] for o in second.mover_owners} == {"Hatch"}
    assert len(second.mover_texture_table) == 1           # Door's row is gone, not stranded
    assert second.mover_groups == ["CoreTexWater.water.bluewater"]


def test_reload_after_removing_a_sprite_actor(tmp_path):
    """The sprite table is rebuilt dense too: dropping the only sprite actor empties it."""
    d = _fixture_trunk(tmp_path)
    inputs = _inputs()
    first, cache = trunk_load.load_trunk(d, inputs=inputs, previous=None)
    assert first.sprite_table

    trunk.remove_actor(d, "Light0")
    second, _cache2 = _reload(d, inputs, cache)

    assert second.sprite_table == [] and second.actor_sprites == {}


def test_reload_after_retexturing_a_mover(tmp_path):
    """A changed texture re-resolves that actor's own rows and the merged table is rebuilt dense
    around them — here `Door` moves onto the texture `Hatch` already uses, so the two rows collapse
    to one, which an append-only table could never have done."""
    from uedcli.builders import cube, make_brush_actor

    d = _fixture_trunk(tmp_path)
    inputs = _inputs()
    first, cache = trunk_load.load_trunk(d, inputs=inputs, previous=None)
    assert first.mover_groups == ["CoreTexWater.water.dirtywater", "CoreTexWater.water.bluewater"]

    _write_one(d, make_brush_actor("Door", cube(64, 8, 96, texture="CoreTexWater.bluewater"),
                                   mover_class="Engine.Mover"), "n004")
    second, _cache2 = _reload(d, inputs, cache)

    assert second.mover_groups == ["CoreTexWater.water.bluewater"]
    assert len(second.mover_texture_table) == 1
    assert len(second.mover_polys) == len(first.mover_polys)   # same polys, one shared row now


def test_reload_after_reranking_keeps_name_ordered_polys(tmp_path):
    """Poly and texture-table order follow `level.actors` — the actors/ scan's NAME order, which
    both the full and the incremental read build — not `level.order`, the rank order a cold Load's
    resolvers never see either. A re-rank therefore moves `level.order` and nothing else."""
    d = _fixture_trunk(tmp_path)
    inputs = _inputs()
    first, cache = trunk_load.load_trunk(d, inputs=inputs, previous=None)
    assert first.level.order[0] == "Room"
    assert [o[0] for o in first.mesh_owners][0] == "Crate1"

    _write_one(d, first.level.actors["Crate2"], "a000")   # Crate2 now RANKS first
    second, _cache2 = _reload(d, inputs, cache)

    assert second.level.order[0] == "Crate2"
    assert list(second.level.actors) == list(first.level.actors)
    assert [o[0] for o in second.mesh_owners][0] == "Crate1"


def test_new_scene_inputs_invalidate_every_cached_render(tmp_path):
    """The renders are only valid against the class/package inputs they were resolved with — a
    rebuilt `index`/`defaults` re-resolves everything rather than reusing them."""
    d = _fixture_trunk(tmp_path)
    _first, cache = trunk_load.load_trunk(d, inputs=_inputs(), previous=None)

    _second, cache2 = trunk_load.load_trunk(d, inputs=_inputs(), previous=cache)

    for name in cache.renders:
        assert cache2.renders[name] is not cache.renders[name]


def test_load_without_a_search_path_is_empty_not_a_crash(tmp_path):
    """No configured package search path: every resolver declines, and the trunk still loads with
    every actor present and empty render tables (`resolve_*`'s own degrade disposition)."""
    _search_files, index, defaults = _inputs()
    d = _fixture_trunk(tmp_path)
    inputs = ([], index, defaults)

    loaded, cache = trunk_load.load_trunk(d, inputs=inputs, previous=None)

    assert set(loaded.level.actors) == {"Room", "Light0", "Crate1", "Crate2", "Door", "Hatch"}
    assert loaded.sprite_table == [] and loaded.mesh_polys == [] and loaded.mover_polys == []
    assert set(cache.renders) == set(loaded.level.actors)
    _reload(d, inputs, cache)
