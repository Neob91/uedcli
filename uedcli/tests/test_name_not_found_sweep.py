"""House rule (CLAUDE.md): no bare Python exception may reach the CLI user — a nonexistent
actor/entity name must produce a clean, named `Actor not found: <name>` (or an equivalently
named error) on stderr and exit 2, NEVER a `KeyError`/`IndexError`/`StopIteration` traceback.

This is the cross-verb regression sweep that LOCKS that in. It drives the real `dispatch` for
EVERY name-resolving verb, on BOTH name-source paths:
  * the positional path — a bad name given as a CLI argument;
  * the stdin path — a bad name arriving via the `-` (names-from-stdin) convention;
plus the secondary-name refs (`--pivot-actor`, `--before/--after`) and the `BRUSH:SELECTOR`
poly-target grammar.

Faithful by construction: args are parsed through the actual `build_parser()` grammar (not a
hand-built `Namespace`), and only the trunk seam (`_resolve_level_source`) + `sys.stdin` are
mocked, so a verb whose bad-name lookup regresses to a bare exception fails HERE (the exception
escapes `dispatch` and pytest reports it) instead of reaching a real user.

Board item "KeyError on a nonexistent actor name — audit + regression tests" (to-build).
Per-verb message specifics live in the focused suites (test_actor_name_resolution, _compose,
_bbox, _polyalign, _surface, _query); this file is the exhaustive breadth net.
"""
from __future__ import annotations

import io
from decimal import Decimal
from unittest import mock

import pytest

from uedcli.cli import dispatch as dispatch_mod
from uedcli.cli import level_sources
from uedcli.builders import cube, make_brush_actor
from uedcli.cli.main import build_parser
from uedcli.model import Level, parse_t3d_actors

BAD = "NoSuchActor"

# A minimal but representative level: a plain brush, a Mover (for the `mover key` family), and a
# point (non-brush) light. Every case below references only `BAD`/a secondary bad name, so the
# resolver always misses — but the real actors let the pre-resolve grammar (e.g. a valid
# `--pivot-actor` anchor, a valid `--after` moved set) reach the lookup under test.
def _level() -> Level:
    lv = Level()
    lv.actors["B1"] = make_brush_actor(
        "B1", cube(64, 64, 64), location=(Decimal(0), Decimal(0), Decimal(0)))
    lv.actors["Door1"] = make_brush_actor(
        "Door1", cube(64, 64, 64), location=(Decimal(0), Decimal(0), Decimal(0)),
        mover_class="Engine.Mover")
    lv.actors["Light1"] = parse_t3d_actors(
        'Begin Actor Class=Engine.Light Name=Light1\n    Name="Light1"\nEnd Actor\n')[0]
    lv.order = ["B1", "Door1", "Light1"]
    return lv


def _fake_src():
    src = mock.Mock()
    src.load.return_value = _level()
    # `actor order`/`add` read the load-snapshot ranks off the source; supply them so those paths
    # reach the name lookup rather than tripping on a missing attribute.
    src._ranks = {"B1": "0|hzzzzz:", "Door1": "0|i00000:", "Light1": "0|i00001:"}
    return src


# A valid one-brush T3D snippet — `brush replace NAME -` parses stdin BEFORE resolving NAME, so the
# bad-name path is only reached when stdin carries real geometry.
_REPLACE_T3D = (
    "Begin Actor Class=Brush Name=New\n    CsgOper=CSG_Add\n"
    "    Begin Brush Name=M\n        Begin PolyList\n            Begin Polygon\n"
    "                Vertex -64,-64,-64\n                Vertex -64,+64,-64\n"
    "                Vertex -64,+64,+64\n            End Polygon\n"
    "        End PolyList\n    End Brush\n    Name=\"New\"\nEnd Actor\n"
)

# id, argv (bad name inline), optional stdin.
_POSITIONAL = [
    ("actor-show", ["actor", "show", BAD], ""),
    ("actor-move", ["actor", "move", BAD, "--to", "0,0,0"], ""),
    ("actor-bbox", ["actor", "bbox", BAD], ""),
    ("actor-delete", ["actor", "delete", BAD], ""),
    ("actor-order", ["actor", "order", BAD, "--first"], ""),
    ("actor-order-after-ref", ["actor", "order", "B1", "--after", BAD], ""),
    ("actor-order-before-ref", ["actor", "order", "B1", "--before", BAD], ""),
    ("actor-rotate", ["actor", "rotate", BAD, "--by", "0,0,90"], ""),
    ("actor-rotate-pivot-actor", ["actor", "rotate", "B1", "--by", "0,0,90",
                                  "--pivot-actor", BAD], ""),
    ("actor-scale", ["brush", "scale", BAD, "--by", "2,2,2"], ""),
    ("actor-scale-pivot-actor", ["brush", "scale", "B1", "--by", "2,2,2",
                                 "--pivot-actor", BAD], ""),
    ("actor-apply-transform", ["brush", "apply-transform", BAD], ""),
    ("actor-prop-get", ["actor", "prop", "get", BAD, "Tag"], ""),
    ("actor-prop-set", ["actor", "prop", "set", BAD, "Tag=x"], ""),
    ("actor-prop-unset", ["actor", "prop", "unset", BAD, "Tag"], ""),
    ("actor-folder-set", ["actor", "folder", "set", BAD, "--to", "a.b"], ""),
    ("actor-folder-get", ["actor", "folder", "get", BAD], ""),
    ("actor-folder-unset", ["actor", "folder", "unset", BAD], ""),
    # `brush clip` is a stateless T3D filter (no by-name resolution) — not in this sweep.
    ("brush-replace", ["brush", "replace", BAD, "-"], _REPLACE_T3D),
    ("brush-vertex-list", ["brush", "vertex", "list", BAD], ""),
    ("brush-vertex-move", ["brush", "vertex", "move", BAD, "--at", "0,0,0", "--by", "0,0,1"], ""),
    ("brush-poly-list", ["brush", "poly", "list", BAD], ""),
    ("brush-poly-find", ["brush", "poly", "find", BAD], ""),
    ("brush-poly-set", ["brush", "poly", "set", f"{BAD}:all", "--add-flag", "Unlit"], ""),
    ("brush-poly-pan", ["brush", "poly", "pan", f"{BAD}:all", "--by", "0,32"], ""),
    ("brush-poly-rotate", ["brush", "poly", "rotate", f"{BAD}:all", "--by", "16384"], ""),
    ("brush-poly-scale", ["brush", "poly", "scale", f"{BAD}:all", "--by", "2,2"], ""),
    ("brush-poly-align", ["brush", "poly", "align", "--wall", f"{BAD}:0"], ""),
    ("mover-key-list", ["mover", "key", "list", BAD], ""),
    ("mover-key-count", ["mover", "key", "count", BAD, "4"], ""),
    ("mover-key-move", ["mover", "key", "move", BAD, "1", "--by", "0,0,1"], ""),
    ("mover-key-rotate", ["mover", "key", "rotate", BAD, "1", "--by", "0,0,90"], ""),
    ("mover-key-remove", ["mover", "key", "remove", BAD, "1"], ""),
]

