"""The `labels` per-actor sidecar in t3dtree — sorted, atomic, removed-on-empty.

Labels ride the ONE shared per-actor T3D-tree path beside the `folder` sidecar: `<dir>/labels`, one
label per line, sorted. Empty labels write NO file, and clearing a previously-labelled actor REMOVES
the file (mirrors `folder` unset). Pins spec in board item `re-evaluate-whether-reject-nonlevel-target` §2.
"""
from uedcli import t3dtree
from uedcli.model import Actor, Level


def _level_with(actor: Actor) -> tuple[Level, dict[str, str]]:
    level = Level()
    level.actors[actor.name] = actor
    level.order = [actor.name]
    return level, {actor.name: "0|hzzzzz:"}


def test_labels_file_is_sorted_with_trailing_newline(tmp_path):
    actor = Actor(name="Torch7", cls="Light", labels=frozenset({"b", "a", "c"}))
    level, ranks = _level_with(actor)

    t3dtree.write_actor_tree(tmp_path, level, ranks)

    assert (tmp_path / "actors" / "Torch7" / "labels").read_text() == "a\nb\nc\n"


def test_labels_round_trip_to_frozenset(tmp_path):
    actor = Actor(name="Torch7", cls="Light", labels=frozenset({"lighting", "hero"}))
    level, ranks = _level_with(actor)
    t3dtree.write_actor_tree(tmp_path, level, ranks)

    loaded, _ranks, _bodies, _folders = t3dtree.read_actor_tree(tmp_path)

    assert loaded.actors["Torch7"].labels == frozenset({"hero", "lighting"})


def test_empty_labels_writes_no_file(tmp_path):
    actor = Actor(name="Plain", cls="Light")             # labels default = frozenset()
    level, ranks = _level_with(actor)

    t3dtree.write_actor_tree(tmp_path, level, ranks)

    assert not (tmp_path / "actors" / "Plain" / "labels").exists()


def test_absent_labels_file_reads_empty(tmp_path):
    actor = Actor(name="Plain", cls="Light")
    level, ranks = _level_with(actor)
    t3dtree.write_actor_tree(tmp_path, level, ranks)

    loaded, _r, _b, _f = t3dtree.read_actor_tree(tmp_path)

    assert loaded.actors["Plain"].labels == frozenset()


def test_clearing_labels_removes_the_existing_file(tmp_path):
    labelled = Actor(name="Torch7", cls="Light", labels=frozenset({"lighting"}))
    level, ranks = _level_with(labelled)
    t3dtree.write_actor_tree(tmp_path, level, ranks)
    labels_file = tmp_path / "actors" / "Torch7" / "labels"
    assert labels_file.exists()                          # precondition: the file was written

    level.actors["Torch7"] = Actor(name="Torch7", cls="Light", labels=frozenset())
    t3dtree.write_actor_tree(tmp_path, level, ranks)

    assert not labels_file.exists()
