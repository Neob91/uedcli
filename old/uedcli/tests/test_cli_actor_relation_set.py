import argparse
from decimal import Decimal

from uedcli import trunk
from uedcli.builders import cube, make_brush_actor
from uedcli.cli import dispatch
from uedcli.model import Level


def _brush(name, brush, loc=(0, 0, 0)):
    return make_brush_actor(name, brush, location=tuple(Decimal(str(c)) for c in loc))


def _lexo(i):
    return f"{i:04d}"


def _project(tmp_path, monkeypatch, actors, name="lvl"):
    proj = tmp_path / "repo"
    (proj / "maps" / name).mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    lvl = Level(actors={a.name: a for a in actors})
    trunk.write_level(proj / "maps" / name, lvl, {a.name: _lexo(i) for i, a in enumerate(actors)})
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    return proj


def _ns(proj, target, relative_to, **overrides):
    defaults = dict(
        cmd="actor", sub="relation", relationsub="set",
        project=str(proj), tree=None, target=target, relative_to=relative_to,
        gap=None, centroid_u=None, centroid_v=None,
        edge_u_min=None, edge_u_max=None, edge_v_min=None, edge_v_max=None,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _top_and_bottom(ref, tgt):
    top_ref = next(i for i, p in enumerate(ref.brush.polys) if p.normal == (0.0, 0.0, 1.0))
    bottom_tgt = next(i for i, p in enumerate(tgt.brush.polys) if p.normal == (0.0, 0.0, -1.0))
    return top_ref, bottom_tgt


def test_set_gap_moves_target_and_prints_name(tmp_path, monkeypatch, capsys):
    ref = _brush("Ref", cube(64, 64, 8), loc=(0, 0, 0))
    tgt = _brush("Tgt", cube(64, 64, 8), loc=(0, 0, 8))   # flush today
    proj = _project(tmp_path, monkeypatch, [ref, tgt])
    top_ref, bottom_tgt = _top_and_bottom(ref, tgt)
    rc = dispatch.dispatch(_ns(proj, [f"Tgt:{bottom_tgt}"], f"Ref:{top_ref}", gap=10.0))
    assert rc == 0
    out = capsys.readouterr().out
    assert out.strip() == "Tgt"
    lvl, _ = trunk.read_level(proj / "maps" / "lvl")
    assert lvl.actors["Tgt"].location[2] == Decimal(str(8 + 10))


def test_set_no_flags_exits_2(tmp_path, monkeypatch, capsys):
    ref = _brush("Ref", cube(16, 16, 16), loc=(0, 0, 0))
    tgt = _brush("Tgt", cube(16, 16, 16), loc=(0, 0, 16))
    proj = _project(tmp_path, monkeypatch, [ref, tgt])
    rc = dispatch.dispatch(_ns(proj, ["Tgt:0"], "Ref:0"))
    assert rc == 2
    assert "at least one" in capsys.readouterr().err


def test_set_non_planar_pair_exits_2(tmp_path, monkeypatch, capsys):
    ref = _brush("Ref", cube(64, 64, 8), loc=(0, 0, 0))
    tgt = _brush("Tgt", cube(64, 64, 8), loc=(0, 0, 8))
    proj = _project(tmp_path, monkeypatch, [ref, tgt])
    top_ref, _ = _top_and_bottom(ref, tgt)
    side_tgt = next(i for i, p in enumerate(tgt.brush.polys) if p.normal == (1.0, 0.0, 0.0))
    rc = dispatch.dispatch(_ns(proj, [f"Tgt:{side_tgt}"], f"Ref:{top_ref}", gap=0.0))
    assert rc == 2


def test_set_empty_stdin_dash_is_clean_noop(tmp_path, monkeypatch, capsys):
    ref = _brush("Ref", cube(16, 16, 16), loc=(0, 0, 0))
    tgt = _brush("Tgt", cube(16, 16, 16), loc=(0, 0, 16))
    proj = _project(tmp_path, monkeypatch, [ref, tgt])
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(""))
    rc = dispatch.dispatch(_ns(proj, ["-"], "Ref:0", gap=0.0))
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_set_ref_location_never_changes(tmp_path, monkeypatch, capsys):
    ref = _brush("Ref", cube(64, 64, 8), loc=(0, 0, 0))
    tgt = _brush("Tgt", cube(64, 64, 8), loc=(0, 0, 8))
    proj = _project(tmp_path, monkeypatch, [ref, tgt])
    top_ref, bottom_tgt = _top_and_bottom(ref, tgt)
    dispatch.dispatch(_ns(proj, [f"Tgt:{bottom_tgt}"], f"Ref:{top_ref}", gap=25.0))
    lvl, _ = trunk.read_level(proj / "maps" / "lvl")
    assert lvl.actors["Ref"].location == (Decimal(0), Decimal(0), Decimal(0))


