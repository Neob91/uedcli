"""The `level import` verb: destination resolution, the write path, and every refusal.

`level import MAPFILE --tree level|stash/NAME [--overwrite]` decodes a COMPILED map file into a new
T3D tree. It is the inverse of `level materialize`, and unlike materialize it needs no editor and no
container — it reads the map's bytes.

These tests run the real verb through `dispatch`, against the committed editor-built map fixtures
and the committed class packages, into a temporary project. The one thing they patch is the seam
that finds the game's class packages (`dispatch._class_index`), pointing it at the committed
`uned/UED22` tree instead of a game install the offline suite does not have.

Spec: `dev/docs/specs/2026-07-24-level-import.md` §4 (verb surface) and §6 (write path).
"""
from __future__ import annotations

import argparse
from pathlib import Path
from unittest import mock

import pytest

from uedcli import dispatch, trunk
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


def _ns(mapfile, tree, *, project, overwrite=False) -> argparse.Namespace:
    return argparse.Namespace(cmd="level", sub="import", mapfile=str(mapfile), tree=tree,
                              overwrite=overwrite, project=str(project), container="c")


def _run(mapfile, tree, *, project, overwrite=False) -> int:
    """Run the verb with the class-package seam pointed at the committed UED22 tree."""
    with mock.patch("uedcli.dispatch._class_index", _real_index):
        return dispatch.dispatch(_ns(mapfile, tree, project=project, overwrite=overwrite))


# ── the happy paths ──────────────────────────────────────────────────────────────────────────

def test_importing_into_a_level_writes_a_readable_trunk(capsys, tmp_project):
    """A compiled map becomes a level trunk holding only its content actors.

    `paste.dx` holds ten actors: the level-info singleton, two real brushes (a subtractive room and
    an additive pillar), and seven pieces of editor apparatus (the builder brush plus six viewport
    cameras). Only the first three are content, so only those are written.
    """
    rc = _run(_FIXTURES / "paste.dx", "level/m03-study", project=tmp_project)
    out = capsys.readouterr().out

    assert rc == 0
    assert out.split() == ["LevelInfo0", "ProbeRoom", "ProbePillar"]

    level, ranks = trunk.read_level(tmp_project / "maps" / "m03-study")
    assert sorted(level.actors) == ["LevelInfo0", "ProbePillar", "ProbeRoom"]
    assert set(ranks) == set(level.actors), "every imported actor needs an order_value"
    # The brush geometry survived the whole trip to disk.
    assert len(level.actors["ProbeRoom"].brush.polys) == 6
    # (Class names reach the trunk fully qualified; the offline suite stubs the validation gate that
    # does that, so it is asserted separately below under `real_validation`.)


def test_the_import_summary_and_hint_go_to_stderr_not_stdout(capsys, tmp_project):
    """Actor names are the pipeable result on stdout; the human summary is on stderr.

    Producer verbs print their result one item per line so it can be piped onward, and keep counts
    and advice off that pipe. The summary also names what it dropped, so a shrinking import is
    visible rather than silent.
    """
    rc = _run(_FIXTURES / "paste.dx", "level/m03-study", project=tmp_project)
    cap = capsys.readouterr()

    assert rc == 0
    assert "imported 3 actor(s)" in cap.err
    assert "dropped 7 editor scratch object(s)" in cap.err
    assert "export UEDCLI_LEVEL=m03-study" in cap.err
    # None of that pollutes the pipe.
    assert "imported" not in cap.out and "UEDCLI_LEVEL" not in cap.out


def test_importing_into_a_stash_writes_a_readable_stash_entry(capsys, tmp_project):
    """A stash destination stores the same actors as a stash entry rather than a level trunk."""
    rc = _run(_FIXTURES / "paste.dx", "stash/import-1337", project=tmp_project)
    out = capsys.readouterr().out

    assert rc == 0
    assert out.split() == ["LevelInfo0", "ProbeRoom", "ProbePillar"]

    reg = dispatch._stash_register_for(
        dispatch.config.resolve_project(env_project=str(tmp_project), cwd=str(tmp_project)))
    assert reg.exists("import-1337")
    actors_t3d, order, _packages, meta, _folders = reg.read_stash("import-1337")
    assert order == ["LevelInfo0", "ProbeRoom", "ProbePillar"]
    assert sorted(actors_t3d) == ["LevelInfo0", "ProbePillar", "ProbeRoom"]
    assert meta["source_map"] == "paste.dx", "the stash records which map it came from"


