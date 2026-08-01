"""Content verbs through `dispatch()` on the git-native TRUNK path (a project + selected level →
`src` is a `TrunkLevelSource`): these prove the verbs edit the on-disk trunk."""
import argparse

from uedcli import trunk
from uedcli.cli import dispatch
from uedcli.model import Actor, Brush, Level, Polygon


def _project_with_level(tmp_path, monkeypatch, name="lvl"):
    proj = tmp_path / "repo"
    (proj / "maps" / name).mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    lvl = Level(actors={"A_1": Actor(name="A_1", cls="Light", location=(1, 2, 3)),
                        "B_2": Actor(name="B_2", cls="Light", location=(4, 5, 6))})
    trunk.write_level(proj / "maps" / name, lvl, {"A_1": "m", "B_2": "t"})
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    return proj, name


def _ns(**kw):
    return argparse.Namespace(**kw)


def test_actor_find_reads_the_trunk(tmp_path, capsys, monkeypatch):
    proj, _ = _project_with_level(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_ns(cmd="actor", sub="find", project=str(proj),
                               name=[], cls=[], group=[], prop=[], kind=None))
    assert rc == 0
    out = capsys.readouterr().out
    assert "A_1" in out and "B_2" in out


def test_actor_find_json_emits_a_name_array(tmp_path, capsys, monkeypatch):
    import json
    proj, _ = _project_with_level(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_ns(cmd="actor", sub="find", project=str(proj),
                               name=[], cls=[], group=[], prop=[], kind=None, json=True))
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == ["A_1", "B_2"]   # structured, not one-per-line


def test_actor_find_default_still_one_per_line(tmp_path, capsys, monkeypatch):
    # --json must not change the default (non-json) output.
    proj, _ = _project_with_level(tmp_path, monkeypatch)
    dispatch.dispatch(_ns(cmd="actor", sub="find", project=str(proj),
                          name=[], cls=[], group=[], prop=[], kind=None, json=False))
    assert capsys.readouterr().out.splitlines() == ["A_1", "B_2"]


def _project_with_cube(tmp_path, monkeypatch, name="lvl"):
    proj = tmp_path / "repo"
    (proj / "maps" / name).mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    a = Actor(name="Box_1", cls="Engine.Brush", location=(0, 0, 0),
              brush=Brush(model_name="Model_Box_1", polys=_cube_polys(texture="Foo.Bar")))
    lvl = Level(actors={"Box_1": a})
    trunk.write_level(proj / "maps" / name, lvl, {"Box_1": "m"})
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    return proj


def test_poly_list_json(tmp_path, capsys, monkeypatch):
    import json
    proj = _project_with_cube(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_ns(cmd="brush", sub="poly", polysub="list", project=str(proj),
                               name="Box_1", tree=None, json=True))
    assert rc == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["actor"] == "Box_1"
    assert len(doc["polys"]) == 6
    assert set(doc["polys"][0]) >= {"idx", "facing", "texture", "flags", "pan", "centroid",
                                    "area", "nverts"}


def test_poly_list_default_text_unchanged(tmp_path, capsys, monkeypatch):
    proj = _project_with_cube(tmp_path, monkeypatch)
    dispatch.dispatch(_ns(cmd="brush", sub="poly", polysub="list", project=str(proj),
                          name="Box_1", tree=None, json=False))
    out = capsys.readouterr().out
    assert out.startswith("Box_1: 6 polys")     # the aligned text table, unchanged


def test_actor_delete_mutates_the_trunk(tmp_path, monkeypatch):
    proj, name = _project_with_level(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_ns(cmd="actor", sub="delete", project=str(proj), names=["B_2"]))
    assert rc == 0
    assert not (proj / "maps" / name / "actors" / "B_2").exists()      # removed from the on-disk trunk
    got, _ = trunk.read_level(proj / "maps" / name)
    assert set(got.actors) == {"A_1"}


def test_actor_move_persists_to_the_trunk(tmp_path, monkeypatch):
    proj, name = _project_with_level(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_ns(cmd="actor", sub="move", project=str(proj),
                               name="A_1", to=[10, 20, 30], by=None))
    assert rc == 0
    got, _ = trunk.read_level(proj / "maps" / name)
    assert got.actors["A_1"].location == (10, 20, 30)                  # the move landed in the trunk


def test_brush_replace_swaps_geometry_but_keeps_the_on_disk_rank(tmp_path, monkeypatch):
    # board Geometry #9: an in-place shape swap must keep the target's order_value (CSG rank) on the
    # trunk — the identity the mocked-seam dispatch tests can't see (only the real same-Name save
    # preserves it). Build a project with a brush at a known rank, replace its shape, read back.
    from uedcli.builders import cube, make_brush_actor
    from uedcli.emit import emit_actor_t3d
    proj = tmp_path / "repo"
    name = "lvl"
    (proj / "maps" / name).mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    wall = make_brush_actor("WALL", cube(64, 64, 64), csg="subtract", group="rooms")
    trunk.write_level(proj / "maps" / name, Level(actors={"WALL": wall}), {"WALL": "hhhhhh"})
    monkeypatch.setenv("UEDCLI_LEVEL", name)

    t3d = emit_actor_t3d(make_brush_actor("NewShape", cube(200, 200, 200), csg="add"))
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(t3d))
    rc = dispatch.dispatch(_ns(cmd="brush", sub="replace", name="WALL", shape="-",
                               project=str(proj)))
    assert rc == 0
    got, ranks = trunk.read_level(proj / "maps" / name)
    assert ranks["WALL"] == "hhhhhh"                              # rank UNCHANGED by the swap
    verts = {v for p in got.actors["WALL"].brush.polys for v in p.vertices}
    assert (100, 100, 100) in verts and (32, 32, 32) not in verts  # geometry swapped in
    assert [v for k, v in got.actors["WALL"].props if k == "CsgOper"] == ["CSG_Subtract"]  # id kept


