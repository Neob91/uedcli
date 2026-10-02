from unittest import mock

import pytest

from uedcli.materialize import (earliest_changed_actor, actor_suffix_plan, ActorSuffixPlan,
                                materialize, assert_at_most_one_levelinfo, levelinfo_first_order)


def test_earliest_changed_actor_finds_first_divergence():
    assert earliest_changed_actor(["A", "B", "C", "D"], ["A", "B", "X", "D"]) == 2


def test_earliest_changed_actor_zero_when_first_differs():
    assert earliest_changed_actor(["A", "B"], ["Z", "B"]) == 0


def test_earliest_changed_actor_at_append_boundary():
    assert earliest_changed_actor(["A", "B"], ["A", "B", "C"]) == 2


def test_actor_suffix_plan_lists_deletes_then_ordered_readds():
    plan = actor_suffix_plan(current_order=["A", "B", "C"], merged_order=["A", "X", "C"])
    assert isinstance(plan, ActorSuffixPlan)
    assert plan.first_changed == 1
    assert plan.delete == ["B", "C"]    # delete current K..N
    assert plan.readd == ["X", "C"]     # re-add merged K..N in canonical order


# ── full-re-import materialize (Task 20a spike: by-name brush delete is unreliable) ──


def test_materialize_full_reimport_resets_then_adds_in_canonical_order():
    """FULL RE-IMPORT: map_new, then re-add every merged actor in canonical order, then one
    rebuild. No by-name delete (the spike showed CSG brush delete is unreliable)."""
    driver = mock.Mock()
    calls = []
    re_add = mock.Mock(side_effect=lambda actors: calls.extend(a.name for a in actors))
    rebuild = mock.Mock()

    class _A:
        def __init__(self, name):
            self.name = name

    parse_actor = mock.Mock(side_effect=lambda t3d: _A(t3d))   # t3d == its name here

    materialize(driver=driver,
                current_actors={"old": "old"}, merged_actors={"B1": "B1", "L1": "L1"},
                current_order=["old"], merged_order=["B1", "L1"],
                parse_actor=parse_actor, validate_brush=mock.Mock(),
                re_add=re_add, delete_named=mock.Mock(), rebuild=rebuild)

    driver.map_new.assert_called_once()
    assert calls == ["B1", "L1"]                 # added in canonical merged order
    rebuild.assert_called_once()


def test_materialize_rolls_back_and_reraises_on_failure():
    """All-or-nothing: a re-add failure restores the captured original level and re-raises."""
    driver = mock.Mock()

    class _A:
        def __init__(self, name):
            self.name = name

    parse_actor = mock.Mock(side_effect=lambda t3d: _A(t3d))
    restore_calls = []

    def re_add(actors):
        names = [a.name for a in actors]
        if names == ["B1", "L1"]:                # the forward (merged) re-add fails
            raise RuntimeError("paste failed")
        restore_calls.append(names)              # the rollback re-add of the originals

    import pytest
    with pytest.raises(RuntimeError, match="paste failed"):
        materialize(driver=driver,
                    current_actors={"old": "old"}, merged_actors={"B1": "B1", "L1": "L1"},
                    current_order=["old"], merged_order=["B1", "L1"],
                    parse_actor=parse_actor, validate_brush=mock.Mock(),
                    re_add=re_add, delete_named=mock.Mock(), rebuild=mock.Mock())
    assert restore_calls == [["old"]]            # original level restored on failure


# ── Task 12: LevelInfo-first import + at-most-one model-side singleton assert ──


def test_assert_at_most_one_passes_with_one():
    assert_at_most_one_levelinfo({"LevelInfo0": "LevelInfo", "B1": "Brush"})   # no raise


def test_assert_at_most_one_accepts_a_lone_deusex_levelinfo():
    # A DeusExLevelInfo with no engine LevelInfo present must not trip the engine-singleton guard.
    assert_at_most_one_levelinfo({"DeusExLevelInfo0": "DeusExLevelInfo", "B1": "Brush"})


def test_assert_at_most_one_accepts_the_dx_dual_pairing():
    # The NORMAL Deus Ex map shape: one engine LevelInfo (Actors[0] singleton) PLUS one
    # DeusExLevelInfo (an ordinary mission-metadata actor). Verified against every DX/Maps/*.dx
    # (e.g. 03_NYC_UNATCOHQ: LevelInfo at Actors[0], DeusExLevelInfo at Actors[330]). Must build.
    assert_at_most_one_levelinfo(
        {"LevelInfo0": "Engine.LevelInfo", "DeusExLevelInfo0": "DeusEx.DeusExLevelInfo",
         "B1": "Brush"})


def test_assert_at_most_one_passes_with_zero():
    # A from-scratch session (no .dx) has NO LevelInfo in the model; MAP NEW supplies it at
    # materialize. Zero must be allowed (H3 — exactly-one is an editor-side post-import fact).
    assert_at_most_one_levelinfo({"B1": "Brush"})


def test_assert_at_most_one_rejects_two_engine_levelinfos():
    # Two engine LevelInfos is the genuine bug: only the first becomes Actors[0], the second is
    # silently dropped by the assembler's is_level_info filter.
    with pytest.raises(ValueError, match="at most one engine LevelInfo"):
        assert_at_most_one_levelinfo({"LevelInfo0": "LevelInfo", "LevelInfo1": "LevelInfo"})


def test_assert_at_most_one_rejects_two_deusex_levelinfos():
    # A DX map carries exactly one DeusExLevelInfo; two is anomalous and rejected too — even with
    # a legitimate engine LevelInfo present.
    with pytest.raises(ValueError, match="at most one DeusExLevelInfo"):
        assert_at_most_one_levelinfo(
            {"LevelInfo0": "LevelInfo", "DeusExLevelInfo0": "DeusExLevelInfo",
             "DeusExLevelInfo1": "DeusExLevelInfo"})


