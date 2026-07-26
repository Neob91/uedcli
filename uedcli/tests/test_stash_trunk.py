"""Stash on the git-native path: capture writes to the self-ignoring `<root>/.uedcli/stash/` register,
apply merges through the `LevelSource` seam into the on-disk trunk with random-suffix names — all
through `dispatch()` with a project + selected level and NO session."""
import argparse
from pathlib import Path

from uedcli import dispatch, trunk
from uedcli.model import Actor, Level


def _project_with_level(tmp_path, monkeypatch, name="lvl"):
    proj = tmp_path / "repo"
    (proj / "maps" / name).mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    lvl = Level(actors={"Lamp": Actor(name="Lamp", cls="Light", location=(128, 256, 64)),
                        "Torch": Actor(name="Torch", cls="Light", location=(512, 64, 0))})
    trunk.write_level(proj / "maps" / name, lvl, {"Lamp": "m", "Torch": "t"})
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    return proj, name


def _capture_ns(proj, *, sid):
    return argparse.Namespace(cmd="stash", sub="capture", id=sid, force=False, names=[],
                              from_t3d=None,
                              project=str(proj))


def _apply_ns(proj, *, sid):
    return argparse.Namespace(cmd="stash", sub="apply", id=sid, at=None, group=None,
                              no_group=False, project=str(proj))


def test_it_captures_the_trunk_into_the_gitignored_register(tmp_path, monkeypatch):
    proj, _ = _project_with_level(tmp_path, monkeypatch)

    rc = dispatch.dispatch(_capture_ns(proj, sid="cap1"))

    assert rc == 0
    # first state-dir use wrote the `*` self-ignore (acceptance §10.3)
    assert (proj / ".uedcli" / ".gitignore").read_text() == "*\n"
    reg_dir = proj / ".uedcli" / "stash" / "cap1"
    assert reg_dir.is_dir()
    captured = {d.name for d in (reg_dir / "actors").iterdir() if d.is_dir()}
    assert captured == {"Lamp", "Torch"}


def test_it_applies_a_stash_back_into_the_trunk_with_random_suffix_names(tmp_path, monkeypatch):
    proj, name = _project_with_level(tmp_path, monkeypatch)
    assert dispatch.dispatch(_capture_ns(proj, sid="cap1")) == 0

    rc = dispatch.dispatch(_apply_ns(proj, sid="cap1"))

    assert rc == 0
    got, ranks = trunk.read_level(proj / "maps" / name)
    # the two originals survive; two random-suffix copies are appended
    assert {"Lamp", "Torch"} <= set(got.actors)
    added = set(got.actors) - {"Lamp", "Torch"}
    assert len(added) == 2
    for n in added:
        assert "_" in n and n.split("_")[0] in {"Lamp", "Torch"}
    # every actor carries a distinct order_value (no rank collision on append)
    assert len(set(ranks.values())) == len(ranks) == 4

