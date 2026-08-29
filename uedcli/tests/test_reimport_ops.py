"""Pure diff/order-recompute logic for `level reimport` — no I/O, no editor. See
dev/docs/board/to-plan/level-reimport-reimport-a-hand-edited-dx-unr/spec.md."""
from __future__ import annotations

from uedcli import reimport_ops
from uedcli.model import Actor, Brush, Level


def _level(*actors: Actor) -> Level:
    return Level(actors={a.name: a for a in actors}, order=[a.name for a in actors])


def test_added_and_deleted_are_classified_by_name_membership():
    existing = _level(Actor(name="Keep", cls="Engine.Light"),
                      Actor(name="Gone", cls="Engine.Light"))
    new = _level(Actor(name="Keep", cls="Engine.Light"),
                Actor(name="New", cls="Engine.Light"))

    diff = reimport_ops.diff_actors(existing, new)

    assert diff.added == {"New"}
    assert diff.deleted == {"Gone"}


def test_a_matched_actor_with_an_identical_body_is_neither_changed_nor_modified():
    existing = _level(Actor(name="A", cls="Engine.Light", props=[("Tag", "x")]))
    new = _level(Actor(name="A", cls="Engine.Light", props=[("Tag", "x")]))

    diff = reimport_ops.diff_actors(existing, new)

    assert diff.changed == frozenset()
    assert diff.modified == frozenset()


def test_a_property_change_is_both_changed_and_modified():
    existing = _level(Actor(name="A", cls="Engine.Light", props=[("Tag", "x")]))
    new = _level(Actor(name="A", cls="Engine.Light", props=[("Tag", "y")]))

    diff = reimport_ops.diff_actors(existing, new)

    assert diff.changed == {"A"}
    assert diff.modified == {"A"}


def test_a_location_only_move_is_changed_but_not_modified():
    """An ordinary reposition must be written (it's a real edit) but must NOT count toward the
    blast-radius guard (spec 'The blast-radius guard') — the guard exists to catch a wrong-file
    reimport, and moving actors around is routine editor work."""
    existing = _level(Actor(name="A", cls="Engine.Light", location=(0, 0, 0)))
    new = _level(Actor(name="A", cls="Engine.Light", location=(50, 0, 0)))

    diff = reimport_ops.diff_actors(existing, new)

    assert diff.changed == {"A"}
    assert diff.modified == frozenset()


def test_a_rotation_only_change_is_changed_but_not_modified():
    existing = _level(Actor(name="A", cls="Engine.Light", props=[("Rotation", "(Yaw=100)")]))
    new = _level(Actor(name="A", cls="Engine.Light", props=[("Rotation", "(Yaw=999)")]))

    diff = reimport_ops.diff_actors(existing, new)

    assert diff.changed == {"A"}
    assert diff.modified == frozenset()


def test_a_class_change_on_a_matched_name_counts_as_modified():
    """A same-name reclass (e.g. changing a mover's class) is a legitimate matched-actor edit — it
    just flows through as an ordinary body diff, no special-cased guard (spec 'Rejected')."""
    existing = _level(Actor(name="A", cls="Engine.Mover"))
    new = _level(Actor(name="A", cls="Engine.Light"))

    diff = reimport_ops.diff_actors(existing, new)

    assert diff.modified == {"A"}


def test_a_brush_actor_uses_the_same_pose_blind_comparison():
    existing = _level(Actor(name="B", cls="Engine.Brush", brush=Brush(model_name="Model", polys=[])))
    new = _level(Actor(name="B", cls="Engine.Brush", brush=Brush(model_name="Model", polys=[]),
                       location=(10, 0, 0)))

    diff = reimport_ops.diff_actors(existing, new)

    assert diff.changed == {"B"}
    assert diff.modified == frozenset()      # still just a location move


def test_blast_radius_is_not_exceeded_at_exactly_the_threshold():
    diff = reimport_ops.ReimportDiff(added=frozenset(), deleted=frozenset({"D"}),
                                     changed=frozenset(), modified=frozenset({"M"}))
    assert reimport_ops.blast_radius_exceeded(diff, old_actor_count=10) is False   # 2/10 == 20%