def test_set_multi_target_moves_distinct_brushes(tmp_path, monkeypatch, capsys):
    ref = _brush("Ref", cube(64, 64, 8), loc=(0, 0, 0))
    tgt1 = _brush("Tgt1", cube(64, 64, 8), loc=(0, 0, 8))
    tgt2 = _brush("Tgt2", cube(64, 64, 8), loc=(100, 0, 8))
    proj = _project(tmp_path, monkeypatch, [ref, tgt1, tgt2])
    top_ref, bottom_tgt1 = _top_and_bottom(ref, tgt1)
    _, bottom_tgt2 = _top_and_bottom(ref, tgt2)
    rc = dispatch.dispatch(_ns(
        proj, [f"Tgt1:{bottom_tgt1}", f"Tgt2:{bottom_tgt2}"], f"Ref:{top_ref}", gap=10.0))
    assert rc == 0
    out = capsys.readouterr().out.split()
    assert out == ["Tgt1", "Tgt2"]
    lvl, _ = trunk.read_level(proj / "maps" / "lvl")
    assert lvl.actors["Tgt1"].location == (Decimal(0), Decimal(0), Decimal(18))
    assert lvl.actors["Tgt2"].location == (Decimal(100), Decimal(0), Decimal(18))


def test_set_one_bad_target_among_several_mutates_nothing(tmp_path, monkeypatch, capsys):
    ref = _brush("Ref", cube(64, 64, 8), loc=(0, 0, 0))
    tgt1 = _brush("Tgt1", cube(64, 64, 8), loc=(0, 0, 8))
    tgt2 = _brush("Tgt2", cube(64, 64, 8), loc=(100, 0, 8))
    tgt3 = _brush("Tgt3", cube(64, 64, 8), loc=(200, 0, 8))
    proj = _project(tmp_path, monkeypatch, [ref, tgt1, tgt2, tgt3])
    top_ref, bottom_tgt1 = _top_and_bottom(ref, tgt1)
    _, bottom_tgt2 = _top_and_bottom(ref, tgt2)
    side_tgt3 = next(i for i, p in enumerate(tgt3.brush.polys) if p.normal == (1.0, 0.0, 0.0))
    rc = dispatch.dispatch(_ns(
        proj,
        [f"Tgt1:{bottom_tgt1}", f"Tgt2:{bottom_tgt2}", f"Tgt3:{side_tgt3}"],
        f"Ref:{top_ref}", gap=10.0))
    assert rc == 2
    assert capsys.readouterr().out == ""
    lvl, _ = trunk.read_level(proj / "maps" / "lvl")
    assert lvl.actors["Ref"].location == (Decimal(0), Decimal(0), Decimal(0))
    assert lvl.actors["Tgt1"].location == (Decimal(0), Decimal(0), Decimal(8))
    assert lvl.actors["Tgt2"].location == (Decimal(100), Decimal(0), Decimal(8))
    assert lvl.actors["Tgt3"].location == (Decimal(200), Decimal(0), Decimal(8))


def test_set_duplicate_canonical_target_exits_2_nothing_saved(tmp_path, monkeypatch, capsys):
    ref = _brush("Ref", cube(64, 64, 8), loc=(0, 0, 0))
    tgt = _brush("Tgt", cube(64, 64, 8), loc=(0, 0, 8))
    proj = _project(tmp_path, monkeypatch, [ref, tgt])
    top_ref, bottom_tgt = _top_and_bottom(ref, tgt)
    top_tgt = next(i for i, p in enumerate(tgt.brush.polys) if p.normal == (0.0, 0.0, 1.0))
    rc = dispatch.dispatch(_ns(
        proj, [f"Tgt:{bottom_tgt}", f"Tgt:{top_tgt}"], f"Ref:{top_ref}", gap=10.0))
    assert rc == 2
    err = capsys.readouterr()
    assert err.out == ""
    assert "Tgt" in err.err
    lvl, _ = trunk.read_level(proj / "maps" / "lvl")
    assert lvl.actors["Tgt"].location == (Decimal(0), Decimal(0), Decimal(8))


def _light(name, loc):
    from uedcli.model import Actor
    return Actor(name=name, cls="Engine.Light",
                 location=tuple(Decimal(str(c)) for c in loc))


