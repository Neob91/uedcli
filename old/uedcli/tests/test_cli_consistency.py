"""Regression tests for the CLI consistency & clarity audit fixes
(`dev/docs/reviews/2026-07-19-cli-consistency-audit.md`).

Mostly one section per finding (L3 is the exception — help-only, no test):
  H1 — `brush poly set` accepts `-`/stdin (the `poly find | poly set` pipe its help promises)
  M1 — mutator success-summaries go to STDERR (stdout stays pipe-clean)
  M2 — `--json` on `brush vertex list`, `actor prop get`, `mover key list`
  M3 — `--prop KEY=VALUE` on `brush build` (generator-surface parity with `actor build`)
  L2 — `brush clip` miss notice → stderr; `actor folder get --json` (null, not `(none)`)
  L3 — help-only clarifications (no test section): the `brush build --prop` override-semantics
       sentence, the `--rotate` precedence note, and the `actor prop get --json` string-values
       note. Their observable behaviour IS exercised, though — by the M2/M3 sections below
       (the piped-`--json` nested shape, the `--rotate`-wins-over-`--prop` precedence, the
       plain-brush `--prop`, and the `world_pos == base + off_pos` mover assertion).

Each drives the REAL argparse parser through `dispatch()` so the new flags/positionals parse
and route correctly. `_stub_author_validation` (conftest autouse) no-ops the class/texture ingest
gate so brush/generator verbs run offline.
"""
from __future__ import annotations

import io
import json
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest

from uedcli import trunk
from uedcli.cli import main as cli, dispatch, generators
from uedcli.cli.parsers._arguments import parse_coord
from uedcli.builders import cube, make_brush_actor
from uedcli.model import Actor, Level
from uedcli.uprops import Prop


# ── project harnesses ────────────────────────────────────────────────────────────────

def _write_project(tmp_path, monkeypatch, actors, *, name="lvl"):
    root = tmp_path / "proj"
    (root / "maps" / name).mkdir(parents=True)
    (root / "uedcli.toml").write_text('game = "deusex"\n')
    monkeypatch.setenv("UEDCLI_PROJECT", str(root))
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    lvl = Level(actors={a.name: a for a in actors}, order=[a.name for a in actors])
    ranks = dict(zip([a.name for a in actors], trunk.initial_ranks(len(actors))))
    trunk.write_level(root / "maps" / name, lvl, ranks)
    return root


def _point_project(tmp_path, monkeypatch, names):
    actors = [Actor(name=n, cls="Engine.Light", location=(Decimal(0), Decimal(0), Decimal(0)))
              for n in names]
    return _write_project(tmp_path, monkeypatch, actors)


def _run(argv, stdin=""):
    args = cli.build_parser().parse_args(argv)
    with mock.patch("sys.stdin", io.StringIO(stdin)):
        return dispatch.dispatch(args)


def _read(root, name="lvl"):
    lvl, _ranks = trunk.read_level(root / "maps" / name)
    return lvl


# ─────────────────────────────────────────────────────────────────────────────────────
# H1 — `brush poly set` accepts `-`/stdin
# ─────────────────────────────────────────────────────────────────────────────────────

def _brush_project(tmp_path, monkeypatch, name="WALL"):
    a = make_brush_actor(name, cube(64, 64, 64), location=(Decimal(0), Decimal(0), Decimal(0)))
    return _write_project(tmp_path, monkeypatch, [a])


def test_poly_set_reads_targets_from_stdin(tmp_path, monkeypatch):
    root = _brush_project(tmp_path, monkeypatch)
    # The `poly find | poly set -` loop: BRUSH:idx lines (what `poly find` prints) on stdin.
    rc = _run(["brush", "poly", "set", "-", "--texture", "DeusExDeco.Stone.Block"],
              stdin="WALL:0\nWALL:2\n")
    assert rc == 0
    polys = _read(root).actors["WALL"].brush.polys
    assert polys[0].texture == "DeusExDeco.Stone.Block"
    assert polys[2].texture == "DeusExDeco.Stone.Block"
    assert polys[1].texture != "DeusExDeco.Stone.Block"     # untouched


def test_poly_set_dash_is_mutually_exclusive_with_positional_targets(tmp_path, monkeypatch, capsys):
    _brush_project(tmp_path, monkeypatch)
    rc = _run(["brush", "poly", "set", "WALL:0", "-", "--texture", "DeusExDeco.Stone.Block"],
              stdin="WALL:1\n")
    assert rc == 2
    assert "stdin" in capsys.readouterr().err.lower()


