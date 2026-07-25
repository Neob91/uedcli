"""Label query layer (plan Task 2.1): `list_actors(labels=/no_label=)` + the `actor_show_block`
labels carrier. Mirrors the folder filters in `test_query.py`/`test_folders.py`, but for the flat,
multi-valued label dimension (spec §5, §6)."""
from uedctl.model import Actor, Level, parse_t3d
from uedctl.query import actor_show_block, list_actors


def _lvl():
    lv = Level()
    lv.actors["Torch_1"] = Actor(name="Torch_1", cls="Engine.Light",
                                 labels=frozenset({"lighting", "dup-a1b2c3"}))
    lv.actors["Torch_2"] = Actor(name="Torch_2", cls="Engine.Light",
                                 labels=frozenset({"lighting"}))
    lv.actors["Plain_3"] = Actor(name="Plain_3", cls="Engine.Light")
    lv.order = ["Torch_1", "Torch_2", "Plain_3"]
    return lv


def test_it_matches_a_label_glob():
    lv = _lvl()

    assert list_actors(lv, labels=["dup-*"]) == ["Torch_1"]


def test_it_matches_a_literal_label_across_actors():
    lv = _lvl()

    assert list_actors(lv, labels=["lighting"]) == ["Torch_1", "Torch_2"]


def test_it_ors_multiple_label_patterns():
    lv = _lvl()

    assert list_actors(lv, labels=["dup-*", "nonexistent"]) == ["Torch_1"]


def test_it_selects_only_unlabelled_with_no_label():
    lv = _lvl()

    assert list_actors(lv, no_label=True) == ["Plain_3"]


def test_it_ands_labels_with_name_glob():
    lv = _lvl()

    assert list_actors(lv, labels=["lighting"], name_glob="Torch_2") == ["Torch_2"]


def test_it_emits_the_labels_carrier_when_sidecars_on():
    a = Actor(name="Torch_1", cls="Engine.Light", labels=frozenset({"b", "a"}))

    block = actor_show_block(a, with_sidecars=True)

    assert "    // uedctl-labels: a,b" in block


def test_it_omits_the_labels_carrier_when_sidecars_off():
    a = Actor(name="Torch_1", cls="Engine.Light", labels=frozenset({"a"}))

    assert "uedctl-labels" not in actor_show_block(a, with_sidecars=False)


def test_it_round_trips_labels_via_show_block_and_parse_t3d():
    a = Actor(name="Torch_1", cls="Engine.Light", labels=frozenset({"lighting", "hero"}))

    parsed = parse_t3d("Begin Map\n" + actor_show_block(a, with_sidecars=True) + "\nEnd Map\n")

    assert parsed.actors["Torch_1"].labels == {"lighting", "hero"}
