"""`actor bbox <names…|->` — world AABB (min/max/size/center) enclosing the passed actors as ONE
box (the multi-actor case IS the union; there is no --union flag). Reuses writes.union_bounds, so
rotation/scale/location are honoured. Feature 5 (build group #2, 2026-07-18)."""
import argparse
import io
import json

import pytest

from uedcli import dispatch, trunk
from uedcli.builders import cube, make_brush_actor
from uedcli.model import Actor, Level


def _lexo(i: int) -> str:
    return chr(ord("m") + i)


def _project(tmp_path, monkeypatch, actors, name="lvl"):
    proj = tmp_path / "repo"
    (proj / "maps" / name).mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    lvl = Level(actors={a.name: a for a in actors})
    trunk.write_level(proj / "maps" / name, lvl,
                      {a.name: _lexo(i) for i, a in enumerate(actors)})
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    return proj


def _ns(proj, names, **kw):
    base = dict(cmd="actor", sub="bbox", project=str(proj), tree=None,
                names=names, field=None, json=False)
    base.update(kw)
    return argparse.Namespace(**base)


def _points(*locs):
    return [Actor(name=f"P{i}", cls="Light", location=loc) for i, loc in enumerate(locs)]


# ── default text output ──────────────────────────────────────────────────────────────────────

def test_bbox_union_of_two_points(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, _points((0, 0, 0), (100, 200, 300)))
    rc = dispatch.dispatch(_ns(proj, ["P0", "P1"]))
    assert rc == 0
    cap = capsys.readouterr()
    lines = cap.out.splitlines()
    assert lines[0] == "min    0,0,0"
    assert lines[1] == "max    100,200,300"
    assert lines[2] == "size   100,200,300"
    assert lines[3] == "center 50,100,150"
    assert "bbox of 2 actor(s)" in cap.err     # human summary goes to STDERR, not the pipe


def test_bbox_single_actor_is_its_own_box(tmp_path, monkeypatch, capsys):
    # A point actor is a zero-size box at its Location.
    proj = _project(tmp_path, monkeypatch, _points((10, 20, 30)))
    rc = dispatch.dispatch(_ns(proj, ["P0"]))
    assert rc == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "min    10,20,30"
    assert lines[1] == "max    10,20,30"
    assert lines[2] == "size   0,0,0"
    assert lines[3] == "center 10,20,30"


def test_bbox_non_integer_center_prints_decimal(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, _points((0, 0, 0), (5, 0, 0)))
    rc = dispatch.dispatch(_ns(proj, ["P0", "P1"]))
    assert rc == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[3] == "center 2.5,0,0"       # odd extent → fractional centre, exact (no float tail)


# ── --field bare extractor ───────────────────────────────────────────────────────────────────

def test_bbox_field_center_prints_one_bare_vector(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, _points((0, 0, 0), (100, 200, 300)))
    rc = dispatch.dispatch(_ns(proj, ["P0", "P1"], field="center"))
    assert rc == 0
    out = capsys.readouterr().out
    assert out.strip() == "50,100,150"         # ONLY the requested vector, one bare x,y,z line


def test_bbox_field_size(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, _points((0, 0, 0), (100, 200, 300)))
    dispatch.dispatch(_ns(proj, ["P0", "P1"], field="size"))
    assert capsys.readouterr().out.strip() == "100,200,300"


# ── --json ───────────────────────────────────────────────────────────────────────────────────

def test_bbox_json(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, _points((0, 0, 0), (100, 200, 300)))
    rc = dispatch.dispatch(_ns(proj, ["P0", "P1"], json=True))
    assert rc == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["min"] == {"x": 0, "y": 0, "z": 0}
    assert doc["max"] == {"x": 100, "y": 200, "z": 300}
    assert doc["size"] == {"x": 100, "y": 200, "z": 300}
    assert doc["center"] == {"x": 50, "y": 100, "z": 150}


# ── rotation/scale honoured (reuses union_bounds → the full actor transform) ───────────────────

def test_bbox_honours_rotation(tmp_path, monkeypatch, capsys):
    # A 128×64×32 box centred at origin; yaw 90° swaps the X/Y extents.
    a = make_brush_actor("Box", cube(128, 64, 32), location=(0.0, 0.0, 0.0))
    a.props.insert(0, ("Rotation", "(Pitch=0,Yaw=16384,Roll=0)"))   # 16384 UU = 90°
    proj = _project(tmp_path, monkeypatch, [a])
    rc = dispatch.dispatch(_ns(proj, ["Box"], json=True))
    assert rc == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["size"]["x"] == pytest.approx(64, abs=0.05)     # was 128, now the breadth
    assert doc["size"]["y"] == pytest.approx(128, abs=0.05)    # was 64, now the width
    assert doc["size"]["z"] == pytest.approx(32, abs=0.05)     # unchanged by a yaw


