"""`read_actor_tree` must not stat() per sidecar per actor.

The old implementation checked existence of each of `actor.t3d`/`folder`/`labels`/`order_value` with
a separate `Path.is_file()` (plus an `is_dir()` per outer entry) — 5 real `stat()` syscalls per actor
before reading a single byte. On a real level (WanChai, 2288 actors) that was ~11000 stat() calls and
the dominant cost of a cold trunk read on slow storage (~4s of ~10s;
`dev/docs/board/inbox/scene-cold-load-must-return-within-5s`). Fixed to list each actor dir with one
`os.scandir()` and check membership instead of stat-ing each candidate name.
"""
import pathlib

from uedcli import t3dtree
from uedcli.model import Actor, Level


def _write_actors(tmp_path, n):
    level = Level()
    ranks = {}
    for i in range(n):
        name = f"Actor_{i}"
        level.actors[name] = Actor(name=name, cls="Light")
        ranks[name] = f"{i:06d}"
    level.order = list(level.actors)
    t3dtree.write_actor_tree(tmp_path, level, ranks)
    return level, ranks


def test_read_actor_tree_makes_no_per_actor_stat_calls(tmp_path, monkeypatch):
    n = 50
    _write_actors(tmp_path, n)

    calls = 0
    real_stat = pathlib.Path.stat

    def counting_stat(self, *a, **kw):
        nonlocal calls
        calls += 1
        return real_stat(self, *a, **kw)

    monkeypatch.setattr(pathlib.Path, "stat", counting_stat)

    level, ranks, bodies, folders = t3dtree.read_actor_tree(tmp_path)

    assert len(level.actors) == n
    assert calls == 0, f"expected zero Path.stat() calls, got {calls} for {n} actors"


def test_read_actor_tree_still_reads_correct_content(tmp_path):
    level, ranks = _write_actors(tmp_path, 5)
    got, got_ranks, bodies, folders = t3dtree.read_actor_tree(tmp_path)
    assert set(got.actors) == set(level.actors)
    assert got_ranks == ranks
    assert got.order == sorted(level.actors, key=lambda n: (ranks[n], n))