@pytest.mark.parametrize("stem", ["paste", "import", "importadd"])
def test_every_committed_editor_map_imports_cleanly(capsys, tmp_project, stem):
    """All three committed editor-built maps import end to end without error."""
    rc = _run(_FIXTURES / f"{stem}.dx", f"level/from-{stem}", project=tmp_project)
    capsys.readouterr()

    assert rc == 0
    level, _ranks = trunk.read_level(tmp_project / "maps" / f"from-{stem}")
    assert "LevelInfo0" in level.actors
    # Compare the SHORT class name: this test is not marked `real_validation`, so the autouse
    # fixture stubs out the gate that qualifies `Camera` to `Engine.Camera`. Asserting on the
    # qualified spelling here would be vacuous — it could never appear however the code behaved.
    assert not any(a.cls.rsplit(".", 1)[-1] == "Camera" for a in level.actors.values()), \
        "viewport cameras must never reach the trunk"
    assert not any(n.startswith("Camera") for n in level.actors), \
        "viewport cameras must never reach the trunk"


# ── the overwrite guard ──────────────────────────────────────────────────────────────────────

def test_an_existing_level_is_refused_without_overwrite(capsys, tmp_project):
    """Importing over a level that already has actors exits 2 rather than clobbering it."""
    assert _run(_FIXTURES / "paste.dx", "level/m03-study", project=tmp_project) == 0
    capsys.readouterr()

    rc = _run(_FIXTURES / "paste.dx", "level/m03-study", project=tmp_project)
    err = capsys.readouterr().err

    assert rc == 2
    assert "level already exists: m03-study" in err
    assert "--overwrite" in err


def test_an_existing_stash_is_refused_without_overwrite(capsys, tmp_project):
    assert _run(_FIXTURES / "paste.dx", "stash/import-1337", project=tmp_project) == 0
    capsys.readouterr()

    rc = _run(_FIXTURES / "paste.dx", "stash/import-1337", project=tmp_project)
    err = capsys.readouterr().err

    assert rc == 2
    assert "stash already exists" in err and "import-1337" in err


def test_overwrite_replaces_the_level_and_prunes_what_is_no_longer_there(capsys, tmp_project):
    """`--overwrite` leaves the level holding EXACTLY the newly imported actors.

    The trunk writer is deliberately a delta write — it leaves actor directories it was not told
    about alone, so that concurrent edits to different actors compose instead of stomping each
    other. That makes an overwrite import a trap: without naming the previous level's actors as
    deletions, they would linger and silently merge into the imported level. Here the first import
    brings in a brush the second one does not, so a surviving leftover is detectable.
    """
    assert _run(_FIXTURES / "paste.dx", "level/m03-study", project=tmp_project) == 0
    level_dir = tmp_project / "maps" / "m03-study"
    before, _ = trunk.read_level(level_dir)
    assert "ProbePillar" in before.actors
    # Plant an extra actor that the re-import will not produce.
    ranks = {n: trunk.append_rank({}) for n in before.actors}
    (level_dir / "actors" / "LeftoverLight").mkdir(parents=True)
    (level_dir / "actors" / "LeftoverLight" / "actor.t3d").write_text(
        "Begin Actor Class=Engine.Light Name=LeftoverLight\nEnd Actor\n")
    (level_dir / "actors" / "LeftoverLight" / "order_value").write_text(
        trunk.append_rank(ranks))
    assert "LeftoverLight" in trunk.read_level(level_dir)[0].actors
    capsys.readouterr()

    rc = _run(_FIXTURES / "paste.dx", "level/m03-study", project=tmp_project, overwrite=True)
    capsys.readouterr()

    assert rc == 0
    after, _ = trunk.read_level(level_dir)
    assert sorted(after.actors) == ["LevelInfo0", "ProbePillar", "ProbeRoom"]
    assert "LeftoverLight" not in after.actors, \
        "an --overwrite import left a stale actor behind, silently merging two levels"


def test_an_empty_level_directory_does_not_count_as_existing(capsys, tmp_project):
    """A half-created or emptied level needs no `--overwrite` — matching `level create`'s rule.

    Otherwise a previous failed run would leave a directory that permanently demands a flag to
    retry past, for no benefit: there is nothing there to lose.
    """
    (tmp_project / "maps" / "m03-study" / "actors").mkdir(parents=True)

    rc = _run(_FIXTURES / "paste.dx", "level/m03-study", project=tmp_project)
    capsys.readouterr()

    assert rc == 0


# ── the refusals ─────────────────────────────────────────────────────────────────────────────

def test_a_prefab_destination_is_refused(capsys, tmp_project):
    """A prefab is a small reusable fragment, not a home for a whole imported level."""
    rc = _run(_FIXTURES / "paste.dx", "prefab/door", project=tmp_project)
    err = capsys.readouterr().err

    assert rc == 2
    assert "prefab is not a valid import destination" in err


@pytest.mark.parametrize("tree", ["", "level", "level/", "/name", "bogus/name"])
def test_a_malformed_tree_value_is_refused_naming_it(capsys, tmp_project, tree):
    """The destination must be `level/NAME` or `stash/NAME`; anything else exits 2 naming it."""
    rc = _run(_FIXTURES / "paste.dx", tree, project=tmp_project)
    err = capsys.readouterr().err

    assert rc == 2
    assert "--tree must be level/NAME or stash/NAME" in err


