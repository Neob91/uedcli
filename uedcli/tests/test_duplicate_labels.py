"""`actor duplicate` overhaul (plan Task 3.1) — end-to-end through the real argparse parser.

`duplicate` now REQUIRES a `--by`/`--at` placement, always stamps every copy with a fresh
`dup-<rand>` batch label (re-rolled until unused level-wide), inherits the source's labels, and
takes `--label` ADDITIVELY. Placement translates the source actors before the trunk write.

Labels are TRUNK-ONLY; these drive a real on-disk project + trunk so the sidecar round-trips.
`_stub_author_validation` (autouse in conftest) no-ops the class/texture ingest gate so the run
stays offline.
"""
from decimal import Decimal

import pytest

from uedcli import cli, dispatch, t3dtree, trunk
from uedcli.model import Actor, Level


def _mkproject(tmp_path, monkeypatch, actors):
    root = tmp_path / "proj"
    (root / "maps" / "lvl").mkdir(parents=True)
    (root / "uedcli.toml").write_text('game = "deusex"\n')
    monkeypatch.setenv("UEDCLI_PROJECT", str(root))
    lvl = Level(actors={a.name: a for a in actors}, order=[a.name for a in actors])
    ranks = dict(zip([a.name for a in actors], trunk.initial_ranks(len(actors)) or []))
    trunk.write_level(root / "maps" / "lvl", lvl, ranks)
    monkeypatch.setenv("UEDCLI_LEVEL", "lvl")
    return root


def _run(argv):
    return dispatch.dispatch(cli.build_parser().parse_args(argv))


def _read(root):
    lvl, _ranks = trunk.read_level(root / "maps" / "lvl")
    return lvl


def _light(name, *, loc, labels=frozenset()):
    return Actor(name=name, cls="Engine.Light", location=loc, labels=labels)


def _copy_names(capsys):
    return capsys.readouterr().out.split()


# ── required placement ────────────────────────────────────────────────────────────────

def test_it_rejects_a_bare_duplicate_without_by_or_at(tmp_path, monkeypatch):
    _mkproject(tmp_path, monkeypatch, [_light("Lamp", loc=(0, 0, 0))])
    with pytest.raises(SystemExit) as exc:                # argparse: --by/--at group is required
        cli.build_parser().parse_args(["actor", "duplicate", "Lamp"])
    assert exc.value.code == 2


# ── placement ─────────────────────────────────────────────────────────────────────────

def test_it_offsets_the_copy_with_by(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch, [_light("Lamp", loc=(10, 20, 30))])
    assert _run(["actor", "duplicate", "Lamp", "--by", "128,0,0"]) == 0
    (copy,) = _copy_names(capsys)
    assert _read(root).actors[copy].location == (Decimal(138), Decimal(20), Decimal(30))


def test_it_anchors_the_set_bbox_min_corner_with_at(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch, [_light("Lamp", loc=(100, 200, 300))])
    assert _run(["actor", "duplicate", "Lamp", "--at", "16,32,48"]) == 0
    (copy,) = _copy_names(capsys)
    assert _read(root).actors[copy].location == (Decimal(16), Decimal(32), Decimal(48))


def test_it_preserves_relative_layout_for_a_multi_actor_by(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch,
                      [_light("A", loc=(0, 0, 0)), _light("B", loc=(128, 0, 0))])
    assert _run(["actor", "duplicate", "A", "B", "--by", "0,0,256"]) == 0
    lvl = _read(root)
    copies = [lvl.actors[n] for n in _copy_names(capsys)]
    locs = sorted((c.location for c in copies), key=lambda p: p[0])
    assert locs == [(Decimal(0), Decimal(0), Decimal(256)), (Decimal(128), Decimal(0), Decimal(256))]


def test_it_preserves_relative_layout_for_a_multi_actor_at(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch,
                      [_light("A", loc=(100, 0, 0)), _light("B", loc=(300, 0, 0))])
    assert _run(["actor", "duplicate", "A", "B", "--at", "10,0,0"]) == 0
    lvl = _read(root)
    locs = sorted((lvl.actors[n].location for n in _copy_names(capsys)), key=lambda p: p[0])
    assert locs == [(Decimal(10), Decimal(0), Decimal(0)), (Decimal(210), Decimal(0), Decimal(0))]


