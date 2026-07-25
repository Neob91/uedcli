from decimal import Decimal

import pytest

from uedctl import trunk
from uedctl.model import Actor, Brush, Level, Polygon


# --- Task 1: LexoRank order-value algebra ---

def test_it_makes_a_rank_strictly_between_two_ranks():
    r = trunk.rank_between("i", "r")
    assert "i" < r < "r"


def test_it_makes_a_rank_before_and_after_open_ends():
    assert trunk.rank_between(None, "i") < "i"
    assert trunk.rank_between("i", None) > "i"


def test_it_never_exhausts_on_repeated_left_inserts():
    lo, prev = "i", "j"
    for _ in range(2000):
        r = trunk.rank_between(lo, prev)
        assert lo < r < prev
        prev = r


def test_initial_ranks_are_ascending_and_distinct():
    rs = trunk.initial_ranks(5)
    assert len(rs) == 5
    assert rs == sorted(rs)
    assert len(set(rs)) == 5


# --- Task 2: random-suffix name allocation ---

def test_it_raises_when_no_rank_exists_between_adjacent_ranks():
    # "a" and "a0" are lexicographically adjacent (nothing strictly between). A hand-edited /
    # imported pair can present this; refuse loudly rather than return a rank > b.
    with pytest.raises(ValueError):
        trunk.rank_between("a", "a0")


def test_alloc_name_has_the_stem_and_a_base36_suffix():
    n = trunk.alloc_name("Cube", set())
    stem, _, suffix = n.rpartition("_")
    assert stem == "Cube"
    assert len(suffix) == 6 and all(c in trunk._SUFFIX_ALPHABET for c in suffix)


def test_alloc_name_avoids_an_existing_name():
    seq = iter(["aaaaaa", "bbbbbb"])
    n = trunk.alloc_name("Wall", {"Wall_aaaaaa"}, _rand=lambda: next(seq))
    assert n == "Wall_bbbbbb"


# --- Task 3: per-actor stored body (strip/inject Name= + brush model-ref) ---

def _brush_actor(name):
    # Empty poly list: this task tests identity strip/inject, not geometry round-trip
    # (that is model.py's own test surface).
    a = Actor(name=name, cls="Brush", location=(1, 2, 3),
              props=[("CsgOper", "CSG_Subtract"), ("Brush", f"Model'MyLevel.Model_{name}'")])
    a.brush = Brush(model_name=f"Model_{name}", polys=[])
    return a


def test_dump_body_carries_no_actor_name_and_a_constant_model_ref():
    body = trunk.dump_actor_body(_brush_actor("Wall_abc123"))
    assert "Wall_abc123" not in body
    assert "Begin Brush Name=Model\n" in body
    assert "Model'MyLevel.Model'" in body


def test_load_body_reinjects_name_and_model_ref_from_the_dir():
    a0 = _brush_actor("Wall_abc123")
    got = trunk.load_actor_body(trunk.dump_actor_body(a0), "Wall_xyz789")
    assert got.name == "Wall_xyz789"
    assert got.brush.model_name == "Model_Wall_xyz789"
    assert ("Brush", "Model'MyLevel.Model_Wall_xyz789'") in got.props


def test_body_roundtrip_is_idempotent_for_a_point_actor():
    a = Actor(name="Light_q1", cls="Light", location=(10, 20, 30),
              props=[("LightBrightness", "200")])
    got = trunk.load_actor_body(trunk.dump_actor_body(a), "Light_q1")
    assert got.cls == "Light" and got.location == a.location
    assert ("LightBrightness", "200") in got.props
    assert got.brush is None


def test_dump_strips_only_the_header_name_token():
    body = trunk.dump_actor_body(_brush_actor("Wall_abc123"))
    assert body.splitlines()[0] == "Begin Actor Class=Brush"   # header Name removed, nothing else


def test_brush_with_a_real_poly_roundtrips_geometry():
    a = Actor(name="Cube_g1", cls="Brush", location=(0, 0, 0),
              props=[("Brush", "Model'MyLevel.Model_Cube_g1'")])
    a.brush = Brush(model_name="Model_Cube_g1", polys=[Polygon(
        vertices=[(Decimal(0), Decimal(0), Decimal(0)),
                  (Decimal(128), Decimal(0), Decimal(0)),
                  (Decimal(128), Decimal(128), Decimal(0))])])
    got = trunk.load_actor_body(trunk.dump_actor_body(a), "Cube_g1")
    assert got.brush.model_name == "Model_Cube_g1"
    assert len(got.brush.polys) == 1 and len(got.brush.polys[0].vertices) == 3
    assert got.brush.polys[0].vertices[1] == (Decimal(128), Decimal(0), Decimal(0))


# --- Task 4: level read/write (per-actor directory layout) ---

