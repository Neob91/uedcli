"""Characterization baseline for the argparse tree built by `uedcli.cli.main.build_parser()`.

Slice 1 of the command-layer reorg (`dev/docs/board/to-build/reorganize-the-command-layer/`).
It freezes the CURRENT parser so a later slice that moves registration code cannot silently
change help text, the action tree, argv acceptance/rejection, or the parser's non-CLI import
closure. `test_parser_baseline.py` replays these helpers and compares them to the checked-in
fixtures under `fixtures/parser_baseline/`.

Regeneration is EXPLICIT — run `python -m uedcli.tests.parser_baseline` (or call `regenerate()`).
The tests only read the fixtures and compare; they never rewrite one on failure. After an
intended parser move the values must be identical, so a diff here is a real behavior change,
not a fixture that quietly re-baselined itself.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

from uedcli.cli import main as cli

FIXTURES = Path(__file__).parent / "fixtures" / "parser_baseline"
REPO_ROOT = Path(__file__).resolve().parents[2]

# Pin the help/usage wrapping width so the fixtures do not depend on the terminal running the
# suite. argparse derives its width from `shutil.get_terminal_size()`, which honours $COLUMNS
# before probing any tty, so setting it is enough.
HELP_COLUMNS = 80


@contextlib.contextmanager
def _pinned_width():
    old = os.environ.get("COLUMNS")
    os.environ["COLUMNS"] = str(HELP_COLUMNS)
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("COLUMNS", None)
        else:
            os.environ["COLUMNS"] = old


# --------------------------------------------------------------------- normalization

def _norm_value(v):
    """A stable, JSON-round-trippable form for a parsed value or an action attribute.

    Decimals and the odd non-primitive keep a tagged spelling so they compare exactly across a
    JSON round-trip; tuples flatten to lists (JSON has no tuple)."""
    if isinstance(v, Decimal):
        return {"__decimal__": str(v)}
    if isinstance(v, (list, tuple)):
        return [_norm_value(x) for x in v]
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    return {"__repr__": repr(v)}


def _norm_default(v):
    if v is argparse.SUPPRESS:
        return {"__suppress__": True}
    return _norm_value(v)


def _converter_name(t):
    """Callable converters compare by stable `__name__`, never object identity or defining
    module — the reorg moves the module, so identity/module would spuriously differ."""
    if t is None:
        return None
    return getattr(t, "__name__", repr(t))


# --------------------------------------------------------------------- parser walk

def iter_parsers(parser, path=("uedcli",)):
    """Yield `(path_tuple, parser)` for the root and every reachable sub-parser, depth-first in
    registration order."""
    yield path, parser
    for act in parser._actions:
        if isinstance(act, argparse._SubParsersAction):
            for name, sub in act.choices.items():
                yield from iter_parsers(sub, path + (name,))


def _action_entry(act, mx_index):
    is_sub = isinstance(act, argparse._SubParsersAction)
    return {
        "class": type(act).__name__,
        "option_strings": list(act.option_strings),
        "dest": act.dest,
        "nargs": act.nargs,
        "const": _norm_value(act.const),
        "default": _norm_default(act.default),
        "required": bool(act.required),
        # A sub-parsers action's `choices` is the child-parser map (recorded via `subparsers`);
        # only a plain action's `choices` value-list is recorded here.
        "choices": None if is_sub else (list(act.choices) if act.choices is not None else None),
        "metavar": _norm_value(act.metavar),   # a multi-token action's metavar is a tuple
        "converter": _converter_name(act.type),
        "help": act.help,
        "mutex_group": mx_index.get(id(act)),
    }


def action_tree(parser):
    """A normalized, JSON-able view of one parser and (recursively) its sub-parsers: parser class,
    prog, mutually-exclusive groups (order + required + members), and each action's class, option
    strings, dest, nargs, const, default, required, choices, metavar, converter name and mutex-group
    membership — everything the reorg must preserve."""
    mx_index = {}
    groups = []
    for gi, g in enumerate(parser._mutually_exclusive_groups):
        groups.append({"required": bool(g.required),
                       "members": [a.dest for a in g._group_actions]})
        for pos, a in enumerate(g._group_actions):
            mx_index[id(a)] = [gi, pos]

    actions = []
    subtrees = {}
    for act in parser._actions:
        entry = _action_entry(act, mx_index)
        if isinstance(act, argparse._SubParsersAction):
            entry["subparser_choices"] = list(act.choices.keys())
            entry["subparser_help"] = {c.dest: c.help for c in act._choices_actions}
            for name, sub in act.choices.items():
                subtrees[name] = action_tree(sub)
        actions.append(entry)

    return {
        "class": type(parser).__name__,
        "prog": parser.prog,
        "mutex_groups": groups,
        "actions": actions,
        "subparsers": subtrees,
    }


def help_screens():
    """`{path -> --help text}` for the root and every reachable sub-parser, at the pinned width."""
    out = {}
    with _pinned_width():
        parser = cli.build_parser()
        for path, sub in iter_parsers(parser):
            out[" ".join(path)] = sub.format_help()
    return out


# --------------------------------------------------------------------- argv corpus
# Cases from the spec: negative coordinates, `-X/-Y/-Z` facings, prefix abbreviation, required and
# mutually-exclusive groups, and multiple simultaneous mistakes. The generator RUNS the current
# parser, so whatever it produces IS the baseline; the categories only have to be exercised.

ARGV_CORPUS = [
    # negative coordinate tokens accepted as values, not options
    ["actor", "move", "L1", "--to", "-100,-200,-300"],
    ["brush", "vertex", "move", "B1", "--at", "-32,-32,32", "--by", "0,0,-16"],
    ["actor", "build", "Engine.Light", "--at", "-16,-16,-16"],
    ["brush", "build", "cube", "--at", "-128,-64,-32"],
    # -X/-Y/-Z facing values
    ["brush", "poly", "find", "B1", "--facing", "-Z"],
    ["brush", "poly", "find", "B1", "--facing", "-X"],
    ["brush", "poly", "find", "B1", "--facing", "+Y"],
    # prefix abbreviation (argparse allow_abbrev default True)
    ["actor", "find", "--exact", "Light"],
    ["actor", "find", "--subclass", "Engine.Light"],
    ["level", "prev", "at:0,0,0;rot:0,0", "--out-dir", "s"],
    # required mutually-exclusive group: missing / both members
    ["actor", "duplicate", "X"],
    ["actor", "duplicate", "X", "--by", "0,0,0", "--at", "0,0,0"],
    ["actor", "order", "X"],
    ["actor", "order", "X", "--first", "--last"],
    ["actor", "rotate", "X"],
    ["brush", "scale", "B", "--to", "1,1,1", "--by", "2,2,2"],
    # non-required mutually-exclusive group violated
    ["level", "preview", "at:0,0,0;rot:0,0", "--out-dir", "s", "--native", "--game"],
    ["actor", "find", "--folder", "F", "--no-folder"],
    # multiple simultaneous mistakes
    ["actor", "bogus", "--nope"],
    ["brush", "clip", "W", "--axis", "q", "--offset", "abc"],
    ["actor", "build", "Engine.Light", "--at", "nan,0,0"],
    # a --help path (exit 0, help to stdout)
    ["actor", "-h"],
]


def run_argv(argv):
    """Parse `argv` with a fresh parser under the pinned width, capturing outcome, exit code,
    stdout, stderr and the normalized namespace."""
    argv = list(argv)
    out, err = io.StringIO(), io.StringIO()
    result = {"argv": argv}
    with _pinned_width(), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            ns = cli.build_parser().parse_args(argv)
            result["outcome"] = "parsed"
            result["exit_code"] = None
            result["namespace"] = {k: _norm_value(v) for k, v in sorted(vars(ns).items())}
        except SystemExit as e:
            result["outcome"] = "exit"
            result["exit_code"] = e.code
            result["namespace"] = None
    result["stdout"] = out.getvalue()
    result["stderr"] = err.getvalue()
    return result


def argv_corpus_results():
    return [run_argv(a) for a in ARGV_CORPUS]


# --------------------------------------------------------------------- import closure
# The parser's exact non-CLI production-module closure, measured in a FRESH process so the
# suite's own imports cannot pollute it. Excludes the CLI boundary itself (`uedcli.cli*`, which
# now holds both `main` and `dispatch`) and the test package — what remains is the service closure
# the parser construction pulls in, which a reorg must not widen or narrow.

_CLOSURE_SNIPPET = (
    "import json, sys\n"
    "from uedcli.cli.main import build_parser\n"
    "build_parser()\n"
    "mods = sorted(\n"
    "    m for m in sys.modules\n"
    "    if (m == 'uedcli' or m.startswith('uedcli.'))\n"
    "    and not m.startswith('uedcli.tests')\n"
    "    and not m.startswith('uedcli.cli')\n"
    ")\n"
    "print(json.dumps(mods))\n"
)


def compute_import_closure():
    proc = subprocess.run(
        [sys.executable, "-c", _CLOSURE_SNIPPET],
        cwd=str(REPO_ROOT), capture_output=True, text=True, check=True,
    )
    return json.loads(proc.stdout)


# --------------------------------------------------------------------- fixtures I/O

def _write(name, payload):
    (FIXTURES / name).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def regenerate():
    """Rewrite every parser-baseline fixture from the current parser. EXPLICIT only."""
    FIXTURES.mkdir(parents=True, exist_ok=True)
    _write("help.json", help_screens())
    _write("action_tree.json", action_tree(cli.build_parser()))
    _write("argv_corpus.json", argv_corpus_results())
    _write("import_closure.json", compute_import_closure())
    print(f"regenerated parser baseline fixtures in {FIXTURES}")


if __name__ == "__main__":
    regenerate()