def test_actor_add_mints_a_random_name_and_a_distinct_rank(tmp_path, monkeypatch):
    # actor add is the only content verb that mints a NEW order_value + name; on the trunk it must use
    # the coordination-free random-suffix identity (decisions 2026-07-05 15:11), not sequential naming.
    proj, name = _project_with_level(tmp_path, monkeypatch)
    t3d = "Begin Actor Class=Light Name=NewLight\n    LightBrightness=200\nEnd Actor\n"
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(t3d))
    rc = dispatch.dispatch(_ns(cmd="actor", sub="add", project=str(proj), file="-"))
    assert rc == 0
    got, ranks = trunk.read_level(proj / "maps" / name)
    added = [n for n in got.actors if n not in ("A_1", "B_2")]
    assert len(added) == 1
    stem, sep, suffix = added[0].rpartition("_")
    assert stem == "NewLight" and len(suffix) == 6      # random-suffix name, not a sequential "NewLight0"
    assert trunk.duplicate_ranks(ranks) == []           # its minted order_value is distinct
    assert ranks[added[0]] > ranks["B_2"]               # appended after the existing actors


def _cube_polys(texture=None):
    # A minimal solid box (6 quad faces) so `level status`/`referenced_packages` see brush polys.
    faces = [
        [(0, 0, 0), (0, 128, 0), (0, 128, 128), (0, 0, 128)],
        [(128, 0, 0), (128, 0, 128), (128, 128, 128), (128, 128, 0)],
        [(0, 0, 0), (0, 0, 128), (128, 0, 128), (128, 0, 0)],
        [(0, 128, 0), (128, 128, 0), (128, 128, 128), (0, 128, 128)],
        [(0, 0, 0), (128, 0, 0), (128, 128, 0), (0, 128, 0)],
        [(0, 0, 128), (0, 128, 128), (128, 128, 128), (128, 0, 128)],
    ]
    return [Polygon(vertices=[(x, y, z) for x, y, z in f], texture=texture) for f in faces]


def _status_args(**kw):
    return argparse.Namespace(cmd="level", sub="status", **kw)


def test_it_shows_duplicate_order_in_doctor_but_keeps_exit_zero(tmp_path, capsys, monkeypatch):
    # Two actors on the SAME order_value → `level doctor` surfaces a dup-order WARN, exit stays 0.
    proj = tmp_path / "repo"
    (proj / "maps" / "lvl").mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    lvl = Level(actors={"A_1": Actor(name="A_1", cls="Light", location=(1, 2, 3)),
                        "B_2": Actor(name="B_2", cls="Light", location=(4, 5, 6))})
    trunk.write_level(proj / "maps" / "lvl", lvl, {"A_1": "hzzzzz", "B_2": "hzzzzz"})
    monkeypatch.setenv("UEDCLI_LEVEL", "lvl")

    rc = dispatch.dispatch(argparse.Namespace(
        cmd="level", sub="doctor", project=str(proj),
        json=False, severity=None, category=None))

    out = capsys.readouterr().out
    assert rc == 0                                      # a WARN never flips the exit code
    assert "csg_order" in out
    assert "actors A_1, B_2 share order_value 'hzzzzz'" in out   # both names in the one finding


def test_it_lists_referenced_packages_in_level_status(tmp_path, capsys, monkeypatch):
    proj = tmp_path / "repo"
    (proj / "maps" / "lvl").mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    box = Actor(name="Box_1", cls="Brush", brush=Brush(
        model_name="Model_Box", polys=_cube_polys(texture="Artifudge.SomeTex")))
    trunk.write_level(proj / "maps" / "lvl", Level(actors={"Box_1": box}), {"Box_1": "m"})
    monkeypatch.setenv("UEDCLI_LEVEL", "lvl")

    rc = dispatch.dispatch(_status_args(project=str(proj)))

    out = capsys.readouterr().out
    assert rc == 0
    assert "texture packages: Artifudge" in out


def test_it_reports_no_referenced_packages_when_texture_less(tmp_path, capsys, monkeypatch):
    proj = tmp_path / "repo"
    (proj / "maps" / "lvl").mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    lvl = Level(actors={"A_1": Actor(name="A_1", cls="Light", location=(1, 2, 3))})
    trunk.write_level(proj / "maps" / "lvl", lvl, {"A_1": "m"})
    monkeypatch.setenv("UEDCLI_LEVEL", "lvl")

    rc = dispatch.dispatch(_status_args(project=str(proj)))

    out = capsys.readouterr().out
    assert rc == 0
    assert "texture packages: (none referenced)" in out
