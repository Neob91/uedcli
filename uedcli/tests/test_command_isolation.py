"""Fresh-process import-isolation for the `cli.commands` families (plan slice 7, spec §8).

Two guarantees, each measured in a CLEAN interpreter because this suite's own `sys.modules` is long
since polluted:

- HEAVY-IMPORT sentinels: invoking the low-dependency `docs` and `cache` families loads none of the
  heavy stacks (`apply`, `materialize`, `editor`, `preview_game`, `preview_native`, `native.*`,
  `uedcli_native`, PIL/image).
- FAMILY ISOLATION: invoking one top-level family loads no OTHER family's command module under
  `uedcli.cli.commands`.

The probe builds the real parser, parses the argv, and calls `dispatch.dispatch(args)` — so the
router's function-local import of the selected family runs exactly as in production. A handler that
needs a project exits 2 (no project in the sandbox), but its family module is still imported, which
is all these tests measure.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

# The dir HOLDING the `uedcli` package, so the child can import it via a single sys.path entry with
# PYTHONPATH stripped (it measures THIS tree, not whatever bin/test exports).
_ROOT = pathlib.Path(__file__).resolve().parents[2]
_COMMANDS_DIR = pathlib.Path(__file__).resolve().parents[1] / "cli" / "commands"

# The heavy stacks a low-dependency command must never pull in (spec "Command handlers and routing").
_HEAVY = (
    "uedcli.apply", "uedcli.materialize", "uedcli.editor", "uedcli.preview_game",
    "uedcli.preview_native", "uedcli.native", "uedcli_native", "PIL",
)

# Every family that moves into `cli.commands` (slices 7–10), with an argv that routes to each. The
# handler may exit 2 (no project), but the router imports the family module first, which is what we
# measure. `actor` is a package (its `preview` route landed in slice 8); the rest are flat modules.
# Filtered to the families whose module/package already exists, so the suite stays green as each
# family lands and automatically covers the next one — a family cannot ship without its case.
_ALL_FAMILIES = {
    "docs": ["docs", "list"],
    "cache": ["cache", "clear"],
    "project": ["project", "show"],
    "classes": ["class", "list"],
    "texture": ["texture", "tags"],
    "substrate": ["substrate", "stub", "--list"],
    "actor": ["actor", "preview"],
    "brush": ["brush", "build", "cube", "--width", "1", "--breadth", "1", "--height", "1"],
    "mover": ["mover", "key", "list", "X"],
    "stash": ["stash", "list"],
    "prefab": ["prefab", "list"],
    "level": ["level", "list"],
    "event": ["event", "graph"],
}
_FAMILIES = {fam: argv for fam, argv in _ALL_FAMILIES.items()
             if (_COMMANDS_DIR / f"{fam}.py").exists()
             or (_COMMANDS_DIR / fam / "__init__.py").exists()}

_PROBE = r"""
import sys, os, io, json, contextlib
sys.path.insert(0, {root!r})
from uedcli.cli.main import build_parser
args = build_parser().parse_args(json.loads(os.environ["UEDCLI_ISO_ARGV"]))
from uedcli.cli import dispatch
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    try:
        dispatch.dispatch(args)
    except SystemExit:
        pass
loaded = sorted(
    m for m in sys.modules
    if m == "uedcli_native" or m.startswith("uedcli_native.")
    or m == "PIL" or m.startswith("PIL.")
    or m == "uedcli.native" or m.startswith("uedcli.native.")
    or m in ("uedcli.apply", "uedcli.materialize", "uedcli.editor",
             "uedcli.preview_game", "uedcli.preview_native")
    or m.startswith("uedcli.cli.commands.")
)
print(json.dumps(loaded))
"""


def _loaded_modules(argv: list[str], tmp_home: pathlib.Path) -> list[str]:
    """The watched modules present in `sys.modules` after a fresh process invokes `argv`."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["HOME"] = str(tmp_home)                       # keep cache/stub verbs off the real home
    env["UEDCLI_ISO_ARGV"] = json.dumps(argv)
    done = subprocess.run(
        [sys.executable, "-c", _PROBE.format(root=str(_ROOT))],
        env=env, text=True, capture_output=True, check=True,
    )
    return json.loads(done.stdout)


@pytest.mark.parametrize("family", [f for f in ("docs", "cache") if f in _FAMILIES])
def test_low_dependency_family_loads_no_heavy_stack(family, tmp_path):
    """`docs` and `cache` are the low-dependency sentinels: invoking them loads none of the heavy
    import stacks (spec §8)."""
    loaded = set(_loaded_modules(_FAMILIES[family], tmp_path))
    heavy = {m for m in loaded
             if any(m == h or m.startswith(h + ".") for h in _HEAVY)}
    assert not heavy, f"invoking `{family}` loaded heavy modules: {sorted(heavy)}"