def test_levelinfo_first_order_moves_levelinfo_to_the_front():
    classes = {"B1": "Brush", "LevelInfo0": "LevelInfo", "L1": "Light"}
    has_brush = {"B1": True, "LevelInfo0": False, "L1": False}
    # L1 (point) sorts before B1 (brush) under the points-then-brushes grouping below, even
    # though B1 came first in the input order.
    assert (levelinfo_first_order(["B1", "LevelInfo0", "L1"], classes, has_brush)
           == ["LevelInfo0", "L1", "B1"])


def test_levelinfo_first_order_is_a_noop_when_already_first():
    classes = {"LevelInfo0": "LevelInfo", "L1": "Light", "B1": "Brush"}
    has_brush = {"LevelInfo0": False, "L1": False, "B1": True}
    assert (levelinfo_first_order(["LevelInfo0", "L1", "B1"], classes, has_brush)
           == ["LevelInfo0", "L1", "B1"])


def test_levelinfo_first_order_groups_every_point_actor_before_every_brush():
    # writes._re_add splits a re-add batch into one MAP IMPORTADD (all point actors) followed
    # by one EDIT PASTE (all brushes) -- so a brush listed before a point actor in the authored
    # order still lands AFTER every point actor in the live editor's resulting actor list
    # (2026-06-21: confirmed live on a base-content map whose natural order interleaves a brush
    # before two point actors). The predicted order must match this exactly, or H3 post-verify's
    # order-hash spuriously fails on the level's first materialize.
    classes = {"LevelInfo0": "LevelInfo", "Brush2": "Brush", "PlayerStart0": "PlayerStart",
              "Teleporter0": "Teleporter"}
    has_brush = {"LevelInfo0": False, "Brush2": True, "PlayerStart0": False,
                "Teleporter0": False}
    order = ["LevelInfo0", "Brush2", "PlayerStart0", "Teleporter0"]
    assert (levelinfo_first_order(order, classes, has_brush)
           == ["LevelInfo0", "PlayerStart0", "Teleporter0", "Brush2"])


def test_levelinfo_first_order_does_not_hoist_deusex_levelinfo():
    # DeusExLevelInfo is an ORDINARY point actor, NOT the Actors[0] singleton — it must stay in
    # the point-actor group (after the engine LevelInfo), never hoisted to the front.
    classes = {"DeusExLevelInfo0": "DeusEx.DeusExLevelInfo", "LevelInfo0": "Engine.LevelInfo",
              "B1": "Brush", "PlayerStart0": "Engine.PlayerStart"}
    has_brush = {"DeusExLevelInfo0": False, "LevelInfo0": False, "B1": True,
                "PlayerStart0": False}
    order = ["DeusExLevelInfo0", "LevelInfo0", "B1", "PlayerStart0"]
    # only the engine LevelInfo hoists to front; DeusExLevelInfo + PlayerStart stay point actors
    # (in authored relative order) ahead of the brush.
    assert (levelinfo_first_order(order, classes, has_brush)
           == ["LevelInfo0", "DeusExLevelInfo0", "PlayerStart0", "B1"])


def test_materialize_imports_levelinfo_first_and_ensure_loads_before_map_new():
    """The full re-import drives LevelInfo first (D-I) and ensure-loads the manifest before
    MAP NEW (Task 14 wires the real ensure-load; here it's an injected seam)."""
    driver = mock.Mock()
    calls = []
    re_add = mock.Mock(side_effect=lambda actors: calls.extend(a.name for a in actors))
    ensure_load = mock.Mock(side_effect=lambda pkgs: calls.append(("ensure_load", tuple(pkgs))))
    driver.map_new.side_effect = lambda: calls.append("map_new")

    class _A:
        def __init__(self, name, cls):
            self.name = name
            self.cls = cls

    classes = {"B1": "Brush", "LI": "LevelInfo"}
    parse_actor = mock.Mock(side_effect=lambda t3d: _A(t3d, classes[t3d]))

    materialize(driver=driver,
                current_actors={}, merged_actors={"B1": "B1", "LI": "LI"},
                current_order=["B1", "LI"], merged_order=["B1", "LI"],
                parse_actor=parse_actor, validate_brush=mock.Mock(),
                re_add=re_add, delete_named=mock.Mock(), rebuild=mock.Mock(),
                packages=["Engine", "DeusEx"], ensure_load=ensure_load)

    # ensure_load fires before MAP NEW; the import is LevelInfo-first.
    assert calls[0] == ("ensure_load", ("Engine", "DeusEx"))
    assert calls[1] == "map_new"
    assert [c for c in calls if c in ("LI", "B1")] == ["LI", "B1"]


def test_materialize_rejects_two_levelinfo_in_the_model():
    driver = mock.Mock()

    class _A:
        def __init__(self, name, cls):
            self.name = name
            self.cls = cls

    classes = {"LI0": "LevelInfo", "LI1": "LevelInfo"}
    parse_actor = mock.Mock(side_effect=lambda t3d: _A(t3d, classes[t3d]))

    with pytest.raises(ValueError, match="at most one"):
        materialize(driver=driver,
                    current_actors={}, merged_actors={"LI0": "LI0", "LI1": "LI1"},
                    current_order=["LI0", "LI1"], merged_order=["LI0", "LI1"],
                    parse_actor=parse_actor, validate_brush=mock.Mock(),
                    re_add=mock.Mock(), delete_named=mock.Mock(), rebuild=mock.Mock())
    driver.map_new.assert_not_called()                # asserted before driving
