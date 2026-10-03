"""`t3dtree`'s incremental tree read (board `incremental-gui-reload-only-re-resolve-actors`):
`stamp_actor_tree` + `read_actor_tree_delta` must reuse an unchanged actor verbatim and re-read
every actor whose files moved, with the same whole-tree result `read_actor_tree` returns either
way."""
from __future__ import annotations

import os

from uedcli import t3dtree, trunk
from uedcli.model import Level
from uedcli.tests.conftest import cube_room


def _write(tree_dir, actors):
    level = Level(actors={a.name: a for a in actors}, order=[a.name for a in actors])
    trunk.write_level(tree_dir, level, {a.name: f"n{i:03d}" for i, a in enumerate(actors)})


def test_delta_cold_read_matches_read_actor_tree(tmp_path):
    """`previous=None` returns exactly what the one-shot `read_actor_tree` does, and names every
    actor as re-read."""
    d = tmp_path / "TestLevel"
    _write(d, [cube_room(), cube_room(name="Room2")])

    level, ranks, bodies, folders = trunk.read_level_with_bodies(d)
    delta = t3dtree.read_actor_tree_delta(d, None)

    assert list(delta.read.level.actors) == list(level.actors)
    assert delta.read.level.order == level.order
    assert delta.read.ranks == ranks
    assert delta.read.bodies == bodies
    assert delta.read.folders == folders
    assert delta.reread == {"Room", "Room2"}
    assert set(delta.read.stamps) == {"Room", "Room2"}


def test_delta_reuses_unchanged_actors_without_reparsing(tmp_path):
    """An untouched actor comes back as the SAME `Actor` object the previous read parsed (`is`),
    which is what proves no file of its was read again."""
    d = tmp_path / "TestLevel"
    _write(d, [cube_room(), cube_room(name="Room2")])
    first = t3dtree.read_actor_tree_delta(d, None).read

    second = t3dtree.read_actor_tree_delta(d, first)

    assert second.reread == frozenset()
    for name in ("Room", "Room2"):
        assert second.read.level.actors[name] is first.level.actors[name]
        assert second.read.bodies[name] is first.bodies[name]


def test_delta_rereads_an_actor_written_through_write_level(tmp_path):
    """The real uedcli write path (`write_actor_tree`: tmp + `os.replace` in the actor dir) always
    moves that dir's own mtime, so its actor is re-read and every other actor is not."""
    d = tmp_path / "TestLevel"
    _write(d, [cube_room(), cube_room(name="Room2")])
    first = t3dtree.read_actor_tree_delta(d, None).read

    moved = cube_room(name="Room2", size=256.0)
    trunk.write_level(d, Level(actors={"Room2": moved}, order=["Room2"]), {"Room2": "n001"},
                      only={"Room2"})
    second = t3dtree.read_actor_tree_delta(d, first)

    assert second.reread == {"Room2"}
    assert second.read.level.actors["Room"] is first.level.actors["Room"]
    assert second.read.bodies["Room2"] != first.bodies["Room2"]


def test_delta_rereads_an_in_place_body_rewrite(tmp_path):
    """An external writer that truncates `actor.t3d` in place never touches the dir entry, so the
    dir mtime alone would miss it — the body's own mtime+size is why it does not (owner ruling
    2026-10-03)."""
    d = tmp_path / "TestLevel"
    _write(d, [cube_room(), cube_room(name="Room2")])
    first = t3dtree.read_actor_tree_delta(d, None).read

    body = d / "actors" / "Room2" / "actor.t3d"
    rewritten = first.bodies["Room2"].replace("Subtract", "Add")
    assert rewritten != first.bodies["Room2"]
    dir_before = os.stat(d / "actors" / "Room2").st_mtime_ns
    with open(body, "w") as fh:                       # in place: no create, no rename, no unlink
        fh.write(rewritten)
    assert os.stat(d / "actors" / "Room2").st_mtime_ns == dir_before

    second = t3dtree.read_actor_tree_delta(d, first)
    assert second.reread == {"Room2"}
    assert second.read.bodies["Room2"] == rewritten


def test_delta_picks_up_an_added_actor_and_drops_a_deleted_one(tmp_path):
    """A new actor dir is re-read; a deleted one leaves the tree and its stamp with it."""
    d = tmp_path / "TestLevel"
    _write(d, [cube_room(), cube_room(name="Room2")])
    first = t3dtree.read_actor_tree_delta(d, None).read

    added = cube_room(name="Room3")
    trunk.write_level(d, Level(actors={"Room3": added}, order=["Room3"]), {"Room3": "n002"},
                      only={"Room3"})
    trunk.remove_actor(d, "Room")
    second = t3dtree.read_actor_tree_delta(d, first)

    assert second.reread == {"Room3"}
    assert set(second.read.level.actors) == {"Room2", "Room3"}
    assert set(second.read.stamps) == {"Room2", "Room3"}
    assert "Room" not in second.read.ranks


def test_delta_order_matches_a_full_read_after_an_edit(tmp_path):
    """`level.order` is the (order_value, name) sort of the CURRENT tree, reused actors included —
    an incremental read must not inherit the previous read's ordering."""
    d = tmp_path / "TestLevel"
    _write(d, [cube_room(), cube_room(name="Room2")])
    first = t3dtree.read_actor_tree_delta(d, None).read

    # Re-rank Room2 ahead of Room, writing only its own dir.
    trunk.write_level(d, Level(actors={"Room2": first.level.actors["Room2"]}, order=["Room2"]),
                      {"Room2": "a000"}, only={"Room2"})
    second = t3dtree.read_actor_tree_delta(d, first)

    full, _ranks, _bodies, _folders = trunk.read_level_with_bodies(d)
    assert second.read.level.order == full.order == ["Room2", "Room"]


def test_stamp_actor_tree_skips_a_dir_without_a_body(tmp_path):
    """`stamp_actor_tree` admits exactly the dirs `read_actor_tree` does — a rank-only dir (a write
    whose body has not landed) is in neither."""
    d = tmp_path / "TestLevel"
    _write(d, [cube_room()])
    half = d / "actors" / "Pending"
    half.mkdir()
    (half / "order_value").write_text("n999\n")

    assert set(t3dtree.stamp_actor_tree(d)) == {"Room"}
    assert set(t3dtree.read_actor_tree_delta(d, None).read.level.actors) == {"Room"}


def test_stamp_actor_tree_on_a_missing_tree_is_empty(tmp_path):
    assert t3dtree.stamp_actor_tree(tmp_path / "nope") == {}
    assert t3dtree.read_actor_tree_delta(tmp_path / "nope", None).read.level.actors == {}
