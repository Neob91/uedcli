import subprocess
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from uedcli import stash_register, trunk
from uedcli.cli import dispatch
from uedcli.model import Actor, Level

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"     # every preview write is a PNG (there is no PPM route)

_ARCH_T3D = (
    "Begin Actor Class=Brush Name=Arch\n    Begin Brush Name=Model7\n"
    "       Begin PolyList\n         Begin Polygon Texture=DeusExDeco.Stone.Block\n"
    "          Vertex +0.000000,+0.000000,+0.000000\n"
    "          Vertex +64.000000,+0.000000,+0.000000\n"
    "          Vertex +64.000000,+64.000000,+0.000000\n         End Polygon\n"
    "       End PolyList\n    End Brush\n    Name=\"Arch\"\nEnd Actor\n")


def _project_with_level(tmp_path, monkeypatch, name="lvl"):
    """A `<tmp>/repo` project ROOT (new layout: `<root>/uedcli.toml`) with `name` set as the ambient
    `$UEDCLI_LEVEL`. The ambient trunk level is the git-native replacement for the old session's
    `main/` — default-source capture and apply read/write it."""
    proj = tmp_path / "repo"
    (proj / "maps" / name).mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    lvl = Level(actors={"Lamp": Actor(name="Lamp", cls="Light", location=(128, 256, 64))})
    lvl.order = ["Lamp"]
    trunk.write_level(proj / "maps" / name, lvl, {"Lamp": "m"})
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    return proj, name


def _args(proj, **kw):
    base = dict(cmd="stash", project=str(proj), container="c")
    base.update(kw)
    return SimpleNamespace(**base)


def _register(proj):
    return stash_register.FileStashRegister(proj / ".uedcli" / "stash")


def test_it_captures_a_t3d_file_into_a_session_register(tmp_path, monkeypatch):
    proj, _ = _project_with_level(tmp_path, monkeypatch)
    t3d = tmp_path / "arch.t3d"
    t3d.write_text("Begin Map\n" + _ARCH_T3D + "End Map\n")

    rc = dispatch.dispatch(_args(proj, sub="capture", names=[], id="archway",
                                 from_t3d=[str(t3d)], force=False))
    assert rc == 0

    reg = _register(proj)
    assert reg.list_stashes() == ["archway"]
    actors, order, packages, _meta, _folders = reg.read_stash("archway")
    assert "Arch" in actors and order == ["Arch"]
    assert "DeusExDeco" in packages          # texture package derived at capture
    # geometry survived parse->normalize (decimal vertices) — non-degenerate after bbox-min shift
    from uedcli.model import parse_t3d
    from uedcli.writes import union_bounds
    lo, hi = union_bounds(list(parse_t3d("Begin Map\n" + actors["Arch"] + "End Map\n").actors.values()))
    assert hi != lo


def test_it_captures_from_stdin(tmp_path, monkeypatch, capsys):
    proj, _ = _project_with_level(tmp_path, monkeypatch)
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO("Begin Map\n" + _ARCH_T3D + "End Map\n"))
    rc = dispatch.dispatch(_args(proj, sub="capture", names=["-"], id="a",
                                 from_t3d=None, force=False))
    assert rc == 0
    assert capsys.readouterr().out.strip() == "a"          # prints the stored id
    actors, order, _pkgs, _meta, _folders = _register(proj).read_stash("a")
    assert "Arch" in actors and order == ["Arch"]           # the piped actor is stored


def test_it_errors_on_a_missing_requested_actor(tmp_path, monkeypatch):
    proj, _ = _project_with_level(tmp_path, monkeypatch)
    t3d = tmp_path / "arch.t3d"; t3d.write_text("Begin Map\n" + _ARCH_T3D + "End Map\n")
    rc = dispatch.dispatch(_args(proj, sub="capture", names=["Nope"], id="x",
                                 from_t3d=[str(t3d)], force=False))
    assert rc == 2          # CommandError -> exit 2


