"""The `level reimport` verb: destination resolution, the diff/write path, and the blast-radius
guard. Mirrors `test_import_verb.py`'s harness — see that file's module docstring for why the class
package seam is patched. Spec:
dev/docs/board/to-plan/level-reimport-reimport-a-hand-edited-dx-unr/spec.md."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from unittest import mock

import pytest

from uedcli import trunk
from uedcli.cli import dispatch
from uedcli.classindex import ClassIndex

_ROOT = Path(__file__).resolve().parent.parent.parent
_UED22 = _ROOT / "uned" / "UED22"
_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "map_import_bounds"

pytestmark = pytest.mark.skipif(
    not (_UED22 / "Engine.u").is_file(),
    reason="committed UED22/Engine.u not present (the decode needs class schemas + defaults)")


def _real_index(_project=None) -> ClassIndex:
    paths = {p.stem.casefold(): str(p) for p in _UED22.glob("*.u")}
    return ClassIndex(_paths=paths, _stems={k: Path(v).stem for k, v in paths.items()})


def _import_ns(mapfile, tree, *, project) -> argparse.Namespace:
    return argparse.Namespace(cmd="level", sub="import", mapfile=str(mapfile), tree=tree,
                              overwrite=False, project=str(project), container="c")


def _reimport_ns(mapfile, tree, *, project, force=False) -> argparse.Namespace:
    return argparse.Namespace(cmd="level", sub="reimport", mapfile=str(mapfile), tree=tree,
                              force=force, project=str(project), container="c")


def _seed(project, tree="level/m03-study", fixture="paste.dx"):
    """Import a fixture into a fresh trunk so a test has an EXISTING level to reimport onto."""
    with mock.patch("uedcli.cli.resources.class_index", _real_index):
        rc = dispatch.dispatch(_import_ns(_FIXTURES / fixture, tree, project=project))
    assert rc == 0


def _reimport(mapfile, tree, *, project, force=False) -> int:
    with mock.patch("uedcli.cli.resources.class_index", _real_index):
        return dispatch.dispatch(_reimport_ns(mapfile, tree, project=project, force=force))


def test_reimporting_the_same_map_is_a_true_no_op(tmp_project):
    _seed(tmp_project)
    level_dir = tmp_project / "maps" / "m03-study"
    before_mtimes = {p: p.stat().st_mtime_ns for p in level_dir.rglob("*") if p.is_file()}

    rc = _reimport(_FIXTURES / "paste.dx", "level/m03-study", project=tmp_project)

    assert rc == 0
    after_mtimes = {p: p.stat().st_mtime_ns for p in level_dir.rglob("*") if p.is_file()}
    assert before_mtimes == after_mtimes, "an unchanged reimport must touch NO file on disk"


def test_reimporting_a_different_map_with_the_same_actor_names_is_also_a_no_op(tmp_project):
    """paste.dx/import.dx/importadd.dx decode to byte-identical content actors (differing only in
    the editor scratch objects, which are dropped) — so this is still a real no-op, exercised
    through a genuinely different source file."""
    _seed(tmp_project, fixture="paste.dx")
    level_dir = tmp_project / "maps" / "m03-study"
    before_mtimes = {p: p.stat().st_mtime_ns for p in level_dir.rglob("*") if p.is_file()}

    rc = _reimport(_FIXTURES / "import.dx", "level/m03-study", project=tmp_project)

    assert rc == 0
    after_mtimes = {p: p.stat().st_mtime_ns for p in level_dir.rglob("*") if p.is_file()}
    assert before_mtimes == after_mtimes


def test_reimport_prints_actor_names_to_stdout_and_summary_to_stderr(capsys, tmp_project):
    _seed(tmp_project)
    capsys.readouterr()   # discard the seed import's own stdout/stderr — only reimport's counts here

    rc = _reimport(_FIXTURES / "paste.dx", "level/m03-study", project=tmp_project)
    cap = capsys.readouterr()

    assert rc == 0
    assert sorted(cap.out.split()) == ["LevelInfo0", "ProbePillar", "ProbeRoom"]
    assert "reimported 3 actor(s)" in cap.err
    assert "0 added, 0 deleted, 0 changed" in cap.err
    assert "reimported" not in cap.out


def test_reimport_refuses_a_level_that_does_not_exist(capsys, tmp_project):
    rc = _reimport(_FIXTURES / "paste.dx", "level/does-not-exist", project=tmp_project)
    err = capsys.readouterr().err

    assert rc == 2
    assert "level not found: 'does-not-exist'" in err


def test_reimport_preserves_folders_and_labels_on_an_untouched_actor(tmp_project):
    """The compiled map format carries neither — a matched, UNCHANGED actor's sidecar must survive
    reimport untouched (spec: 'Folder/label sidecars are left untouched')."""
    _seed(tmp_project)
    level_dir = tmp_project / "maps" / "m03-study"
    (level_dir / "actors" / "ProbeRoom" / "folder").write_text("dungeon.hall\n")

    rc = _reimport(_FIXTURES / "paste.dx", "level/m03-study", project=tmp_project)

    assert rc == 0
    level, _ranks = trunk.read_level(level_dir)
    assert level.actors["ProbeRoom"].folder == "dungeon.hall"


def test_a_changed_matched_actor_keeps_its_folder_and_labels(tmp_project):
    """Regression for the bug filed at
    dev/docs/board/inbox/level-reimport-drops-folder-labels-sidecar-on-a: a matched actor whose
    body actually changes must still keep its folder/labels — the compiled map carries neither, so
    the write must carry them over from the trunk."""
    _seed(tmp_project)
    level_dir = tmp_project / "maps" / "m03-study"
    actor_dir = level_dir / "actors" / "ProbeRoom"
    body = (actor_dir / "actor.t3d").read_text()
    (actor_dir / "actor.t3d").write_text(body.replace("End Actor", '    Tag="WasHere"\nEnd Actor'))
    (actor_dir / "folder").write_text("dungeon.hall\n")
    (actor_dir / "labels").write_text("flammable\n")

    # 1 of 3 actors modified is 33% — over the unrelated 20% blast-radius guard, so --force here.
    rc = _reimport(_FIXTURES / "paste.dx", "level/m03-study", project=tmp_project, force=True)

    assert rc == 0
    level, _ranks = trunk.read_level(level_dir)
    assert level.actors["ProbeRoom"].folder == "dungeon.hall"
    assert level.actors["ProbeRoom"].labels == frozenset({"flammable"})


def test_added_actors_get_a_shared_reimport_label(tmp_project):
    _seed(tmp_project)
    level_dir = tmp_project / "maps" / "m03-study"
    shutil.rmtree(level_dir / "actors" / "ProbePillar")   # now "added" when paste.dx is reimported

    rc = _reimport(_FIXTURES / "paste.dx", "level/m03-study", project=tmp_project)

    assert rc == 0
    level, _ranks = trunk.read_level(level_dir)
    labels = level.actors["ProbePillar"].labels
    assert len(labels) == 1
    (label,) = labels
    assert label.startswith("reimport-")
    assert level.actors["LevelInfo0"].labels == frozenset()   # untouched actors get no label


def test_an_actor_absent_from_the_map_is_deleted_even_if_added_after_the_last_materialize(
        tmp_project):
    """`level reimport` diffs the CURRENT on-disk trunk against the decode — it has no notion of
    "since the materialize that produced MAPFILE", only "in the map, or not". An actor added to the
    trunk by a concurrent session (or by hand) after that materialize is therefore deleted, exactly
    like `level import --overwrite` already deletes anything the fresh import doesn't mention. This
    is a known, accepted limitation (spec: the write mechanism is shared with `--overwrite`'s
    whole-trunk delete, just scoped to the real diff) — not a guarantee reimport makes. `--force`
    sidesteps the (unrelated) blast-radius guard: deleting 1 of the resulting 4 actors is 25%,
    just over the 20% threshold, and that guard is Task 2's concern, not this one's."""
    _seed(tmp_project)
    level_dir = tmp_project / "maps" / "m03-study"
    extra_dir = level_dir / "actors" / "SomeOtherActor"
    extra_dir.mkdir()
    (extra_dir / "actor.t3d").write_text("Begin Actor Class=Engine.Light\nEnd Actor")
    (extra_dir / "order_value").write_text("zz\n")

    rc = _reimport(_FIXTURES / "paste.dx", "level/m03-study", project=tmp_project, force=True)

    assert rc == 0
    level, _ranks = trunk.read_level(level_dir)
    assert "SomeOtherActor" not in level.actors


def test_the_blast_radius_guard_refuses_without_force(capsys, tmp_project):
    _seed(tmp_project)
    level_dir = tmp_project / "maps" / "m03-study"
    for n in ("Extra1", "Extra2", "Extra3", "Extra4", "Extra5", "Extra6", "Extra7"):
        d = level_dir / "actors" / n
        d.mkdir()
        (d / "actor.t3d").write_text("Begin Actor Class=Engine.Light\nEnd Actor")
        (d / "order_value").write_text(trunk.append_rank({}) + "\n")
    # Trunk now holds 3 (paste.dx) + 7 = 10 actors; reimporting paste.dx alone deletes the 7 extras
    # — 7/10 = 70%, over the 20% guard.

    rc = _reimport(_FIXTURES / "paste.dx", "level/m03-study", project=tmp_project)
    err = capsys.readouterr().err

    assert rc == 2
    assert "70%" in err

    level, _ranks = trunk.read_level(level_dir)
    assert "Extra1" in level.actors, "the guard must refuse BEFORE writing anything"


def test_force_overrides_the_blast_radius_guard(tmp_project):
    _seed(tmp_project)
    level_dir = tmp_project / "maps" / "m03-study"
    for n in ("Extra1", "Extra2", "Extra3", "Extra4", "Extra5", "Extra6", "Extra7"):
        d = level_dir / "actors" / n
        d.mkdir()
        (d / "actor.t3d").write_text("Begin Actor Class=Engine.Light\nEnd Actor")
        (d / "order_value").write_text(trunk.append_rank({}) + "\n")

    rc = _reimport(_FIXTURES / "paste.dx", "level/m03-study", project=tmp_project, force=True)

    assert rc == 0
    level, _ranks = trunk.read_level(level_dir)
    assert "Extra1" not in level.actors