def test_poly_set_empty_stdin_is_a_clean_noop(tmp_path, monkeypatch):
    root = _brush_project(tmp_path, monkeypatch)
    rc = _run(["brush", "poly", "set", "-", "--texture", "DeusExDeco.Stone.Block"], stdin="")
    assert rc == 0
    # nothing changed — every poly keeps the builder default texture
    assert all(p.texture != "DeusExDeco.Stone.Block"
               for p in _read(root).actors["WALL"].brush.polys)


# ─────────────────────────────────────────────────────────────────────────────────────
# M1 — mutator success-summaries go to STDERR
#
# The set-mutating verbs are PRODUCERS (2026-07-19 producer change): the touched actor
# NAMES go to STDOUT (one per line, feeding a downstream `| verb -`), the human summary
# to STDERR. So stdout is NOT empty — it is the touched names — and the summary must not
# leak onto it. (The full producer contract — exact names, stable order, round-trip — is
# the "producers" section below; these keep M1's summary-on-stderr guarantee alongside it.)
# ─────────────────────────────────────────────────────────────────────────────────────

def test_rotate_summary_goes_to_stderr_not_stdout(tmp_path, monkeypatch, capsys):
    _point_project(tmp_path, monkeypatch, ["A_1", "B_2"])
    assert _run(["actor", "rotate", "A_1", "--to", "0,90,0"]) == 0
    cap = capsys.readouterr()
    assert cap.out == "A_1\n"                   # stdout carries only the touched name(s)
    assert "rotated" in cap.err                 # summary stays on stderr


def test_scale_summary_goes_to_stderr_not_stdout(tmp_path, monkeypatch, capsys):
    a = make_brush_actor("WALL", cube(64, 64, 64), location=(Decimal(0), Decimal(0), Decimal(0)))
    _write_project(tmp_path, monkeypatch, [a])
    assert _run(["brush", "scale", "WALL", "--to", "2,2,2"]) == 0   # scale is a brush verb now
    cap = capsys.readouterr()
    assert cap.out == "WALL\n"
    assert "scaled" in cap.err


def test_order_summary_goes_to_stderr_not_stdout(tmp_path, monkeypatch, capsys):
    _point_project(tmp_path, monkeypatch, ["A_1", "B_2", "C_3"])
    assert _run(["actor", "order", "C_3", "--first"]) == 0
    cap = capsys.readouterr()
    assert cap.out == "C_3\n"
    assert "reordered" in cap.err


def test_apply_transform_summary_goes_to_stderr_not_stdout(tmp_path, monkeypatch, capsys):
    a = make_brush_actor("WALL", cube(64, 64, 64), location=(Decimal(0), Decimal(0), Decimal(0)))
    _write_project(tmp_path, monkeypatch, [a])
    assert _run(["brush", "apply-transform", "WALL"]) == 0
    cap = capsys.readouterr()
    assert cap.out == "WALL\n"
    assert "baked" in cap.err


def test_stash_apply_summary_goes_to_stderr_not_stdout(tmp_path, monkeypatch, capsys):
    from uedcli import stash_register
    from uedcli.normalize import canonical_actor_t3d
    root = _point_project(tmp_path, monkeypatch, ["Lamp"])
    reg = stash_register.FileStashRegister(root / ".uedcli" / "stash")
    cube_t3d = canonical_actor_t3d(
        make_brush_actor("Arch", cube(64, 64, 64), location=(0.0, 0.0, 0.0)))
    reg.write_stash("archway", full_level={"Arch": cube_t3d}, order=["Arch"],
                    packages=["DeusExDeco"], meta={"anchor": ["0", "0", "0"], "ts": 1})
    args = SimpleNamespace(cmd="stash", sub="apply", id="archway", project=str(root),
                           at=None, group=None, no_group=False, folder=None)
    assert dispatch.dispatch(args) == 0
    cap = capsys.readouterr()
    # the placed name (random suffix) is emitted to stdout; the "applied N actors" summary to stderr
    placed = cap.out.splitlines()
    assert len(placed) == 1 and placed[0].startswith("Arch")
    assert "applied" in cap.err


# ─────────────────────────────────────────────────────────────────────────────────────
# M2 — `--json` on query verbs
# ─────────────────────────────────────────────────────────────────────────────────────