# ── labels ──────────────────────────────────────────────────────────────────────────────

def test_it_inherits_source_labels_and_stamps_a_dup_token(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch,
                      [_light("Lamp", loc=(0, 0, 0), labels=frozenset({"lighting"}))])
    assert _run(["actor", "duplicate", "Lamp", "--by", "64,0,0"]) == 0
    (copy,) = _copy_names(capsys)
    labels = _read(root).actors[copy].labels
    assert "lighting" in labels                                   # inherited from the source
    assert any(l.startswith("dup-") for l in labels)              # fresh batch token
    assert len([l for l in labels if l.startswith("dup-")]) == 1


def test_it_stamps_a_shared_dup_token_across_the_batch(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch,
                      [_light("A", loc=(0, 0, 0)), _light("B", loc=(64, 0, 0))])
    assert _run(["actor", "duplicate", "A", "B", "--by", "0,0,128"]) == 0
    lvl = _read(root)
    tokens = [{l for l in lvl.actors[n].labels if l.startswith("dup-")} for n in _copy_names(capsys)]
    assert tokens[0] == tokens[1] and len(tokens[0]) == 1         # ONE shared batch token


def test_it_adds_extra_label_and_keeps_the_dup_token(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch,
                      [_light("Lamp", loc=(0, 0, 0), labels=frozenset({"lighting"}))])
    assert _run(["actor", "duplicate", "Lamp", "--by", "64,0,0", "--label", "wing-b"]) == 0
    (copy,) = _copy_names(capsys)
    labels = _read(root).actors[copy].labels
    assert "lighting" in labels                                   # inherited
    assert "wing-b" in labels                                     # additive --label
    assert any(l.startswith("dup-") for l in labels)              # dup token STILL present


def test_it_rerolls_a_dup_token_that_collides_with_an_existing_label(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch,
                      [_light("Lamp", loc=(0, 0, 0), labels=frozenset({"hero"})),
                       _light("Blocker", loc=(500, 0, 0), labels=frozenset({"dup-collide"}))])
    seq = iter(["collide", "fresh"])                              # first roll collides, second is free
    monkeypatch.setattr(t3dtree, "_rand_suffix", lambda: next(seq))
    assert _run(["actor", "duplicate", "Lamp", "--by", "64,0,0"]) == 0
    (copy,) = _copy_names(capsys)
    labels = _read(root).actors[copy].labels
    assert "dup-fresh" in labels                                  # re-rolled past the collision
    assert "dup-collide" not in labels                            # the colliding token was rejected


def test_it_echoes_the_batch_label_to_stderr(tmp_path, monkeypatch, capsys):
    _mkproject(tmp_path, monkeypatch, [_light("Lamp", loc=(0, 0, 0))])
    assert _run(["actor", "duplicate", "Lamp", "--by", "64,0,0"]) == 0
    err = capsys.readouterr().err
    assert "dup-" in err                                          # batch label surfaced to the human


# ── labels are trunk-only: reject a stash/prefab box target ───────────────────────────

def test_it_rejects_a_stash_target_since_it_always_mints_a_label(tmp_path, monkeypatch, capsys):
    # `duplicate` unconditionally stamps a dup-<rand> label, but a stash/prefab box save has no
    # labels channel — so it must reject the box, not silently drop the label. Fires pre-resolution
    # (mirroring the label verbs), so an absent stash still gets the labels message, not "stash not
    # found".
    root = _mkproject(tmp_path, monkeypatch, [_light("Lamp", loc=(0, 0, 0))])
    assert _run(["actor", "duplicate", "Lamp", "--by", "0,0,0", "--tree", "stash/foo"]) == 2
    assert "labels apply only to a level" in capsys.readouterr().err
    assert list(_read(root).actors) == ["Lamp"]                   # nothing written to the trunk