def test_write_then_read_roundtrips_actors_and_derives_order(tmp_path):
    lvl = Level()
    a = _brush_actor("Wall_a1")
    b = Actor(name="Light_b2", cls="Light", location=(5, 5, 5))
    lvl.actors = {a.name: a, b.name: b}
    ranks = {"Wall_a1": "t", "Light_b2": "m"}
    trunk.write_level(tmp_path, lvl, ranks)

    assert (tmp_path / "actors" / "Wall_a1" / "actor.t3d").is_file()
    assert (tmp_path / "actors" / "Wall_a1" / "order_value").read_text().strip() == "t"
    assert not (tmp_path / "actors" / "order").exists()

    got, got_ranks = trunk.read_level(tmp_path)
    assert set(got.actors) == {"Wall_a1", "Light_b2"}
    assert got.order == ["Light_b2", "Wall_a1"]
    assert got_ranks == ranks
    assert got.actors["Wall_a1"].brush.model_name == "Model_Wall_a1"


def test_equal_order_values_tiebreak_by_name(tmp_path):
    lvl = Level()
    lvl.actors = {"X_aaa": Actor(name="X_aaa", cls="Light"),
                  "Y_bbb": Actor(name="Y_bbb", cls="Light")}
    trunk.write_level(tmp_path, lvl, {"X_aaa": "p", "Y_bbb": "p"})
    got, _ = trunk.read_level(tmp_path)
    assert got.order == ["X_aaa", "Y_bbb"]


def test_write_level_errors_on_a_missing_order_value(tmp_path):
    lvl = Level(actors={"X_1": Actor(name="X_1", cls="Light")})
    with pytest.raises(ValueError, match="X_1"):
        trunk.write_level(tmp_path, lvl, {})


def test_write_level_rejects_an_unsafe_actor_name(tmp_path):
    lvl = Level(actors={"e/../x": Actor(name="e/../x", cls="Light")})
    with pytest.raises(ValueError, match="safe directory segment"):
        trunk.write_level(tmp_path, lvl, {"e/../x": "m"})


def test_write_level_prunes_only_explicit_deletions(tmp_path):
    """`write_level` is a DELTA write (decisions.md 2026-07-18): a dropped actor's dir is pruned
    only when named in `deleted` — an on-disk dir absent from the model but NOT in `deleted`
    belongs to a concurrent writer and is left alone."""
    lvl = Level(actors={"A_1": Actor(name="A_1", cls="Light"),
                        "B_2": Actor(name="B_2", cls="Light")})
    trunk.write_level(tmp_path, lvl, {"A_1": "m", "B_2": "t"})
    lvl2 = Level(actors={"A_1": Actor(name="A_1", cls="Light")})   # B_2 dropped
    trunk.write_level(tmp_path, lvl2, {"A_1": "m"})                # …but NOT declared deleted
    assert (tmp_path / "actors" / "B_2").exists()                  # concurrent-writer dir survives
    trunk.write_level(tmp_path, lvl2, {"A_1": "m"}, deleted={"B_2"})
    assert not (tmp_path / "actors" / "B_2").exists()              # explicit deletion prunes
    got, _ = trunk.read_level(tmp_path)
    assert set(got.actors) == {"A_1"}                              # not resurrected


# --- Task 5: duplicate-order_value detection ---

def test_duplicate_ranks_groups_names_sharing_a_value():
    dups = trunk.duplicate_ranks({"X_a": "p", "Y_b": "p", "Z_c": "m"})
    assert dups == [("p", ["X_a", "Y_b"])]


def test_no_duplicates_returns_empty():
    assert trunk.duplicate_ranks({"X_a": "p", "Y_b": "m"}) == []


# --- Slice 2a: remove_actor + append_rank ---

def test_remove_actor_deletes_the_dir(tmp_path):
    lvl = Level(actors={"A_1": Actor(name="A_1", cls="Light"),
                        "B_2": Actor(name="B_2", cls="Light")})
    trunk.write_level(tmp_path, lvl, {"A_1": "m", "B_2": "t"})
    trunk.remove_actor(tmp_path, "B_2")
    assert not (tmp_path / "actors" / "B_2").exists()
    got, _ = trunk.read_level(tmp_path)
    assert set(got.actors) == {"A_1"}


def test_remove_actor_errors_on_an_absent_actor(tmp_path):
    (tmp_path / "actors").mkdir()
    with pytest.raises(ValueError, match="ghost"):
        trunk.remove_actor(tmp_path, "ghost")


def test_append_rank_orders_after_every_current_actor():
    r = trunk.append_rank({"A_1": "m", "B_2": "t"})
    assert r > "t"


def test_append_rank_on_an_empty_level_is_nonempty():
    assert trunk.append_rank({}) != ""


def test_append_rank_after_a_prefix_rank_orders_after_both():
    r = trunk.append_rank({"A_1": "t", "B_2": "t0"})     # "t0" > "t" lexicographically
    assert r > "t0" and r > "t"


def test_remove_actor_rejects_a_name_with_a_path_separator(tmp_path):
    (tmp_path / "actors").mkdir()
    with pytest.raises(ValueError, match="safe directory segment"):
        trunk.remove_actor(tmp_path, "../../foo")