def _tri(name, x):
    """A non-degenerate triangle brush named `name`, offset by `x` on X (for duplicate-Name tests)."""
    return (
        f"Begin Actor Class=Brush Name={name}\n    Begin Brush Name=Model_{name}\n"
        "       Begin PolyList\n         Begin Polygon Texture=DeusExDeco.Stone.Block\n"
        f"          Vertex +{x}.000000,+0.000000,+0.000000\n"
        f"          Vertex +{x + 64}.000000,+0.000000,+0.000000\n"
        f"          Vertex +{x + 64}.000000,+64.000000,+0.000000\n         End Polygon\n"
        "       End PolyList\n    End Brush\n"
        f"    Name=\"{name}\"\nEnd Actor\n")


def test_capture_from_stdin_duplicate_named_actors_all_survive(tmp_path, monkeypatch):
    # Regression: capturing user T3D with N identical Names must keep all N (parse_t3d collapsed).
    proj, _ = _project_with_level(tmp_path, monkeypatch)
    import io
    monkeypatch.setattr("sys.stdin",
                        io.StringIO("Begin Map\n" + _tri("Merlon", 0) + _tri("Merlon", 128) + "End Map\n"))
    rc = dispatch.dispatch(_args(proj, sub="capture", names=["-"], id="wall",
                                 from_t3d=None, force=False))
    assert rc == 0
    actors, order, _pkgs, _meta, _folders = _register(proj).read_stash("wall")
    assert len(actors) == 2 and len(order) == 2                     # both survived, distinct
    assert order[0] == "Merlon"                                     # first keeps its bare Name


def test_capture_filter_then_uniquify_keeps_all_matches(tmp_path, monkeypatch):
    # The filter-before-uniquify order: an explicit `Merlon` filter over a duplicated source keeps
    # BOTH (uniquifying first would suffix the 2nd so the bare filter matched only the 1st).
    proj, _ = _project_with_level(tmp_path, monkeypatch)
    import io
    monkeypatch.setattr("sys.stdin",
                        io.StringIO("Begin Map\n" + _tri("Merlon", 0) + _tri("Merlon", 128) + "End Map\n"))
    rc = dispatch.dispatch(_args(proj, sub="capture", names=["-", "Merlon"], id="w2",
                                 from_t3d=None, force=False))
    assert rc == 0
    actors, order, _pkgs, _meta, _folders = _register(proj).read_stash("w2")
    assert len(actors) == 2                                         # both matches captured, not 1


def test_stdin_source_with_from_t3d_is_a_two_source_error(tmp_path, monkeypatch, capsys):
    proj, _ = _project_with_level(tmp_path, monkeypatch)
    t3d = tmp_path / "arch.t3d"; t3d.write_text("Begin Map\n" + _ARCH_T3D + "End Map\n")
    rc = dispatch.dispatch(_args(proj, sub="capture", names=["-"], id="x",
                                 from_t3d=[str(t3d)], force=False))
    assert rc == 2
    assert "cannot be combined with --from-t3d" in capsys.readouterr().err


def test_stdin_source_with_tree_is_a_two_source_error(tmp_path, monkeypatch, capsys):
    proj, name = _project_with_level(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_args(proj, sub="capture", names=["-"], id="x",
                                 tree=f"level/{name}", from_t3d=None, force=False))
    assert rc == 2
    assert "cannot be combined with --tree" in capsys.readouterr().err


def test_from_t3d_dash_the_removed_spelling_is_rejected(tmp_path, monkeypatch, capsys):
    # Pin the removal: `--from-t3d -` no longer reads stdin; the sole stdin spelling is a leading -.
    proj, _ = _project_with_level(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_args(proj, sub="capture", names=[], id="x",
                                 from_t3d=["-"], force=False))
    assert rc == 2
    err = capsys.readouterr().err
    assert "--from-t3d takes T3D file(s) only" in err and "stash capture -" in err


