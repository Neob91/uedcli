"""Hard-cutover migration + folder persistence + capture-normalization for the unified T3D trees
(decisions.md 2026-07-18 23:01 UTC addendum). Migration is a HARD CUTOVER: an old single-blob prefab
is NOT auto-converted — reading one is a clean, actionable error; the user re-captures it.
"""
import argparse
from decimal import Decimal

import pytest

from uedcli import dispatch, stashlib, stash_register
from uedcli.model import Actor
from uedcli.normalize import canonical_actor_t3d


def _cube_blob(name):
    from uedcli import builders
    brush = builders.cube(64.0, 64.0, 64.0, "DeusExDeco.Stone.Block")
    return canonical_actor_t3d(builders.make_brush_actor(name, brush, location=(0.0, 0.0, 0.0)))


# ── HARD CUTOVER: an old-format prefab raises a clean, actionable error ──────────────────────

def test_old_format_prefab_read_raises_actionable_error(tmp_path):
    root = tmp_path / "Prefabs"
    root.mkdir()
    (root / "door.t3d").write_text("Begin Map\n" + _cube_blob("Panel") + "\nEnd Map\n")
    (root / "door.json").write_text('{"order": ["Panel"], "packages": ["DeusExDeco"]}')
    # It LISTS (so the error surfaces on use, not a misleading "not found")...
    assert "door" in stashlib.list_prefabs(root)
    # ...and reading it is a clean OldFormatPrefab naming the prefab, never a traceback.
    with pytest.raises(stashlib.OldFormatPrefab, match="old-format prefab 'door' — re-capture it"):
        stashlib.read_prefab(root, "door")


def test_old_format_prefab_via_dispatch_is_exit2_no_traceback(tmp_path, capsys):
    root = tmp_path / "Prefabs"
    root.mkdir()
    (root / "arch.t3d").write_text("Begin Map\n" + _cube_blob("Panel") + "\nEnd Map\n")
    (root / "arch.json").write_text('{"order": ["Panel"], "packages": []}')
    rc = dispatch.dispatch(argparse.Namespace(cmd="prefab", sub="show", name="arch", names=[],
                                              summary=False, prefab_dir=str(root), container="c"))
    assert rc == 2
    err = capsys.readouterr().err
    assert "old-format prefab 'arch' — re-capture it (the on-disk format changed)" in err
    assert "Traceback" not in err


def test_new_dir_shadows_a_leftover_old_file(tmp_path):
    # If both an old <name>.t3d and a new <name>/ dir exist, the NEW dir wins (read_prefab keys on
    # dest.is_dir() first), so a stale leftover file never masks the migrated prefab.
    root = tmp_path / "Prefabs"
    stashlib.write_prefab(root, "door", full_level={"Panel": _cube_blob("Panel")}, order=["Panel"],
                          packages=[], meta={})
    (root / "door.t3d").write_text("Begin Map\nStale\nEnd Map\n")
    full, order, _pkgs, _meta, _folders = stashlib.read_prefab(root, "door")
    assert order == ["Panel"] and "Panel" in full


# ── Folder persistence: capture → store → read → apply, and --folder override ────────────────

def _project_with_level(tmp_path, monkeypatch, name="lvl"):
    proj = tmp_path / "repo"
    maps = proj / "maps" / name
    maps.mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    return proj, name, maps