@pytest.mark.parametrize("family", sorted(_FAMILIES))
def test_family_invocation_loads_no_other_family(family, tmp_path):
    """Invoking one top-level family loads no OTHER family's command module (spec §8)."""
    loaded = _loaded_modules(_FAMILIES[family], tmp_path)
    own = f"uedcli.cli.commands.{family}"
    # A package family (e.g. `actor`) legitimately loads its own submodules (`actor.routes`,
    # `actor.preview`); those are the family, not another family, so exclude `own.`-prefixed names.
    others = [m for m in loaded
              if m.startswith("uedcli.cli.commands.") and m != own
              and not m.startswith(own + ".")]
    assert not others, f"invoking `{family}` loaded other families' command modules: {others}"
    assert own in loaded, f"invoking `{family}` did not load its own command module {own}"


# The actor ROUTE MATRIX (spec "Command handlers and routing"): `actor/routes.py` imports only the
# selected feature module, so each subverb loads its own feature module and NONE of the siblings —
# `actor find` loads `actor.query`, never `actor.edit`/`build`/…. Each argv is argparse-valid and
# uses a literal name (not `-`) so no branch reads stdin; in the sandbox every one exits 2 (no
# project), but its owning module is imported first, which is what we measure.
_ACTOR_PKG = "uedcli.cli.commands.actor"
_ACTOR_FEATURES = ("build", "preview", "query", "folder", "label", "prop", "edit")
_ACTOR_ROUTE_MATRIX = {
    "build":     (["actor", "build", "Engine.Light"], "build"),
    "preview":   (["actor", "preview", "X"], "preview"),
    "find":      (["actor", "find"], "query"),
    "show":      (["actor", "show", "X"], "query"),
    "bbox":      (["actor", "bbox", "X"], "query"),
    "folder":    (["actor", "folder", "get", "X"], "folder"),
    "label":     (["actor", "label", "get", "X"], "label"),
    "prop":      (["actor", "prop", "get", "X"], "prop"),
    "add":       (["actor", "add", "dummy.t3d"], "edit"),
    "duplicate": (["actor", "duplicate", "X", "--by", "1,0,0"], "edit"),
    "order":     (["actor", "order", "X", "--first"], "edit"),
    "delete":    (["actor", "delete", "X"], "edit"),
    "move":      (["actor", "move", "X", "--by", "1,0,0"], "edit"),
    "rotate":    (["actor", "rotate", "X", "--by", "0,0,0"], "edit"),
}


@pytest.mark.parametrize("verb", sorted(_ACTOR_ROUTE_MATRIX))
def test_actor_route_loads_only_its_feature_module(verb, tmp_path):
    """Each `actor` subverb loads ONLY its owning feature module (feature isolation)."""
    argv, owner = _ACTOR_ROUTE_MATRIX[verb]
    loaded = _loaded_modules(argv, tmp_path)
    own = f"{_ACTOR_PKG}.{owner}"
    assert own in loaded, f"`actor {verb}` did not load its feature module {own}"
    leaked = [f"{_ACTOR_PKG}.{f}" for f in _ACTOR_FEATURES
              if f != owner and f"{_ACTOR_PKG}.{f}" in loaded]
    assert not leaked, f"`actor {verb}` loaded sibling feature modules: {leaked}"


# The brush ROUTE MATRIX (spec "Command handlers and routing"): `brush/routes.py` imports only the
# selected feature module, so each subverb loads its own and NONE of the siblings — the stateless
# `build` and CSG `intersect`/`deintersect` route source-free, the rest after the single eager
# source resolution. Each argv is argparse-valid and uses a literal name/FILE (not stdin) so no
# branch reads stdin; in the sandbox every one exits 2 (no project — or a missing FILE for the CSG
# generators), but its owning module is imported first, which is what we measure.
_BRUSH_PKG = "uedcli.cli.commands.brush"
_BRUSH_FEATURES = ("build", "edit", "poly", "vertex")
_BRUSH_ROUTE_MATRIX = {
    "build":           (["brush", "build", "cube", "--width", "1", "--breadth", "1",
                         "--height", "1"], "build"),
    "intersect":       (["brush", "intersect", "nonexistent.t3d"], "edit"),
    "deintersect":     (["brush", "deintersect", "nonexistent.t3d"], "edit"),
    "scale":           (["brush", "scale", "X", "--to", "1,1,1"], "edit"),
    "apply-transform": (["brush", "apply-transform", "X"], "edit"),
    "clip":            (["brush", "clip", "X", "--axis", "z", "--offset", "0"], "edit"),
    "replace":         (["brush", "replace", "X", "-"], "edit"),
    "poly":            (["brush", "poly", "list", "X"], "poly"),
    "vertex":          (["brush", "vertex", "list", "X"], "vertex"),
}


@pytest.mark.parametrize("verb", sorted(_BRUSH_ROUTE_MATRIX))
def test_brush_route_loads_only_its_feature_module(verb, tmp_path):
    """Each `brush` subverb loads ONLY its owning feature module (feature isolation)."""
    argv, owner = _BRUSH_ROUTE_MATRIX[verb]
    loaded = _loaded_modules(argv, tmp_path)
    own = f"{_BRUSH_PKG}.{owner}"
    assert own in loaded, f"`brush {verb}` did not load its feature module {own}"
    leaked = [f"{_BRUSH_PKG}.{f}" for f in _BRUSH_FEATURES
              if f != owner and f"{_BRUSH_PKG}.{f}" in loaded]
    assert not leaked, f"`brush {verb}` loaded sibling feature modules: {leaked}"