def test_empty_stdin_source_is_a_clean_error_not_a_no_op(tmp_path, monkeypatch, capsys):
    # A T3D-snippet source yielding no actors is exit 2 (matching `actor add -`), NOT the name-list
    # no-op — regression for the "never a bare exception" rule.
    proj, _ = _project_with_level(tmp_path, monkeypatch)
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO("   \n"))
    rc = dispatch.dispatch(_args(proj, sub="capture", names=["-"], id="x",
                                 from_t3d=None, force=False))
    assert rc == 2
    err = capsys.readouterr().err
    assert "capture source has no actors" in err and "Traceback" not in err


def test_stdin_source_round_trips_through_show(tmp_path, monkeypatch, capsys):
    # `… | stash capture - --id baked` then `stash show baked` returns the captured actor.
    proj, _ = _project_with_level(tmp_path, monkeypatch)
    import io
    monkeypatch.setattr("sys.stdin",
                        io.StringIO("Begin Map\n" + _cube_actor_t3d("Baked") + "End Map\n"))
    assert dispatch.dispatch(_args(proj, sub="capture", names=["-"], id="baked",
                                   from_t3d=None, force=False)) == 0
    assert capsys.readouterr().out.strip() == "baked"
    assert dispatch.dispatch(_args(proj, sub="show", id="baked", names=[], summary=False)) == 0
    assert "Baked" in capsys.readouterr().out


def test_it_shows_dumps_t3d_and_summary_and_lists_and_drops(tmp_path, monkeypatch, capsys):
    proj, _ = _project_with_level(tmp_path, monkeypatch)
    reg = _register(proj)
    reg.write_stash("archway", full_level={"Arch": "Begin Actor Class=Brush Name=Arch\nEnd Actor\n"},
                    order=["Arch"], packages=[], meta={"anchor": ["0", "0", "0"], "ts": 1})

    assert dispatch.dispatch(_args(proj, sub="show", id="archway",
                                   names=[], summary=False)) == 0
    assert "Begin Actor" in capsys.readouterr().out

    assert dispatch.dispatch(_args(proj, sub="show", id="archway",
                                   names=[], summary=True)) == 0
    summary_out = capsys.readouterr().out        # capsys drains on read — capture ONCE
    assert "Arch" in summary_out and "Brush" in summary_out

    assert dispatch.dispatch(_args(proj, sub="list")) == 0
    assert "archway" in capsys.readouterr().out

    assert dispatch.dispatch(_args(proj, sub="drop", id="archway")) == 0
    assert _register(proj).list_stashes() == []


def _cube_actor_t3d(name: str, *, texture: str = "DeusExDeco.Stone.Block") -> str:
    """A canonical, geometrically-valid cube actor block — apply validates geometry up front,
    so the degenerate 3-vertex `_ARCH_T3D` can't be used as an apply source."""
    from uedcli import builders
    from uedcli.normalize import canonical_actor_t3d
    brush = builders.cube(64.0, 64.0, 64.0, texture)
    actor = builders.make_brush_actor(name, brush, location=(0.0, 0.0, 0.0))
    return canonical_actor_t3d(actor)


def test_it_applies_a_stash_merging_translated_grouped_renamed_actors(tmp_path, monkeypatch):
    proj, name = _project_with_level(tmp_path, monkeypatch)
    reg = _register(proj)
    reg.write_stash("archway", full_level={"Arch": _cube_actor_t3d("Arch")}, order=["Arch"],
                    packages=["DeusExDeco"], meta={"anchor": ["0", "0", "0"], "ts": 1})

    rc = dispatch.dispatch(_args(proj, sub="apply", id="archway",
                                 at=(Decimal(512), Decimal(0), Decimal(128)),
                                 group=None, no_group=False))
    assert rc == 0

    got, _ranks = trunk.read_level(proj / "maps" / name)
    placed = [n for n in got.order if n != "Lamp"]     # the pre-seeded Lamp survives; one copy added
    assert len(placed) == 1
    placed = placed[0]
    assert placed.startswith("Arch")                   # random-suffix name off the source stem
    from uedcli.writes import actor_bounds
    a = got.actors[placed]
    # The documented contract: --at anchors the bbox-min CORNER, not the actor Location. The cube
    # is origin-CENTERED (bbox-min = Location + (-32,-32,-32)), so the two genuinely differ.
    assert actor_bounds(a)[0] == (Decimal(512), Decimal(0), Decimal(128))
    assert ("Group", "archway") in a.props             # default group = id