def test_folder_persists_through_capture_store_read_and_apply(tmp_path, monkeypatch):
    proj, name, maps = _project_with_level(tmp_path, monkeypatch)
    # Seed a trunk actor carrying a folder, via the shared writer.
    from uedcli import trunk, t3dtree
    from uedcli.model import Level
    a = Actor(name="Torch", cls="Engine.Light", location=(Decimal(0), Decimal(0), Decimal(0)),
              folder="castle.tower")
    lvl = Level(actors={"Torch": a}, order=["Torch"])
    trunk.write_level(maps, lvl, dict(zip(["Torch"], t3dtree.initial_ranks(1))))

    reg = stash_register.FileStashRegister(proj / ".uedcli" / "stash")
    # Capture the selected level's actors into a stash (folder rides the separate channel).
    cap = argparse.Namespace(cmd="stash", sub="capture", id="cap", force=False, names=[],
                             from_t3d=None, project=str(proj))
    assert dispatch.dispatch(cap) == 0

    # Stored: the per-member folder sidecar exists and read_stash surfaces it.
    assert (reg.root / "cap" / "actors" / "Torch" / "folder").read_text().strip() == "castle.tower"
    _a, _o, _p, _m, folders = reg.read_stash("cap")
    assert folders == {"Torch": "castle.tower"}

    # Apply into the trunk WITHOUT --folder → the placed actor defaults to its stored folder.
    ap = argparse.Namespace(cmd="stash", sub="apply", id="cap", at=None, group=None, no_group=False,
                            folder=None, project=str(proj))
    assert dispatch.dispatch(ap) == 0
    placed, _ranks = trunk.read_level(maps)
    added = [n for n in placed.actors if n != "Torch"]
    assert len(added) == 1
    assert placed.actors[added[0]].folder == "castle.tower"     # stored folder honoured as default


def test_apply_folder_flag_overrides_the_stored_folder(tmp_path, monkeypatch):
    proj, name, maps = _project_with_level(tmp_path, monkeypatch)
    from uedcli import trunk, t3dtree
    from uedcli.model import Level
    a = Actor(name="Torch", cls="Engine.Light", location=(Decimal(0), Decimal(0), Decimal(0)),
              folder="castle.tower")
    lvl = Level(actors={"Torch": a}, order=["Torch"])
    trunk.write_level(maps, lvl, dict(zip(["Torch"], t3dtree.initial_ranks(1))))

    assert dispatch.dispatch(argparse.Namespace(
        cmd="stash", sub="capture", id="cap", force=False, names=[], from_t3d=None,
        project=str(proj))) == 0

    ap = argparse.Namespace(cmd="stash", sub="apply", id="cap", at=None, group=None, no_group=False,
                            folder="barracks", project=str(proj))
    assert dispatch.dispatch(ap) == 0
    placed, _ranks = trunk.read_level(maps)
    added = [n for n in placed.actors if n != "Torch"]
    assert placed.actors[added[0]].folder == "barracks"        # --folder overrides the stored one


# ── Capture-time mover canonicalization (§3) ─────────────────────────────────────────────────

def test_external_mover_captured_at_nonzero_keynum_stores_canonical(tmp_path, monkeypatch):
    proj, name, maps = _project_with_level(tmp_path, monkeypatch)
    reg = stash_register.FileStashRegister(proj / ".uedcli" / "stash")
    mover = ("Begin Actor Class=Engine.Mover Name=M\n    KeyNum=2\n"
             "    KeyPos(2)=(Z=256.000000)\n    NumKeys=3\n"
             "    Location=(X=0.000000,Y=0.000000,Z=356.000000)\n    Name=\"M\"\nEnd Actor\n")
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO("Begin Map\n" + mover + "End Map\n"))
    cap = argparse.Namespace(cmd="stash", sub="capture", id="mv", force=False, names=[],
                             from_t3d=["-"], project=str(proj))
    assert dispatch.dispatch(cap) == 0
    stored = (reg.root / "mv" / "actors" / "M" / "actor.t3d").read_text()
    # Canonicalized at CAPTURE: KeyNum folded away (the read path no longer does this). The base pose
    # then rides to the bbox-min origin via normalize_for_capture, so what pins canonicalization is
    # the absence of KeyNum while the relative KeyPos offset is preserved unchanged.
    assert "KeyNum" not in stored
    assert "KeyPos(2)=(Z=256.000000)" in stored
    # Read-back through the shared path is likewise canonical (no KeyNum resurrected).
    actors, _o, _p, _m, _f = reg.read_stash("mv")
    assert "KeyNum" not in actors["M"]
