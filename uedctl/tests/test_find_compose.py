from __future__ import annotations
import io
from types import SimpleNamespace
from unittest import mock

from uedctl.cli import build_parser
from uedctl.dispatch import dispatch
from uedctl.model import Actor, Level


def _lv(*names):
    lv = Level()
    for n in names:
        lv.actors[n] = Actor(name=n, cls="Engine.Brush", location=None, props=[])
    lv.order = list(names)
    return lv


def _find_args(**over):
    base = dict(cmd="actor", sub="find", name=None, cls=[], subclass_of=[], group=None,
                prop=[], folder=[], no_folder=False, kind=None, json=False, tree=None,
                restrict=None, exclude=False)
    base.update(over)
    return SimpleNamespace(**base)


def _run(args, level, stdin=""):
    src = mock.Mock(); src.load.return_value = level
    out = io.StringIO()
    with mock.patch("uedctl.dispatch._resolve_level_source", return_value=src), \
            mock.patch("sys.stdin", io.StringIO(stdin)), \
            mock.patch("sys.stdout", out):
        rc = dispatch(args)
    return rc, out.getvalue()


def test_it_parses_find_restrict_and_exclude():
    p = build_parser()
    ns = p.parse_args(["actor", "find", "--group", "A", "--exclude", "-"])
    assert ns.restrict == "-"
    assert ns.exclude is True


def test_it_defaults_restrict_none_and_exclude_false():
    p = build_parser()
    ns = p.parse_args(["actor", "find", "--group", "A"])
    assert ns.restrict is None
    assert ns.exclude is False


def test_it_intersects_the_piped_universe_with_the_filters():
    lv = _lv("A1", "A2", "B1")           # find all, restricted to the piped {A1, B1}
    rc, out = _run(_find_args(restrict="-"), lv, stdin="A1\nB1\n")
    assert rc == 0
    assert out.splitlines() == ["A1", "B1"]


def test_it_excludes_the_matches_from_the_universe_when_exclude():
    lv = _lv("A1", "A2", "B1")           # universe {A1,A2,B1}; predicate = name A2; exclude → drop A2
    rc, out = _run(_find_args(name=["A2"], restrict="-", exclude=True), lv,
                   stdin="A1\nA2\nB1\n")
    assert rc == 0
    assert out.splitlines() == ["A1", "B1"]


def test_it_keeps_in_tree_order_regardless_of_piped_order():
    lv = _lv("A1", "A2", "A3")
    rc, out = _run(_find_args(restrict="-"), lv, stdin="A3\nA1\n")
    assert out.splitlines() == ["A1", "A3"]        # tree order, not piped order


def test_it_resolves_piped_names_case_insensitively():
    lv = _lv("Wall_N")
    rc, out = _run(_find_args(restrict="-"), lv, stdin="wall_n\n")
    assert out.splitlines() == ["Wall_N"]


def test_it_errors_exit2_on_an_unknown_piped_name():
    lv = _lv("A1")
    rc, out = _run(_find_args(restrict="-"), lv, stdin="A1\nNope\n")
    assert rc == 2
    assert out == ""                                # nothing printed on error


def test_it_is_a_clean_noop_on_empty_stdin():
    lv = _lv("A1", "A2")
    rc, out = _run(_find_args(restrict="-"), lv, stdin="")
    assert rc == 0
    assert out == ""


def test_it_errors_exit2_when_exclude_without_dash():
    lv = _lv("A1")
    rc, out = _run(_find_args(exclude=True), lv)
    assert rc == 2


def test_it_errors_exit2_on_a_non_dash_positional():
    rc, out = _run(_find_args(restrict="foo"), _lv("A1"))
    assert rc == 2
    assert out == ""


def test_it_ands_the_universe_with_a_real_filter():
    lv = _lv("A1", "A2", "B1")                  # universe {A1,B1}, predicate name=A1 → {A1}
    rc, out = _run(_find_args(name=["A1"], restrict="-"), lv, stdin="A1\nB1\n")
    assert rc == 0
    assert out.splitlines() == ["A1"]


def test_it_returns_empty_for_exclude_with_no_filters():
    rc, out = _run(_find_args(restrict="-", exclude=True), _lv("A1", "A2"), stdin="A1\n")
    assert rc == 0
    assert out == ""


def test_it_json_reflects_the_restricted_set():
    lv = _lv("A1", "A2", "B1")
    rc, out = _run(_find_args(restrict="-", json=True), lv, stdin="A1\nB1\n")
    import json as _json
    assert _json.loads(out) == ["A1", "B1"]