def test_stash_apply_at_anchors_the_bbox_min_corner_for_a_non_origin_source(tmp_path, monkeypatch):
    # Regression for the live Z=768-vs-512 (256uu) offset: a captured set whose stored bbox-min is
    # NOT at the origin (a residual a bare normalize can leave — e.g. a scaled brush) must still
    # place its bbox-min corner EXACTLY at --at. The old code added --at to Location directly,
    # leaking the residual straight into the placement.
    from uedcli import builders
    from uedcli.normalize import canonical_actor_t3d
    from uedcli.writes import actor_bounds
    proj, name = _project_with_level(tmp_path, monkeypatch)
    reg = _register(proj)
    # An origin-centred cube located so its world bbox-min is (100, 100, 256) — a Z residual of 256,
    # exactly the magnitude of the live bug.
    brush = builders.cube(64.0, 64.0, 64.0, "DeusExDeco.Stone.Block")
    actor = builders.make_brush_actor("Wid", brush, location=(132.0, 132.0, 288.0))
    reg.write_stash("w", full_level={"Wid": canonical_actor_t3d(actor)}, order=["Wid"],
                    packages=["DeusExDeco"], meta={"anchor": ["0", "0", "0"], "ts": 1})
    at = (Decimal(2048), Decimal(0), Decimal(512))
    assert dispatch.dispatch(_args(proj, sub="apply", id="w", at=at,
                                   group=None, no_group=False)) == 0
    got, _ranks = trunk.read_level(proj / "maps" / name)
    placed = next(n for n in got.order if n != "Lamp")
    a = got.actors[placed]
    assert actor_bounds(a)[0] == at      # bbox-min lands on --at; the 256 residual is neutralized


def test_it_previews_a_stash_to_png(tmp_path, monkeypatch):
    proj, _ = _project_with_level(tmp_path, monkeypatch)
    reg = _register(proj)
    reg.write_stash("archway", full_level={"Arch": _ARCH_T3D}, order=["Arch"], packages=[],
                    meta={"anchor": ["0", "0", "0"], "ts": 1})
    host_out = str(tmp_path / "out" / "p.png")

    # diagram is host-side only: any docker call means a container crept back in.
    def no_docker(cmd, *a, **kw):
        if cmd and cmd[0] == "docker":
            raise AssertionError(f"stash diagram shelled out to docker: {cmd}")
        from unittest import mock
        return mock.Mock(returncode=0)
    monkeypatch.setattr(subprocess, "run", no_docker)

    rc = dispatch.dispatch(_args(proj, sub="diagram", id="archway", names=[],
                                 view="iso", annotate="all", iso_angle=30.0,
                                 size=128,
                                 out=host_out))
    assert rc == 0
    # the PNG is written straight to the host path (no /work, no docker cp)
    assert Path(host_out).read_bytes().startswith(_PNG_MAGIC)  # geometry survived parse->render