def test_bbox_snaps_gmath_rotator_noise_to_the_grid(tmp_path, monkeypatch, capsys):
    """UE1's GMath table gives sin(180°) = -8.742278e-08, not 0, so a ±64 vertex offset leaks ~6e-06
    into the cross axis: a box sitting exactly on Y=228 used to report `min 992,225.999994,48`. The
    trunk is exact (whole-number Location and vertices) and the noise is ~170x below doctor.WELD, so
    the REPORTED box snaps it through emit.clean rather than printing off-grid-looking numbers for
    on-grid geometry."""
    a = make_brush_actor("Sheet", cube(128, 4, 128), location=(1056.0, 228.0, 112.0))
    a.props.insert(0, ("Rotation", "(Pitch=0,Yaw=32768,Roll=0)"))   # 32768 UU = 180°
    proj = _project(tmp_path, monkeypatch, [a])
    rc = dispatch.dispatch(_ns(proj, ["Sheet"]))
    assert rc == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "min    992,226,48"
    assert lines[1] == "max    1120,230,176"
    assert lines[2] == "size   128,4,128"
    assert lines[3] == "center 1056,228,112"


def test_bbox_snap_preserves_a_genuine_fraction(tmp_path, monkeypatch, capsys):
    """`clean` snaps only INSIDE the tolerance band, so a real half-unit extent still prints — the
    snap must not degrade into a blanket round(), which would erase authored fractional geometry."""
    a = make_brush_actor("Odd", cube(5, 5, 5), location=(0.0, 0.0, 0.0))
    proj = _project(tmp_path, monkeypatch, [a])
    rc = dispatch.dispatch(_ns(proj, ["Odd"]))
    assert rc == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "min    -2.5,-2.5,-2.5"
    assert lines[1] == "max    2.5,2.5,2.5"
    assert lines[2] == "size   5,5,5"


# ── stdin `-` name list ──────────────────────────────────────────────────────────────────────

def test_bbox_reads_names_from_stdin(tmp_path, capsys, monkeypatch):
    proj = _project(tmp_path, monkeypatch, _points((0, 0, 0), (100, 200, 300)))
    monkeypatch.setattr("sys.stdin", io.StringIO("P0\nP1\n"))
    rc = dispatch.dispatch(_ns(proj, ["-"], field="max"))
    assert rc == 0
    assert capsys.readouterr().out.strip() == "100,200,300"


def test_bbox_empty_stdin_is_clean_noop(tmp_path, capsys, monkeypatch):
    proj = _project(tmp_path, monkeypatch, _points((0, 0, 0)))
    monkeypatch.setattr("sys.stdin", io.StringIO(""))    # a filter that matched nothing
    rc = dispatch.dispatch(_ns(proj, ["-"]))
    assert rc == 0
    assert capsys.readouterr().out == ""                 # no box, no error


# ── error paths (no traceback ever reaches the user) ─────────────────────────────────────────

def test_bbox_unknown_name_exits_2(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, _points((0, 0, 0)))
    rc = dispatch.dispatch(_ns(proj, ["Nope"]))
    assert rc == 2
    assert "not found" in capsys.readouterr().err        # names the offending value, no traceback


def test_bbox_dash_mixed_with_names_exits_2(tmp_path, capsys, monkeypatch):
    proj = _project(tmp_path, monkeypatch, _points((0, 0, 0)))
    monkeypatch.setattr("sys.stdin", io.StringIO("P0\n"))
    rc = dispatch.dispatch(_ns(proj, ["-", "P0"]))        # `-` is the SOLE source, not mixable
    assert rc == 2
    assert "stdin" in capsys.readouterr().err


# ── the report must agree with the predicates that consume it ───────────────────────────────────

def test_a_rotated_actor_is_within_its_own_reported_bbox(tmp_path, monkeypatch, capsys):
    """Build-review finding #1, 2026-07-26: `actor bbox` reports tolerance-snapped bounds while
    `--within-bbox` compared RAW ones, so piping `bbox --field min/max` into `find --within-bbox`
    returned an empty set at exit 0 — the actor was not contained in its own reported box. The
    containment predicate now compares within the same CLEAN_EPS band."""
    from uedcli import writes
    a = make_brush_actor("Sheet", cube(128, 4, 128), location=(1056.0, 228.0, 112.0))
    a.props.insert(0, ("Rotation", "(Pitch=0,Yaw=32768,Roll=0)"))     # 180°, the noisy case
    proj = _project(tmp_path, monkeypatch, [a])
    rc = dispatch.dispatch(_ns(proj, ["Sheet"], json=True))
    assert rc == 0
    doc = json.loads(capsys.readouterr().out)
    reported = (tuple(doc["min"][k] for k in "xyz"), tuple(doc["max"][k] for k in "xyz"))
    assert writes.aabb_within(writes.actor_bounds(a), reported)


def test_vertex_list_and_bbox_report_the_same_corner(tmp_path, monkeypatch, capsys):
    """Build-review finding #2: `query._coord_component` was a second, UNSNAPPED formatter, so the
    two verbs printed different numbers for the same world corner."""
    from uedcli import query
    a = make_brush_actor("Sheet", cube(128, 4, 128), location=(1056.0, 228.0, 112.0))
    a.props.insert(0, ("Rotation", "(Pitch=0,Yaw=32768,Roll=0)"))
    proj = _project(tmp_path, monkeypatch, [a])
    rc = dispatch.dispatch(_ns(proj, ["Sheet"]))
    assert rc == 0
    hi = capsys.readouterr().out.splitlines()[1].split()[1]           # the "max" row
    coords = {c for row in query.list_vertices(a)
              for c in [",".join(query._coord_component(v) for v in row["coord"])]}
    assert hi in coords, f"bbox max {hi} is not among the reported vertices {sorted(coords)}"