def test_vertex_list_json_is_valid_and_structured(tmp_path, monkeypatch, capsys):
    a = make_brush_actor("WALL", cube(64, 64, 64), location=(Decimal(0), Decimal(0), Decimal(0)))
    _write_project(tmp_path, monkeypatch, [a])
    assert _run(["brush", "vertex", "list", "WALL", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["actor"] == "WALL"
    assert len(doc["vertices"]) == 8                       # a cube welds to 8 corners
    v = doc["vertices"][0]
    assert set(v["coord"]) == {"x", "y", "z"} and "polys" in v and "nrefs" in v


def test_mover_key_list_json_is_valid_and_structured(tmp_path, monkeypatch, capsys):
    mover = make_brush_actor("Lift", cube(64, 64, 96),
                             location=(Decimal(0), Decimal(0), Decimal("100")),
                             mover_class="Engine.Mover")
    mover.props += [("KeyPos(1)", "(Z=256.000000)"), ("NumKeys", "2")]
    _write_project(tmp_path, monkeypatch, [mover])
    assert _run(["mover", "key", "list", "Lift", "--json"]) == 0
    keys = json.loads(capsys.readouterr().out)
    assert [k["idx"] for k in keys] == [0, 1]
    assert keys[0]["base"] is True
    assert keys[1]["off_pos"] == [0, 0, 256]
    # world_pos is base (Location Z=100) + the key's offset — key 1 lands at 100 + 256 = 356.
    assert keys[0]["world_pos"] == [0, 0, 100]              # base key: zero offset
    assert keys[1]["world_pos"] == [0, 0, 356]              # 100 (base) + 256 (off) = 356


_PROP_SCHEMA = {
    "tag": Prop(name="Tag", kind="NameProperty", array_dim=1, property_flags=0, type_ref=0,
                type_name=None, owner="Engine.Actor"),
}


def _prop_get_json(tokens):
    """Run `actor prop get <tokens> --json` against a single in-memory Light, schema-mocked."""
    level = Level(actors={"Widget0": Actor(name="Widget0", cls="Engine.Light",
                                           location=(Decimal(1), Decimal(2), Decimal(3)),
                                           props=[("Tag", "lamp1")])},
                  order=["Widget0"])
    args = SimpleNamespace(cmd="actor", sub="prop", propsub="get", name="widget0",
                           tokens=list(tokens), kv=False, json=True)
    src = mock.Mock()
    src.load.return_value = level
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src), \
            mock.patch("uedcli.cli.resources.resolve_project",
                       side_effect=dispatch.ProjectError("no project")), \
            mock.patch("uedcli.cli.resources.class_schema",
                       lambda cls, project=None: dict(_PROP_SCHEMA)), \
            mock.patch("uedcli.cli.resources.class_defaults", lambda cls, project=None: {}), \
            mock.patch("uedcli.cli.resources.struct_members", lambda p, project=None: []), \
            mock.patch("uedcli.cli.resources.enum_names", lambda p, project=None: ()):
        rc = dispatch._dispatch(args)
    return rc


def test_prop_get_json_single_actor_is_a_flat_object(capsys):
    assert _prop_get_json(["Tag", "Location.X"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["Tag"] == "lamp1"
    assert doc["Location.X"] == "1"                         # value keeps its string form


def _prop_get_json_piped(names_stdin, tokens):
    """Run `actor prop get - --json` (piped `-`) over the newline names in `names_stdin`, against a
    two-actor in-memory level, schema-mocked — mirrors `_prop_get_json` but exercises the `-` path."""
    level = Level(actors={
        "Widget0": Actor(name="Widget0", cls="Engine.Light",
                         location=(Decimal(1), Decimal(2), Decimal(3)), props=[("Tag", "lamp1")]),
        "Widget1": Actor(name="Widget1", cls="Engine.Light",
                         location=(Decimal(4), Decimal(5), Decimal(6)), props=[("Tag", "lamp2")]),
    }, order=["Widget0", "Widget1"])
    args = SimpleNamespace(cmd="actor", sub="prop", propsub="get", name="-",
                           tokens=list(tokens), kv=False, json=True)
    src = mock.Mock()
    src.load.return_value = level
    with mock.patch("sys.stdin", io.StringIO(names_stdin)), \
            mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src), \
            mock.patch("uedcli.cli.resources.resolve_project",
                       side_effect=dispatch.ProjectError("no project")), \
            mock.patch("uedcli.cli.resources.class_schema",
                       lambda cls, project=None: dict(_PROP_SCHEMA)), \
            mock.patch("uedcli.cli.resources.class_defaults", lambda cls, project=None: {}), \
            mock.patch("uedcli.cli.resources.struct_members", lambda p, project=None: []), \
            mock.patch("uedcli.cli.resources.enum_names", lambda p, project=None: ()):
        return dispatch._dispatch(args)


def test_prop_get_json_piped_multi_actor_is_nested_by_name(capsys):
    # `-` over 2+ actors nests one {key: value} object per actor under its canonical Name.
    assert _prop_get_json_piped("widget0\nwidget1\n", ["Tag", "Location.X"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert set(doc) == {"Widget0", "Widget1"}              # keyed by canonical Name
    assert doc["Widget0"] == {"Tag": "lamp1", "Location.X": "1"}
    assert doc["Widget1"] == {"Tag": "lamp2", "Location.X": "4"}


# ─────────────────────────────────────────────────────────────────────────────────────
# M3 — `--prop` on `brush build`
# ─────────────────────────────────────────────────────────────────────────────────────

_BRUSH_PROP_SCHEMA = {
    "tag": Prop(name="Tag", kind="NameProperty", array_dim=1, property_flags=0, type_ref=0,
                type_name=None, owner="Engine.Actor"),
    "moverencroachtype": Prop(name="MoverEncroachType", kind="ByteProperty", array_dim=1,
                              property_flags=0, type_ref=0, type_name=None, owner="Engine.Mover"),
    "rotation": Prop(name="Rotation", kind="StructProperty", array_dim=1, property_flags=0,
                     type_ref=0, type_name="Rotator", owner="Engine.Actor"),
}


def test_brush_build_prop_bakes_props_onto_the_mover(capsys):
    from uedcli.model import parse_t3d
    argv = ["brush", "build", "cube", "--width", "64", "--breadth", "64", "--height", "96",
            "--mover-class", "Engine.Mover",
            "--prop", "MoverEncroachType=2", "--prop", "Tag=Lift1"]
    with mock.patch("uedcli.cli.resources.class_schema",
                    lambda cls, project=None: dict(_BRUSH_PROP_SCHEMA)):
        rc = _run(argv)
    assert rc == 0
    level = parse_t3d(capsys.readouterr().out)
    a = next(iter(level.actors.values()))
    props = dict(a.props)
    assert props.get("MoverEncroachType") == "2"
    assert props.get("Tag") == "Lift1"
    assert "CsgOper" not in props                           # a mover keeps its no-CSG shape


def test_brush_build_prop_on_plain_brush_carries_the_prop(capsys):
    # The non-mover path: a plain Engine.Brush (no --mover-class) also honours --prop.
    from uedcli.model import parse_t3d
    argv = ["brush", "build", "cube", "--width", "64", "--breadth", "64", "--height", "64",
            "--prop", "Tag=WallTag"]
    with mock.patch("uedcli.cli.resources.class_schema",
                    lambda cls, project=None: dict(_BRUSH_PROP_SCHEMA)):
        rc = _run(argv)
    assert rc == 0
    level = parse_t3d(capsys.readouterr().out)
    a = next(iter(level.actors.values()))
    assert a.cls == "Engine.Brush"                          # a plain brush, not a mover
    assert dict(a.props).get("Tag") == "WallTag"


def test_brush_build_rotate_wins_over_prop_rotation(capsys):
    # `--rotate` is applied AFTER --prop, so it OVERRIDES any --prop Rotation=… (help claim L3/§7).
    from uedcli.model import parse_t3d
    argv = ["brush", "build", "cube", "--width", "64", "--breadth", "64", "--height", "64",
            "--prop", "Rotation=(Pitch=1,Yaw=2,Roll=3)", "--rotate", "0,16384,0"]  # 16384 UU = 90°
    with mock.patch("uedcli.cli.resources.class_schema",
                    lambda cls, project=None: dict(_BRUSH_PROP_SCHEMA)):
        rc = _run(argv)
    assert rc == 0
    level = parse_t3d(capsys.readouterr().out)
    a = next(iter(level.actors.values()))
    rotations = [v for k, v in a.props if k == "Rotation"]
    assert len(rotations) == 1                              # exactly one Rotation — no duplicate
    # ...and it is the --rotate-derived value, NOT the --prop one that it overrode.
    uu = generators.rotation_prop_uu(parse_coord("0,16384,0"))
    assert rotations[0] == f"(Pitch={uu[0]},Yaw={uu[1]},Roll={uu[2]})"
    assert rotations[0] != "(Pitch=1,Yaw=2,Roll=3)"


def test_brush_build_bad_prop_errors_cleanly(capsys):
    rc = _run(["brush", "build", "cube", "--width", "64", "--breadth", "64", "--height", "64",
               "--prop", "NoEqualsHere"])
    assert rc == 2
    assert "NoEqualsHere" in capsys.readouterr().err


# ─────────────────────────────────────────────────────────────────────────────────────
# L2 — `brush clip` miss → stderr; `actor folder get --json`
# ─────────────────────────────────────────────────────────────────────────────────────

def test_brush_clip_miss_message_goes_to_stderr(tmp_path, monkeypatch, capsys):
    from uedcli.emit import emit_actor_t3d
    a = make_brush_actor("WALL", cube(64, 64, 64), location=(Decimal(0), Decimal(0), Decimal(0)))
    # `brush clip` is a stateless filter: a plane far above the cube misses its interior → the
    # brush passes through on stdout unchanged and the notice goes to stderr, not stdout.
    rc = _run(["brush", "clip", "-", "--axis", "z", "--offset", "100000", "--keep", "below"],
              stdin=emit_actor_t3d(a))
    assert rc == 0
    cap = capsys.readouterr()
    assert "WALL" in cap.out                                # the brush is emitted (passed through)
    assert "did not intersect brush WALL" in cap.err        # human notice → stderr only


def test_folder_get_json_maps_unfoldered_to_null(tmp_path, monkeypatch, capsys):
    a1 = Actor(name="A_1", cls="Engine.Light", location=(Decimal(0), Decimal(0), Decimal(0)),
               folder="castle.tower")
    a2 = Actor(name="B_2", cls="Engine.Light", location=(Decimal(0), Decimal(0), Decimal(0)))
    _write_project(tmp_path, monkeypatch, [a1, a2])
    assert _run(["actor", "folder", "get", "A_1", "B_2", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["A_1"] == "castle.tower"
    assert doc["B_2"] is None                               # unfoldered → JSON null, not "(none)"


# ─────────────────────────────────────────────────────────────────────────────────────
# producers — set-mutating verbs print their touched actor NAMES to STDOUT (2026-07-19)
#
# The stdout is exactly the resolved touched names, one per line, in a stable order — so it
# is a valid input to a downstream `| verb -` consumer (matching `brush poly align`). This
# closes the `actor find | actor rotate - | brush scale -` pipe.
# ─────────────────────────────────────────────────────────────────────────────────────

def test_rotate_prints_touched_names_to_stdout(tmp_path, monkeypatch, capsys):
    _point_project(tmp_path, monkeypatch, ["A_1", "B_2", "C_3"])
    # multiple targets → every touched name on stdout, one per line, in the resolved order
    assert _run(["actor", "rotate", "A_1", "B_2", "--to", "0,90,0"]) == 0
    assert capsys.readouterr().out == "A_1\nB_2\n"


def test_rotate_by_prints_touched_names_to_stdout(tmp_path, monkeypatch, capsys):
    # the relative (--by) path is a separate return branch — assert it produces names too
    _point_project(tmp_path, monkeypatch, ["A_1", "B_2"])
    assert _run(["actor", "rotate", "A_1", "B_2", "--by", "0,90,0"]) == 0
    assert capsys.readouterr().out == "A_1\nB_2\n"


def _brush_pair(tmp_path, monkeypatch):
    a1 = make_brush_actor("A_1", cube(64, 64, 64), location=(Decimal(0), Decimal(0), Decimal(0)))
    a2 = make_brush_actor("B_2", cube(64, 64, 64), location=(Decimal(128), Decimal(0), Decimal(0)))
    return _write_project(tmp_path, monkeypatch, [a1, a2])


def test_scale_by_prints_touched_names_to_stdout(tmp_path, monkeypatch, capsys):
    _brush_pair(tmp_path, monkeypatch)                      # scale is brush-only now → use brushes
    assert _run(["brush", "scale", "A_1", "B_2", "--by", "2,2,2"]) == 0
    assert capsys.readouterr().out == "A_1\nB_2\n"


def test_find_pipes_into_rotate_pipes_into_scale(tmp_path, monkeypatch, capsys):
    # end-to-end round-trip across namespaces: `actor find` → `actor rotate -` → `brush scale -`
    # (scale is a BRUSH verb since 2026-07-19). Each `-` consumer reads the prior producer's stdout.
    root = _brush_pair(tmp_path, monkeypatch)

    assert _run(["actor", "find"]) == 0
    found = capsys.readouterr().out
    assert found == "A_1\nB_2\n"

    assert _run(["actor", "rotate", "-", "--to", "0,90,0"], stdin=found) == 0
    rotated = capsys.readouterr().out
    assert rotated == found                                 # producer stdout == the names it touched

    assert _run(["brush", "scale", "-", "--to", "2,2,2"], stdin=rotated) == 0
    scaled = capsys.readouterr().out
    assert scaled == rotated                                # and it round-trips one more hop

    # the chain actually mutated both actors it named
    lvl = _read(root)
    for n in ("A_1", "B_2"):
        assert any(k == "Rotation" for k, _ in lvl.actors[n].props)


def test_delete_prints_removed_names_to_stdout(tmp_path, monkeypatch, capsys):
    # producer follow-up (2026-07-19): delete emits the removed names to stdout, count to stderr
    _point_project(tmp_path, monkeypatch, ["A_1", "B_2", "C_3"])
    assert _run(["actor", "delete", "A_1", "B_2"]) == 0
    cap = capsys.readouterr()
    assert cap.out == "A_1\nB_2\n" and "deleted 2 actor(s)" in cap.err


def test_move_prints_moved_name_to_stdout(tmp_path, monkeypatch, capsys):
    _point_project(tmp_path, monkeypatch, ["A_1"])
    assert _run(["actor", "move", "A_1", "--by", "0,0,64"]) == 0
    cap = capsys.readouterr()
    assert cap.out == "A_1\n" and "moved 1 actor(s)" in cap.err


def test_poly_set_prints_the_touched_faces_as_selectors_to_stdout(tmp_path, monkeypatch, capsys):
    # A PER-FACE verb prints per-face selectors, not the brush name: a bare `WALL` means ALL of that
    # brush's polys, so piping it into a second per-face verb would silently widen a two-face edit
    # to the whole brush. (It used to print `WALL`; owner ruling 2026-07-26 inverted that.)
    _brush_project(tmp_path, monkeypatch)
    assert _run(["brush", "poly", "set", "WALL:0", "WALL:2",
                 "--texture", "DeusExDeco.Stone.Block"]) == 0
    cap = capsys.readouterr()
    assert cap.out == "WALL:0\nWALL:2\n"
    assert "set 2 face(s) across 1 brush(es)" in cap.err


@pytest.mark.parametrize("argv,summary", [
    (["brush", "poly", "pan", "WALL:all", "--by", "0,32"], "panned 6 face(s) across 1 brush(es)"),
    (["brush", "poly", "rotate", "WALL:all", "--by", "16384"],
     "rotated 6 face(s) across 1 brush(es)"),
    (["brush", "poly", "scale", "WALL:all", "--by", "2,2"],
     "scaled 6 face(s) across 1 brush(es)"),
])
def test_per_face_verbs_print_expanded_selectors_to_stdout(tmp_path, monkeypatch, capsys,
                                                           argv, summary):
    # `all` must EXPAND on stdout — an implementation that echoed the caller's own token back would
    # print `WALL:all` and pass a laxer assertion.
    _brush_project(tmp_path, monkeypatch)
    assert _run(argv) == 0
    cap = capsys.readouterr()
    assert cap.out == "".join(f"WALL:{i}\n" for i in range(6))
    assert summary in cap.err


def test_per_face_verb_stdout_canonicalizes_a_case_folded_input(tmp_path, monkeypatch, capsys):
    # The other half an echo-the-input implementation gets wrong: brush names resolve
    # case-insensitively, so the printed selector must carry the CANONICAL name.
    _brush_project(tmp_path, monkeypatch)
    assert _run(["brush", "poly", "pan", "wall:3", "--to", "0,0"]) == 0
    assert capsys.readouterr().out == "WALL:3\n"


def test_per_face_verb_stdout_round_trips_through_the_dash_convention(tmp_path, monkeypatch,
                                                                      capsys):
    # The contract that makes the verbs compose: one verb's stdout is re-consumable as another's
    # stdin target set.
    _brush_project(tmp_path, monkeypatch)
    assert _run(["brush", "poly", "pan", "WALL:all", "--by", "1,0"]) == 0
    produced = capsys.readouterr().out
    assert _run(["brush", "poly", "pan", "-", "--by", "1,0"], stdin=produced) == 0
    assert capsys.readouterr().out == produced