# The `-` (names-from-stdin) path: the same verbs whose name/target arg accepts `-`. stdin carries
# the bad name (or `BAD:all`/`BAD:0` for the poly-target verbs).
_STDIN = [
    ("actor-show-stdin", ["actor", "show", "-"], f"{BAD}\n"),
    ("actor-bbox-stdin", ["actor", "bbox", "-"], f"{BAD}\n"),
    ("actor-delete-stdin", ["actor", "delete", "-"], f"{BAD}\n"),
    ("actor-order-stdin", ["actor", "order", "-", "--first"], f"{BAD}\n"),
    ("actor-move-stdin", ["actor", "move", "-", "--by", "0,0,10"], f"{BAD}\n"),
    ("actor-rotate-stdin", ["actor", "rotate", "-", "--by", "0,0,90"], f"{BAD}\n"),
    ("actor-scale-stdin", ["brush", "scale", "-", "--by", "2,2,2"], f"{BAD}\n"),
    ("actor-apply-transform-stdin", ["brush", "apply-transform", "-"], f"{BAD}\n"),
    ("actor-prop-get-stdin", ["actor", "prop", "get", "-", "Tag"], f"{BAD}\n"),
    ("actor-prop-set-stdin", ["actor", "prop", "set", "-", "Tag=x"], f"{BAD}\n"),
    ("actor-prop-unset-stdin", ["actor", "prop", "unset", "-", "Tag"], f"{BAD}\n"),
    ("actor-folder-set-stdin", ["actor", "folder", "set", "-", "--to", "a.b"], f"{BAD}\n"),
    ("actor-folder-get-stdin", ["actor", "folder", "get", "-"], f"{BAD}\n"),
    ("actor-folder-unset-stdin", ["actor", "folder", "unset", "-"], f"{BAD}\n"),
    ("brush-poly-set-stdin", ["brush", "poly", "set", "-", "--add-flag", "Unlit"], f"{BAD}:all\n"),
    ("brush-poly-pan-stdin", ["brush", "poly", "pan", "-", "--by", "0,32"], f"{BAD}:all\n"),
    ("brush-poly-rotate-stdin", ["brush", "poly", "rotate", "-", "--by", "16384"], f"{BAD}:all\n"),
    ("brush-poly-scale-stdin", ["brush", "poly", "scale", "-", "--by", "2,2"], f"{BAD}:all\n"),
    ("brush-poly-align-stdin", ["brush", "poly", "align", "--floor", "-"], f"{BAD}:0\n"),
]

_PARSER = build_parser()


def _run(argv, stdin):
    args = _PARSER.parse_args(argv)              # real grammar → faithful Namespace
    with mock.patch.object(level_sources, "resolve_level_source", return_value=_fake_src()), \
            mock.patch("sys.stdin", io.StringIO(stdin)):
        # If a bad-name lookup regresses to a bare KeyError/IndexError/StopIteration, it escapes
        # `dispatch` here and pytest reports the traceback — exactly the failure we guard against.
        return dispatch_mod.dispatch(args)


def _assert_clean_not_found(rc, capsys):
    err = capsys.readouterr().err
    assert rc == 2, f"expected exit 2, got {rc}; stderr={err!r}"
    low = err.lower()
    # A clean, named miss — never a traceback. Accepts the shared resolver's "Actor(s) not found:"
    # and the poly-target wrappers' "unknown brush …".
    assert ("not found" in low or "unknown brush" in low), f"message not clean/named: {err!r}"
    assert "Traceback" not in err


@pytest.mark.parametrize("argv,stdin", [(a, s) for _id, a, s in _POSITIONAL],
                         ids=[i for i, _a, _s in _POSITIONAL])
def test_positional_bad_name_is_clean_exit2(argv, stdin, capsys):
    _assert_clean_not_found(_run(argv, stdin), capsys)


@pytest.mark.parametrize("argv,stdin", [(a, s) for _id, a, s in _STDIN],
                         ids=[i for i, _a, _s in _STDIN])
def test_stdin_bad_name_is_clean_exit2(argv, stdin, capsys):
    _assert_clean_not_found(_run(argv, stdin), capsys)