def test_it_routes_actor_preview_from_the_trunk_not_the_editor(tmp_path, monkeypatch):
    # actor diagram is model-side: it reads the ambient trunk level, never MAP EXPORT.
    from uedcli.normalize import canonical_actor_t3d
    from uedcli.model import parse_t3d
    arch = next(iter(parse_t3d("Begin Map\n" + _ARCH_T3D + "End Map\n").actors.values()))
    arch.name = "Arch"
    proj, name = _project_with_level(tmp_path, monkeypatch)
    lvl = Level(actors={"Arch": arch}); lvl.order = ["Arch"]
    trunk.write_level(proj / "maps" / name, lvl, {"Arch": "m"})

    def no_docker(cmd, *a, **kw):                        # host-side only: no container either
        if cmd and cmd[0] == "docker":
            raise AssertionError(f"actor diagram shelled out to docker: {cmd}")
        from unittest import mock
        return mock.Mock(returncode=0)
    monkeypatch.setattr(subprocess, "run", no_docker)

    host_out = str(tmp_path / "out" / "b.png")
    rc = dispatch.dispatch(_args(proj, cmd="actor", sub="diagram",
                                 names=["Arch"], from_t3d=None, view="iso",
                                 annotate="all", iso_angle=30.0,
                                 size=128, out=host_out))
    assert rc == 0
    assert Path(host_out).read_bytes().startswith(_PNG_MAGIC)



def _preview_stash_args(proj, out):
    return _args(proj, sub="diagram", id="archway", names=[], view="iso",
                 annotate="all", iso_angle=30.0,
                 size=128, out=out)


def _stash_archway(tmp_path, monkeypatch):
    proj, _ = _project_with_level(tmp_path, monkeypatch)
    reg = _register(proj)
    reg.write_stash("archway", full_level={"Arch": _ARCH_T3D}, order=["Arch"], packages=[],
                    meta={"anchor": ["0", "0", "0"], "ts": 1})
    return proj


def test_it_writes_a_png_host_side_via_pillow(tmp_path, monkeypatch):
    # Every preview write encodes the in-memory PPM to PNG with Pillow -- there is no PPM route.
    proj = _stash_archway(tmp_path, monkeypatch)
    host_out = str(tmp_path / "out" / "p.ppm")
    rc = dispatch.dispatch(_preview_stash_args(proj, host_out))
    assert rc == 0
    png = tmp_path / "out" / "p.png"                 # .ppm suffix swapped to .png
    assert png.read_bytes().startswith(_PNG_MAGIC)
    assert not (tmp_path / "out" / "p.ppm").exists()  # only the PNG is written


def test_png_out_with_no_extension_under_dotted_parent(tmp_path, monkeypatch):
    # Regression: the extension swap must strip only the basename suffix, never a dot in a
    # parent dir. --out <dotted-dir>/pic (no extension) must land at .../pic.png, not .../.png.
    proj = _stash_archway(tmp_path, monkeypatch)
    out = str(tmp_path / ".cache" / "pic")           # dotted parent, extensionless filename
    rc = dispatch.dispatch(_preview_stash_args(proj, out))
    assert rc == 0
    assert (tmp_path / ".cache" / "pic.png").read_bytes().startswith(_PNG_MAGIC)
    assert not (tmp_path / ".png").exists()           # the old rsplit bug wrote here


def test_preview_write_failure_is_a_clean_error_not_a_traceback(tmp_path, monkeypatch, capsys):
    # A bad --out (parent is an existing FILE) must surface as exit 2 + message, per the
    # "no Python exception reaches the CLI user" rule -- not an OSError traceback.
    proj = _stash_archway(tmp_path, monkeypatch)
    blocker = tmp_path / "blocker"
    blocker.write_bytes(b"not a dir")
    out = str(blocker / "sub" / "p.png")             # mkdir under a file -> NotADirectoryError
    rc = dispatch.dispatch(_preview_stash_args(proj, out))
    assert rc == 2
    assert "could not write preview" in capsys.readouterr().err


