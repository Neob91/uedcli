import pytest

from uedcli import trunk
from uedcli.order_ops import (order_after_add, order_after_delete,
                              compute_reorder_ranks, compute_add_ranks)


def test_add_appends_to_order():
    assert order_after_add(["A", "B"], "C") == ["A", "B", "C"]


def test_add_is_idempotent_on_an_existing_name():
    assert order_after_add(["A", "B"], "B") == ["A", "B"]


def test_delete_removes_from_order_preserving_the_rest():
    assert order_after_delete(["A", "B", "C"], ["B"]) == ["A", "C"]


# --- CSG-order placement (spec 2026-07-18) ---------------------------------------------

def _order(ranks):
    """The CSG order the (order_value, name) sort yields."""
    return sorted(ranks, key=lambda n: (ranks[n], n))


def _seed(names):
    return dict(zip(names, trunk.initial_ranks(len(names))))


def test_ranks_between_yields_k_distinct_ascending_in_the_gap():
    rs = trunk.ranks_between("a", "z", 4)
    assert len(rs) == 4 and rs == sorted(rs) and len(set(rs)) == 4
    assert all("a" < r < "z" for r in rs)


def test_reorder_first_lands_before_the_min():
    ranks = _seed("ABC")                                  # CSG order A < B < C
    ranks.update(compute_reorder_ranks(ranks, ["C"], "first", None))
    assert _order(ranks) == ["C", "A", "B"]


def test_reorder_last_lands_after_the_max():
    ranks = _seed("ABC")
    ranks.update(compute_reorder_ranks(ranks, ["A"], "last", None))
    assert _order(ranks) == ["B", "C", "A"]


def test_reorder_before_name_lands_immediately_before():
    ranks = _seed("ABC")
    ranks.update(compute_reorder_ranks(ranks, ["C"], "before", "B"))
    assert _order(ranks) == ["A", "C", "B"]


def test_reorder_after_name_lands_immediately_after():
    ranks = _seed("ABC")
    ranks.update(compute_reorder_ranks(ranks, ["A"], "after", "B"))
    assert _order(ranks) == ["B", "A", "C"]


def test_block_move_preserves_relative_order_noncontiguous():
    # order A B C D E; move the NON-contiguous set {A,C,E} (passed shuffled) to first: they keep
    # A<C<E and land contiguously ahead of the untouched B,D.
    ranks = _seed("ABCDE")
    ranks.update(compute_reorder_ranks(ranks, ["E", "A", "C"], "first", None))
    assert _order(ranks) == ["A", "C", "E", "B", "D"]
    assert len(set(ranks.values())) == 5                  # no duplicate order_value minted


def test_neighbour_lookup_excludes_the_moved_set():
    # move {B,C} after A: the gap's upper bound must be D (the moved C is excluded), so B,C land
    # strictly between A and D — not against a rank being simultaneously reassigned.
    ranks = _seed("ABCD")
    ranks.update(compute_reorder_ranks(ranks, ["B", "C"], "after", "A"))
    assert _order(ranks) == ["A", "B", "C", "D"]
    assert len(set(ranks.values())) == 4


def test_reorder_between_adjacent_imported_ranks_raises():
    # A ("a") and B ("a0") are lexicographically adjacent — no order_value fits between them.
    ranks = {"A": "a", "B": "a0", "C": "b"}
    with pytest.raises(ValueError):
        compute_reorder_ranks(ranks, ["C"], "before", "B")


def test_reorder_between_duplicate_ranks_raises():
    # A and B share a rank; inserting strictly between them is impossible.
    ranks = {"A": "m", "B": "m", "C": "t"}
    with pytest.raises(ValueError):
        compute_reorder_ranks(ranks, ["C"], "before", "B")


def test_add_first_places_new_below_the_min():
    ranks = _seed("ABC")
    ranks.update(compute_add_ranks(ranks, ["N_1"], "first", None))
    assert _order(ranks)[0] == "N_1"


def test_add_block_after_name_keeps_emit_order():
    ranks = _seed("AB")
    ranks.update(compute_add_ranks(ranks, ["N_1", "N_2"], "after", "A"))
    assert _order(ranks) == ["A", "N_1", "N_2", "B"]