def test_a_destination_name_escaping_the_project_is_refused(capsys, tmp_project):
    """A traversing name cannot be used to write outside the project's own directories."""
    rc = _run(_FIXTURES / "paste.dx", "stash/../../escape", project=tmp_project)
    err = capsys.readouterr().err

    assert rc == 2
    assert err.strip(), "a traversing destination must be refused with a message"
    assert not (tmp_project.parent.parent / "escape").exists()


def test_a_missing_map_file_is_refused_naming_it(capsys, tmp_project):
    rc = _run(_FIXTURES / "no-such-map.dx", "level/m03-study", project=tmp_project)
    err = capsys.readouterr().err

    assert rc == 2
    assert "map file not found" in err and "no-such-map.dx" in err


def test_a_file_that_is_not_a_package_is_refused_naming_it(capsys, tmp_project, tmp_path):
    """A text file, a truncated map, or anything without the UE1 package magic exits 2 naming it —
    never a traceback out of the binary parser."""
    bogus = tmp_path / "not-a-map.dx"
    bogus.write_text("this is not a compiled Unreal package\n")

    rc = _run(bogus, "level/m03-study", project=tmp_project)
    err = capsys.readouterr().err

    assert rc == 2
    assert "not-a-map.dx" in err


# ── strict validation, with the real gate running ────────────────────────────────────────────
#
# The offline suite stubs the class/texture ingest gate to a no-op by default (the game install it
# needs is not present), so the tests above cannot see it work. These opt back in with
# `real_validation` and inject the committed UED22 packages as the substrate.

class _AnyTexture:
    """A texture resolver that accepts anything. The committed fixtures' polygons carry no texture
    reference at all, so texture validation is not what these tests are about."""

    def __init__(self, _files):
        pass

    def exists(self, _ref):
        return True


@pytest.fixture
def real_substrate(monkeypatch):
    from uedcli import config, utexture
    monkeypatch.setattr(ClassIndex, "from_project",
                        classmethod(lambda cls, project, user_config: _real_index()))
    monkeypatch.setattr(config, "composed_search_files",
                        lambda project, user_config: [("x.utx", "base")])
    monkeypatch.setattr(config, "load_user_config", lambda: object())
    monkeypatch.setattr(utexture, "TextureResolver", _AnyTexture)


@pytest.mark.real_validation
def test_imported_class_names_reach_the_trunk_fully_qualified(capsys, tmp_project, real_substrate):
    """Import stores `Engine.Brush`, not the short `Brush` the map file itself carries.

    A compiled map names each actor's class without saying which package it came from, because the
    engine already knows. A trunk cannot rely on that, and every other uedcli write path stores the
    fully-qualified name — so an imported tree must match, or `actor find --class`, rebuild, and the
    comparison machinery would all disagree with it.
    """
    rc = _run(_FIXTURES / "paste.dx", "level/m03-study", project=tmp_project)
    capsys.readouterr()

    assert rc == 0
    level, _ranks = trunk.read_level(tmp_project / "maps" / "m03-study")
    assert {a.cls for a in level.actors.values()} == {"Engine.Brush", "Engine.LevelInfo"}


@pytest.mark.real_validation
def test_the_scratch_drop_happens_before_qualification_in_the_real_pipeline(
        capsys, tmp_project, real_substrate):
    """With the real gate running, the builder brush and cameras are still gone.

    This is the end-to-end form of an ordering constraint: the scratch objects are recognised by
    their SHORT class name, and the validation gate rewrites short names to qualified ones. If the
    two steps were ever reordered, the apparatus would survive into the trunk — and it would survive
    looking like ordinary content, since by then its class would read `Engine.Brush` like any other.
    """
    rc = _run(_FIXTURES / "paste.dx", "level/m03-study", project=tmp_project)
    capsys.readouterr()

    assert rc == 0
    level, _ranks = trunk.read_level(tmp_project / "maps" / "m03-study")
    assert sorted(level.actors) == ["LevelInfo0", "ProbePillar", "ProbeRoom"]
    assert not any(a.cls == "Engine.Camera" for a in level.actors.values())


def test_the_overwrite_guard_runs_before_the_map_file_is_read(capsys, tmp_project):
    """A refused destination is reported even when the map file does not exist at all.

    This pins the ORDER: the destination check comes first, so refusing an import never pays the
    cost of reading (or even finding) a large map file. If the order inverted, the error below would
    complain about the missing file instead.
    """
    assert _run(_FIXTURES / "paste.dx", "level/m03-study", project=tmp_project) == 0
    capsys.readouterr()

    rc = _run(_FIXTURES / "no-such-map.dx", "level/m03-study", project=tmp_project)
    err = capsys.readouterr().err

    assert rc == 2
    assert "level already exists" in err
    assert "map file not found" not in err