def test_it_promotes_a_stash_into_the_library(tmp_path, monkeypatch):
    # No --prefab-dir → the resolved project's prefabs dir (default `<root>/prefabs/`).
    proj, _ = _project_with_level(tmp_path, monkeypatch)
    reg = _register(proj)
    reg.write_stash("archway", full_level={"Arch": "Begin Actor Class=Brush Name=Arch\nEnd Actor\n"},
                    order=["Arch"], packages=["DeusExDeco"], meta={"anchor": ["0", "0", "0"], "ts": 1})
    rc = dispatch.dispatch(_args(proj, sub="promote", id="archway",
                                 as_name="hangar/archway", force=False, prefab_dir=None))
    assert rc == 0
    # A prefab is now a per-actor T3D tree (dir), not a single .t3d blob.
    assert (proj / "prefabs" / "hangar" / "archway" / "actors" / "Arch" / "actor.t3d").is_file()
    assert (proj / "prefabs" / "hangar" / "archway" / "meta.json").is_file()


def test_it_lists_prefabs_with_an_explicit_dir_and_no_project(tmp_path, monkeypatch, capsys):
    # Regression (spec §6): an explicit --prefab-dir needs NO project — the verb must not
    # resolve one (chdir to an isolated dir so walk-up can't find an ambient uedcli.toml).
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("UEDCLI_PROJECT", raising=False)
    from uedcli import stashlib
    stashlib.write_prefab(tmp_path / "Prefabs", "hangar/archway",
                          full_level={"Arch": "Begin Actor Class=Brush Name=Arch\nEnd Actor\n"},
                          order=["Arch"], packages=[], meta={})
    rc = dispatch.dispatch(SimpleNamespace(cmd="prefab", sub="list",
                                           prefab_dir=str(tmp_path / "Prefabs"),
                                           container="c"))
    assert rc == 0
    assert "hangar/archway" in capsys.readouterr().out


def test_prefab_list_without_a_project_or_dir_errors(tmp_path, monkeypatch, capsys):
    # Behavior change (spec §6, stated in help): no project + no --prefab-dir → clean exit 2.
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("UEDCLI_PROJECT", raising=False)
    rc = dispatch.dispatch(SimpleNamespace(cmd="prefab", sub="list", prefab_dir=None,
                                           project=None, container="c"))
    assert rc == 2
    assert "not in a uedcli project" in capsys.readouterr().err


def test_prefab_drop_rejects_escaping_name(tmp_path, monkeypatch):
    # M1: a `..` name must not unlink outside the library root.
    victim = tmp_path / "victim.t3d"
    victim.write_text("precious")
    args = SimpleNamespace(cmd="prefab", sub="drop", name="../victim", container="ct",
                           prefab_dir=str(tmp_path / "Prefabs"))
    assert dispatch.dispatch(args) == 2     # wrapper turns CommandError into exit 2
    assert victim.exists()                  # nothing unlinked outside Prefabs/


def test_prefab_drop_removes_a_new_format_dir(tmp_path):
    # drop must rmtree the new per-actor tree DIR (not just the old .t3d/.json), and remain a clean
    # no-op-ish exit 0.
    from uedcli import stashlib
    root = tmp_path / "Prefabs"
    stashlib.write_prefab(root, "hangar/archway",
                          full_level={"Arch": "Begin Actor Class=Engine.Light Name=Arch\nEnd Actor\n"},
                          order=["Arch"], packages=[], meta={})
    assert (root / "hangar" / "archway" / "actors" / "Arch" / "actor.t3d").is_file()
    args = SimpleNamespace(cmd="prefab", sub="drop", name="hangar/archway", container="ct",
                           prefab_dir=str(root))
    assert dispatch.dispatch(args) == 0
    assert not (root / "hangar" / "archway").exists()          # the whole tree is gone
    assert "hangar/archway" not in stashlib.list_prefabs(root)