def test_blast_radius_is_exceeded_just_over_the_threshold():
    diff = reimport_ops.ReimportDiff(added=frozenset(), deleted=frozenset({"D"}),
                                     changed=frozenset(), modified=frozenset({"M1", "M2"}))
    assert reimport_ops.blast_radius_exceeded(diff, old_actor_count=10) is True    # 3/10 == 30%


def test_pure_additions_never_trip_the_blast_radius_guard():
    diff = reimport_ops.ReimportDiff(added=frozenset({f"N{i}" for i in range(50)}),
                                     deleted=frozenset(), changed=frozenset(), modified=frozenset())
    assert reimport_ops.blast_radius_exceeded(diff, old_actor_count=2) is False


def test_blast_radius_on_an_empty_trunk_is_never_exceeded():
    diff = reimport_ops.ReimportDiff(added=frozenset(), deleted=frozenset(), changed=frozenset(),
                                     modified=frozenset())
    assert reimport_ops.blast_radius_exceeded(diff, old_actor_count=0) is False


def _brush(name: str) -> Actor:
    return Actor(name=name, cls="Engine.Brush", brush=Brush(model_name="Model", polys=[]))


def test_an_unchanged_brush_order_keeps_every_order_value():
    existing_ranks = {"B1": "m", "B2": "n", "B3": "o"}
    new = _level(_brush("B1"), _brush("B2"), _brush("B3"))
    diff = reimport_ops.ReimportDiff(added=frozenset(), deleted=frozenset(), changed=frozenset(),
                                     modified=frozenset())

    ranks = reimport_ops.compute_brush_ranks(existing_ranks, new, diff)

    assert ranks == {"B1": "m", "B2": "n", "B3": "o"}


def test_reordering_two_brushes_only_re_ranks_the_minimal_one():
    """Swapping B2/B3's relative order: the longest-increasing-subsequence diff keeps B1/B3
    (already increasing) untouched and only mints a fresh rank for B2 (spec: 'brushes only ...
    keep their existing order_value untouched; everything else ... gets freshly minted')."""
    existing_ranks = {"B1": "m", "B2": "n", "B3": "o"}
    new = _level(_brush("B1"), _brush("B3"), _brush("B2"))     # B3 now before B2
    diff = reimport_ops.ReimportDiff(added=frozenset(), deleted=frozenset(), changed=frozenset(),
                                     modified=frozenset())

    ranks = reimport_ops.compute_brush_ranks(existing_ranks, new, diff)

    assert ranks["B1"] == "m"
    assert ranks["B3"] == "o"                 # unchanged: still the longest stable run
    assert ranks["B2"] not in ("m", "n", "o")  # freshly minted
    assert ranks["B3"] < ranks["B2"]           # and lands strictly after B3, per the new order


def test_a_new_brush_inserted_between_two_unchanged_ones_gets_a_rank_between_them():
    existing_ranks = {"B1": "m", "B2": "n"}
    new = _level(_brush("B1"), _brush("B3"), _brush("B2"))     # B3 is new, inserted in the middle
    diff = reimport_ops.ReimportDiff(added=frozenset({"B3"}), deleted=frozenset(),
                                     changed=frozenset(), modified=frozenset())

    ranks = reimport_ops.compute_brush_ranks(existing_ranks, new, diff)

    assert ranks["B1"] == "m"                  # both unchanged
    assert ranks["B2"] == "n"
    assert "m" < ranks["B3"] < "n"


def test_point_actors_are_ignored_entirely():
    existing_ranks = {"B1": "m", "P1": "z"}
    new = _level(_brush("B1"), Actor(name="P1", cls="Engine.Light"))
    diff = reimport_ops.ReimportDiff(added=frozenset(), deleted=frozenset(), changed=frozenset(),
                                     modified=frozenset())

    ranks = reimport_ops.compute_brush_ranks(existing_ranks, new, diff)

    assert ranks == {"B1": "m"}                # P1 never appears — brush-only, per the spec
