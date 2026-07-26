"""The delta-write diff MUST include labels — the critical trap (spec 2026-07-22-actor-labels.md §3).

`TrunkLevelSource.save` writes ONLY actors whose body/rank/folder/LABELS differ from its load
snapshot. Labels are a sidecar (not in the body), so a labels-ONLY change leaves body+rank+folder
byte-identical; without the 4th `changed` clause + the `_loaded_labels` baseline, the write is
silently dropped. This pins BOTH directions: adding a label, and clearing back to empty.
"""
from uedcli import dispatch, trunk
from uedcli.model import Actor, Level


def _light(name, **kw):
    return Actor(name=name, cls="Engine.Light", location=(0, 0, 0), **kw)


def test_label_only_change_persists_via_delta_write(tmp_path):
    """A body/rank/folder-identical, labels-CHANGED actor IS in the written set (the §3 trap)."""
    lvl = Level(actors={"A_1": _light("A_1")}, order=["A_1"])
    trunk.write_level(tmp_path, lvl, {"A_1": "m"})
    src = dispatch.TrunkLevelSource(tmp_path)
    loaded = src.load()
    assert loaded.actors["A_1"].labels == frozenset()    # precondition: baseline has no labels

    loaded.actors["A_1"].labels = frozenset({"lighting"})  # ONLY labels change (body+rank+folder same)
    src.save(verb="label", args={}, level=loaded, touched=["A_1"])

    assert (tmp_path / "actors" / "A_1" / "labels").read_text() == "lighting\n"
    got, _ = trunk.read_level(tmp_path)
    assert got.actors["A_1"].labels == frozenset({"lighting"})


def test_label_clear_persists_via_delta_write(tmp_path):
    """The SYMMETRIC trap: clearing to empty on an otherwise byte-identical actor also fires."""
    lvl = Level(actors={"A_1": _light("A_1", labels=frozenset({"hero"}))}, order=["A_1"])
    trunk.write_level(tmp_path, lvl, {"A_1": "m"})
    src = dispatch.TrunkLevelSource(tmp_path)
    loaded = src.load()
    assert loaded.actors["A_1"].labels == frozenset({"hero"})  # precondition: baseline has the label

    loaded.actors["A_1"].labels = frozenset()            # clear — body+rank+folder unchanged
    src.save(verb="label", args={}, level=loaded, touched=["A_1"])

    assert not (tmp_path / "actors" / "A_1" / "labels").exists()
    got, _ = trunk.read_level(tmp_path)
    assert got.actors["A_1"].labels == frozenset()