def test_prefab_apply_without_a_project_errors(tmp_path, monkeypatch, capsys):
    # With no project, prefab apply resolves no trunk level source and rejects cleanly (exit 2)
    # via `ProjectError`, not a traceback — there is no `--no-session` scratch path anymore.
    # chdir to an isolated dir so the walk-up project resolver can't discover an ambient project
    # (e.g. when the suite runs from inside a checkout that has one) — matches the no-project tests
    # in test_project_show.py.
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("UEDCLI_PROJECT", raising=False)
    args = SimpleNamespace(cmd="prefab", sub="apply", name="arch", at=None, group=None,
                           no_group=False, prefab_dir=str(tmp_path / "Prefabs"), project=None,
                           container="ct")
    assert dispatch.dispatch(args) == 2
    assert "not in a uedcli project" in capsys.readouterr().err


def test_preview_prints_the_rendered_path(tmp_path, monkeypatch, capsys):
    # Restored convenience: preview prints the PNG path actually written, not the name asked for.
    proj, _ = _project_with_level(tmp_path, monkeypatch)
    reg = _register(proj)
    reg.write_stash("arch", full_level={"Arch": _ARCH_T3D}, order=["Arch"], packages=[],
                    meta={"anchor": ["0", "0", "0"], "ts": 1})

    def fake_run(cmd, input=None, **kw):
        from unittest import mock
        return mock.Mock(returncode=0)
    monkeypatch.setattr(subprocess, "run", fake_run)

    asked = str(tmp_path / "out" / "p.ppm")
    rc = dispatch.dispatch(_args(proj, sub="diagram", id="arch", names=[],
                                 view="iso", annotate="all", iso_angle=30.0,
                                 size=128,
                                 out=asked))
    assert rc == 0
    # the HOST PNG path is printed, not the name the caller asked for (and not a /work path)
    assert str(tmp_path / "out" / "p.png") in capsys.readouterr().out


def test_stash_apply_without_at_replays_to_the_recorded_anchor_for_a_non_origin_source(tmp_path, monkeypatch):
    # The no-`--at` path anchors the bbox-min CORNER on the recorded world `anchor` — same residual
    # correctness as the --at path (the old `delta = anchor` only worked for an origin-normalized set).
    from uedcli import builders
    from uedcli.normalize import canonical_actor_t3d
    from uedcli.writes import actor_bounds
    proj, name = _project_with_level(tmp_path, monkeypatch)
    reg = _register(proj)
    brush = builders.cube(64.0, 64.0, 64.0, "DeusExDeco.Stone.Block")
    actor = builders.make_brush_actor("Wid", brush, location=(132.0, 132.0, 288.0))  # bbox-min (100,100,256)
    reg.write_stash("w", full_level={"Wid": canonical_actor_t3d(actor)}, order=["Wid"],
                    packages=["DeusExDeco"], meta={"anchor": ["700", "300", "900"], "ts": 1})
    assert dispatch.dispatch(_args(proj, sub="apply", id="w", at=None,
                                   group=None, no_group=False)) == 0
    got, _ranks = trunk.read_level(proj / "maps" / name)
    placed = next(n for n in got.order if n != "Lamp")
    a = got.actors[placed]
    assert actor_bounds(a)[0] == (Decimal(700), Decimal(300), Decimal(900))   # bbox-min → anchor


# --- not-found / corrupt guards: never a traceback -------------------------------------
def test_stash_show_unknown_id_is_clean_not_found(tmp_path, monkeypatch, capsys):
    proj, _ = _project_with_level(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_args(proj, sub="show", id="nope", names=[], summary=False))
    assert rc == 2
    assert "stash not found: 'nope'" in capsys.readouterr().err


def test_stash_promote_unknown_id_is_clean_not_found(tmp_path, monkeypatch, capsys):
    proj, _ = _project_with_level(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_args(proj, sub="promote", id="nope", as_name="x", force=False,
                                 prefab_dir=str(tmp_path / "Prefabs")))
    assert rc == 2
    assert "stash not found: 'nope'" in capsys.readouterr().err