def _plus_y_face(actor) -> int:
    """The index of the brush's +Y face: the one all of whose vertices sit at the brush's own
    maximum local Y. `cube(200, 8, 200)` puts that at y = +4."""
    ymax = max(v[1] for p in actor.brush.polys for v in p.vertices)
    return next(i for i, p in enumerate(actor.brush.polys)
                if all(v[1] == ymax for v in p.vertices))


def test_set_moves_a_point_actor_to_an_exact_gap(tmp_path, monkeypatch, capsys):
    """Wall is a 200x8x200 box at the origin, so its +Y face sits at y=4 with normal +Y. --gap 8
    puts MyLight at y=12 exactly; X and Z are untouched because no U/V flag was given."""
    wall = make_brush_actor("Wall", cube(200, 8, 200),
                            location=tuple(Decimal(str(c)) for c in (0, 0, 0)))
    actors = [wall, _light("MyLight", (0, 40, 0))]
    proj = _project(tmp_path, monkeypatch, actors)
    ns = _ns(proj, ["MyLight"], f"Wall:{_plus_y_face(wall)}", gap=8.0)
    assert dispatch.dispatch(ns) == 0
    lvl, _ = trunk.read_level(proj / "maps" / "lvl")
    moved = lvl.actors["MyLight"]
    assert moved.location[1] == Decimal("12")
    assert moved.location[0] == Decimal("0") and moved.location[2] == Decimal("0")


def test_set_edge_and_centroid_flags_differ_against_a_point_target(tmp_path, monkeypatch):
    """--edge-u-min and --centroid-u are genuinely different offsets against a point target:
    `_edge_extent` computes pick(target) - pick(ref), and while the POINT's own min/max/centroid all
    collapse to one value, REF's do not."""
    wall = make_brush_actor("Wall", cube(200, 8, 200),
                            location=tuple(Decimal(str(c)) for c in (0, 0, 0)))
    ref = f"Wall:{_plus_y_face(wall)}"
    results = {}
    for flag in ("edge_u_min", "centroid_u"):
        actors = [wall, _light("MyLight", (0, 40, 0))]
        proj = _project(tmp_path, monkeypatch, actors, name=f"lvl_{flag}")
        ns = _ns(proj, ["MyLight"], ref)
        setattr(ns, flag, 8.0)
        assert dispatch.dispatch(ns) == 0
        lvl, _ = trunk.read_level(proj / "maps" / f"lvl_{flag}")
        results[flag] = lvl.actors["MyLight"].location
    assert results["edge_u_min"] != results["centroid_u"]


def test_set_rejects_an_idx_on_a_non_brush_target(tmp_path, monkeypatch, capsys):
    wall = make_brush_actor("Wall", cube(200, 8, 200),
                            location=tuple(Decimal(str(c)) for c in (0, 0, 0)))
    actors = [wall, _light("MyLight", (0, 40, 0))]
    proj = _project(tmp_path, monkeypatch, actors)
    ns = _ns(proj, ["MyLight:0"], f"Wall:{_plus_y_face(wall)}", gap=8.0)
    assert dispatch.dispatch(ns) == 2
    assert "MyLight" in capsys.readouterr().err


def test_set_mixed_brush_and_point_targets_all_or_nothing(tmp_path, monkeypatch, capsys):
    """A bad point target after a good brush target must abort before anything is mutated or
    printed -- the same atomicity `actor relation compare` needed a fix round to establish
    (fbe29cd1): compute/validate every target BEFORE mutating or printing any of them."""
    from uedcli.model import Actor
    wall = make_brush_actor("Wall", cube(200, 8, 200),
                            location=tuple(Decimal(str(c)) for c in (0, 0, 0)))
    tgt = make_brush_actor("Tgt", cube(200, 8, 200),
                           location=tuple(Decimal(str(c)) for c in (0, 40, 0)))
    no_loc = Actor(name="NoLoc", cls="Engine.Light")   # states no Location
    actors = [wall, tgt, no_loc]
    proj = _project(tmp_path, monkeypatch, actors)
    bottom_tgt = next(i for i, p in enumerate(tgt.brush.polys) if p.normal == (0.0, -1.0, 0.0))
    ns = _ns(proj, [f"Tgt:{bottom_tgt}", "NoLoc"], f"Wall:{_plus_y_face(wall)}", gap=8.0)
    assert dispatch.dispatch(ns) == 2
    out = capsys.readouterr()
    assert out.out == ""
    assert "NoLoc" in out.err
    lvl, _ = trunk.read_level(proj / "maps" / "lvl")
    assert lvl.actors["Tgt"].location == (Decimal(0), Decimal(40), Decimal(0))