def test_prefab_show_unknown_name_is_clean_not_found(tmp_path, capsys):
    rc = dispatch.dispatch(SimpleNamespace(cmd="prefab", sub="show", name="nope", names=[],
                                           summary=False,
                                           prefab_dir=str(tmp_path / "Prefabs"), container="c"))
    assert rc == 2
    assert "prefab not found: 'nope'" in capsys.readouterr().err


def test_prefab_show_corrupt_sidecar_is_clean_error(tmp_path, capsys):
    # A NEW-format prefab dir whose meta.json is corrupt → clean exit 2, never a JSONDecodeError.
    pref = tmp_path / "Prefabs"
    (pref / "bad" / "actors" / "A").mkdir(parents=True)
    (pref / "bad" / "actors" / "A" / "actor.t3d").write_text("Begin Actor Class=Engine.Light\nEnd Actor\n")
    (pref / "bad" / "actors" / "A" / "order_value").write_text("m\n")
    (pref / "bad" / "meta.json").write_text("{ not valid json")
    rc = dispatch.dispatch(SimpleNamespace(cmd="prefab", sub="show", name="bad", names=[],
                                           summary=False, prefab_dir=str(pref), container="c"))
    assert rc == 2
    assert "cannot read prefab 'bad'" in capsys.readouterr().err


def test_prefab_show_old_format_is_a_clean_hard_cutover_error(tmp_path, capsys):
    # HARD CUTOVER: an old single-blob prefab is NOT read; it fails with the actionable re-capture
    # message (exit 2, never a traceback), and still LISTS so the message surfaces on use.
    pref = tmp_path / "Prefabs"
    pref.mkdir()
    (pref / "old.t3d").write_text("Begin Map\nBegin Actor Class=Engine.Light Name=A\nEnd Actor\nEnd Map\n")
    (pref / "old.json").write_text('{"order": ["A"], "packages": []}')
    rc = dispatch.dispatch(SimpleNamespace(cmd="prefab", sub="show", name="old", names=[],
                                           summary=False, prefab_dir=str(pref), container="c"))
    assert rc == 2
    err = capsys.readouterr().err
    assert "old-format prefab 'old' — re-capture it" in err
    assert "Traceback" not in err


def test_stash_show_resolves_a_nested_id(tmp_path, monkeypatch, capsys):
    # Regression: the existence guard must NOT reject a real NESTED id (`a/b`). It reads via
    # read_stash (path-resolving), not list_stashes (top-level scan), so nesting works.
    proj, _ = _project_with_level(tmp_path, monkeypatch)
    reg = _register(proj)
    reg.write_stash("hangar/archway",
                    full_level={"Arch": "Begin Actor Class=Brush Name=Arch\nEnd Actor\n"},
                    order=["Arch"], packages=[], meta={"anchor": ["0", "0", "0"]})
    rc = dispatch.dispatch(_args(proj, sub="show", id="hangar/archway", names=[], summary=False))
    assert rc == 0                                    # found + shown, not a false "not found"
    assert "Arch" in capsys.readouterr().out


def test_stash_show_corrupt_meta_is_clean_not_a_traceback(tmp_path, monkeypatch, capsys):
    # The lifecycle reads guard read_stash so a corrupt meta.json is a clean exit 2, not a
    # JSONDecodeError traceback (parity with the --tree StashLevelSource guard + the prefab side).
    proj, _ = _project_with_level(tmp_path, monkeypatch)
    reg = _register(proj)
    reg.write_stash("bay", full_level={"A": "Begin Actor Class=Light Name=A\nEnd Actor\n"},
                    order=["A"], packages=[], meta={"anchor": ["0", "0", "0"]})
    (proj / ".uedcli" / "stash" / "bay" / "meta.json").write_text("{ not valid json")
    rc = dispatch.dispatch(_args(proj, sub="show", id="bay", names=[], summary=False))
    assert rc == 2
    assert "cannot read stash 'bay'" in capsys.readouterr().err
