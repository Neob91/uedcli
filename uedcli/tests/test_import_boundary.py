"""AST-enforced import-boundary rules for the command-layer reorganization.

This file accumulates the structural dependency rules as the reorg makes each one true (spec
"Dependency rules"; plan slices 2, 3, 4, 10). It parses each production module and walks EVERY
import node, including those inside function bodies, so a lazy `from ..cli.dispatch import …` cannot
hide from it.

After slice 10 this enforces every structural rule 1-9 (spec "Dependency rules"):

- Rule 1: `__main__.py` imports the `main` FUNCTION from `cli.main`, not the module.
- Rule 2: `cli.main` imports the parser registrars at module scope and `cli.dispatch` only inside
  `main()`.
- Rule 3: the `cli.parsers` tier imports within itself + lower services only, and only `cli.main`
  imports it.
- Rule 4: the execution owners obey the total order errors < resources < level_sources < ingest <
  targets < rendering < placement < generators < commands < dispatch < main — a module imports an
  earlier owner and lower services, never a later one.
- Rule 5: the five cross-family orchestrators import no command family; no family imports another.
- Rule 6: `cli.dispatch` imports only the eight error owners (plus os/sys) at module scope and loads
  the selected family with function-local imports of `cli.commands`.
- Rule 7: no production module outside `cli/`, except `__main__.py`, imports any `cli` module.
- Rule 8: every `__init__.py` under `uedcli/cli/` is import-free (docstring only).
- Rule 9: no strongly connected component (of the whole production import graph, function bodies
  included) contains a `cli` module.

Plus the packaging invariant: every package discovered under `uedcli/cli/` appears in setuptools'
static package list, so a source-tree-green move cannot ship a broken wheel.
"""
from __future__ import annotations

import ast
import tomllib
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent          # the `uedcli` package dir
REPO = PKG.parent                                     # the dir that contains `uedcli/`
CLI = PKG / "cli"                                     # the command-layer package

# The routing module and its only legitimate importer live here. Everything else is a service or a
# command family and must not import `dispatch`.
_DISPATCH = "uedcli.cli.dispatch"
_BOUNDARY = {CLI / "dispatch.py", CLI / "main.py"}


def _production_modules() -> list[Path]:
    """Every production `.py` under `uedcli/`, excluding the test package itself."""
    return sorted(p for p in PKG.rglob("*.py") if "tests" not in p.relative_to(PKG).parts)


def _module_name(path: Path) -> tuple[str, bool]:
    """The dotted module name for a file under the repo, and whether it is a package `__init__`."""
    parts = list(path.relative_to(REPO).parts)
    is_pkg = parts[-1] == "__init__.py"
    if is_pkg:
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-len(".py")]
    return ".".join(parts), is_pkg


def _imported_names(tree: ast.AST, mod_name: str, is_pkg: bool) -> set[str]:
    """Every absolute module name imported anywhere in `tree`, relative imports resolved."""
    base = mod_name.split(".")
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                drop = node.level - (1 if is_pkg else 0)
                anchor = base[: len(base) - drop]
                prefix = ".".join(anchor + ([node.module] if node.module else []))
            else:
                prefix = node.module or ""
            names.add(prefix)
            names.update(f"{prefix}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
    return names


def test_no_production_module_outside_the_boundary_imports_dispatch():
    offenders = []
    for path in _production_modules():
        if path in _BOUNDARY:
            continue
        mod_name, is_pkg = _module_name(path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if _DISPATCH in _imported_names(tree, mod_name, is_pkg):
            offenders.append(str(path.relative_to(PKG)))
    assert not offenders, (
        "these non-boundary production modules import `cli.dispatch` (the reverse/inward edge the "
        f"reorg forbids): {', '.join(offenders)}")


def test_every_cli_package_initializer_is_import_free():
    """Every `__init__.py` under `uedcli/cli/` is docstring-only: no imports or re-exports."""
    offenders = []
    for init in sorted(CLI.rglob("__init__.py")):
        tree = ast.parse(init.read_text(encoding="utf-8"))
        if any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(tree)):
            offenders.append(str(init.relative_to(PKG)))
    assert not offenders, (
        "these CLI package initializers must be docstring-only (no imports/re-exports): "
        f"{', '.join(offenders)}")


def _static_package_list() -> list[str]:
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    return data["tool"]["setuptools"]["packages"]


def test_every_cli_package_is_in_the_static_package_list():
    """Every package discovered under `uedcli/cli/` is declared to setuptools, so the wheel ships
    it. Scoped to the CLI subtree; the pre-existing omission of other runtime subpackages is tracked
    separately."""
    declared = set(_static_package_list())
    discovered = {_module_name(init)[0] for init in CLI.rglob("__init__.py")}
    missing = sorted(discovered - declared)
    assert not missing, (
        "these packages under uedcli/cli/ are not in pyproject's static package list "
        f"(the wheel would omit them): {', '.join(missing)}")


# Slice 4/6: the execution-owner total order (spec "Dependency rules" rule 4). A module may import
# an earlier owner and lower services, never a later owner. Slice 6 adds the five cross-family
# orchestrators; later slices append `commands` as it lands.
_OWNER_ORDER = ["errors", "resources", "level_sources", "ingest", "targets", "rendering",
                "placement", "generators"]

# The five cross-family orchestrators established in slice 6 (spec "Dependency rules" rule 5).
_ORCHESTRATORS = ["ingest", "targets", "rendering", "placement", "generators"]


def test_owner_modules_obey_the_leftward_order():
    offenders = []
    for i, name in enumerate(_OWNER_ORDER):
        path = CLI / f"{name}.py"
        mod_name, is_pkg = _module_name(path)
        imported = _imported_names(ast.parse(path.read_text(encoding="utf-8")), mod_name, is_pkg)
        for later in _OWNER_ORDER[i + 1:]:
            if f"uedcli.cli.{later}" in imported:
                offenders.append(f"{name} imports later owner {later}")
    assert not offenders, (
        "these owner modules import a later owner (forbidden by the leftward order "
        f"{' < '.join(_OWNER_ORDER)}): {'; '.join(offenders)}")


def test_orchestrators_import_no_command_family():
    """The cross-family orchestrators never import a command family, the routing module or the
    parser tier (spec "Dependency rules" rule 5). Command families live in `cli.dispatch` today and
    move to `cli.commands` in later slices; either home is forbidden here. Only earlier owners and
    lower services (outside `cli`) are allowed — the leftward-order test above covers the owners."""
    forbidden = ("uedcli.cli.commands", "uedcli.cli.dispatch", "uedcli.cli.main",
                 "uedcli.cli.parsers")
    offenders = []
    for name in _ORCHESTRATORS:
        path = CLI / f"{name}.py"
        mod_name, is_pkg = _module_name(path)
        imported = _imported_names(ast.parse(path.read_text(encoding="utf-8")), mod_name, is_pkg)
        for imp in imported:
            if any(imp == f or imp.startswith(f + ".") for f in forbidden):
                offenders.append(f"{name} imports {imp}")
    assert not offenders, (
        "these orchestrators import a command family / routing / parser module (rule 5 forbids it; "
        f"they may import only earlier owners and lower services): {'; '.join(offenders)}")


# Slice 7+: command families live under `cli.commands`. A family is the first path component below
# `commands` (a flat `<family>.py` module, or an `<family>/` package). No family imports another
# family (spec "Dependency rules" rule 5).
COMMANDS = CLI / "commands"
_COMMANDS_PKG = "uedcli.cli.commands"


def _family_of(path: Path) -> str:
    """The command-family name a module under `cli/commands/` belongs to (first component below
    `commands`): `commands/docs.py` → `docs`, `commands/actor/routes.py` → `actor`."""
    rel = path.relative_to(COMMANDS).parts
    return rel[0][:-len(".py")] if len(rel) == 1 else rel[0]


def test_no_command_family_imports_another_family():
    offenders = []
    for path in sorted(COMMANDS.rglob("*.py")):
        if path.name == "__init__.py" and path.parent == COMMANDS:
            continue                                      # the package initializer imports nothing
        family = _family_of(path)
        mod_name, is_pkg = _module_name(path)
        imported = _imported_names(ast.parse(path.read_text(encoding="utf-8")), mod_name, is_pkg)
        for imp in imported:
            if imp.startswith(_COMMANDS_PKG + "."):
                other = imp[len(_COMMANDS_PKG) + 1:].split(".")[0]
                if other and other != family:
                    offenders.append(f"{mod_name} imports family {other} ({imp})")
    assert not offenders, (
        "these command modules import another command family (rule 5 forbids it): "
        f"{'; '.join(offenders)}")


# Slice 5: the parser tier (spec "Dependency rules" rules 2 & 3).
PARSERS = CLI / "parsers"
_PARSER_TIER = "uedcli.cli.parsers"


def _module_scope_imports(tree: ast.Module, mod_name: str, is_pkg: bool) -> set[str]:
    """Imports at module scope only — direct children of the module body, not inside a function."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names |= _imported_names(node, mod_name, is_pkg)
    return names


def test_parser_modules_import_no_other_cli_module():
    """A `cli.parsers` module imports within `cli.parsers` (especially `_arguments`) and lower
    services only — never another `cli` module (rule 3)."""
    offenders = []
    for path in sorted(PARSERS.rglob("*.py")):
        mod_name, is_pkg = _module_name(path)
        imported = _imported_names(ast.parse(path.read_text(encoding="utf-8")), mod_name, is_pkg)
        for name in imported:
            if name == "uedcli.cli" or (
                name.startswith("uedcli.cli.") and not name.startswith(_PARSER_TIER)
            ):
                offenders.append(f"{mod_name} imports {name}")
    assert not offenders, (
        "these parser-tier modules import another cli module (rule 3 allows only cli.parsers + "
        f"lower services): {'; '.join(offenders)}")


def test_only_cli_main_imports_the_parser_tier():
    """Only `cli.main` (and the parser modules among themselves) import `cli.parsers` (rule 3)."""
    offenders = []
    for path in _production_modules():
        mod_name, is_pkg = _module_name(path)
        if mod_name == "uedcli.cli.main" or mod_name.startswith(_PARSER_TIER):
            continue
        imported = _imported_names(ast.parse(path.read_text(encoding="utf-8")), mod_name, is_pkg)
        if any(n == _PARSER_TIER or n.startswith(_PARSER_TIER + ".") for n in imported):
            offenders.append(mod_name)
    assert not offenders, (
        "these modules import the parser tier, but only cli.main may (rule 3): "
        f"{', '.join(offenders)}")


def test_cli_main_imports_dispatch_only_inside_a_function():
    """`cli.main` imports `cli.dispatch` lazily inside `main()` after parsing, never at module scope;
    it imports the parser registrars at module scope (rule 2)."""
    path = CLI / "main.py"
    mod_name, is_pkg = _module_name(path)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    module_scope = _module_scope_imports(tree, mod_name, is_pkg)
    assert _DISPATCH not in module_scope, (
        "cli.main must import cli.dispatch inside main() (after parsing), not at module scope (rule 2)")
    assert _PARSER_TIER in module_scope, (
        "cli.main must import the parser registrars at module scope (rule 2)")


# ── Slice 10: the final rules 1, 4 (full), 6, 7 (full) and 9. ─────────────────────────────────

# Rule 4's total execution order. A cli module "belongs to" one of these owners (or to `commands`
# for anything under `cli/commands/`); the parser tier and the package `__init__` belong to none.
_TOTAL_ORDER = ["errors", "resources", "level_sources", "ingest", "targets", "rendering",
                "placement", "generators", "commands", "dispatch", "main"]


def _cli_owner(name: str) -> str | None:
    """The execution owner a dotted `uedcli.cli.*` name belongs to, or None (the parser tier and the
    package initializer belong to no execution owner — they have their own rules)."""
    if not name.startswith("uedcli.cli."):
        return None
    head = name[len("uedcli.cli."):].split(".")[0]
    return head if head in _TOTAL_ORDER else None


def test_main_imports_the_main_function_not_the_module():
    """Rule 1: `__main__.py` uses `from .cli.main import main` — the FUNCTION, not the `cli.main`
    module (`from .cli import main`). Only the former binds the name `uedcli.cli.main.main`."""
    path = PKG / "__main__.py"
    mod_name, is_pkg = _module_name(path)
    imported = _imported_names(ast.parse(path.read_text(encoding="utf-8")), mod_name, is_pkg)
    assert "uedcli.cli.main.main" in imported, (
        "uedcli/__main__.py must `from .cli.main import main` (import the function, so `__main__` "
        "does not depend on the module object) — rule 1")


def test_execution_owners_obey_the_total_order():
    """Rule 4: every cli execution-owner module (the flat owners, everything under `cli/commands/`,
    `cli.dispatch` and `cli.main`) imports an EARLIER owner and lower services only, never a later
    one. Subsumes the flat-owner leftward-order check above and extends it through commands/dispatch/
    main."""
    rank = {n: i for i, n in enumerate(_TOTAL_ORDER)}
    offenders = []
    for path in _production_modules():
        mod_name, is_pkg = _module_name(path)
        owner = _cli_owner(mod_name)
        if owner is None:
            continue
        imported = _imported_names(ast.parse(path.read_text(encoding="utf-8")), mod_name, is_pkg)
        for imp in imported:
            imp_owner = _cli_owner(imp)
            if imp_owner is not None and rank[imp_owner] > rank[owner]:
                offenders.append(f"{mod_name} ({owner}) imports later owner {imp_owner} ({imp})")
    assert not offenders, (
        "these cli modules import a later execution owner (forbidden by the total order "
        f"{' < '.join(_TOTAL_ORDER)}): {'; '.join(offenders)}")


# Rule 6: the ONLY names `cli.dispatch` may import at module scope — os/sys, `from __future__`, and
# the eight error owners the ordered process guard catches. Everything else (the command families,
# the orchestrators, every service) loads function-locally.
_DISPATCH_MODULE_SCOPE_ALLOWED = {
    "__future__", "__future__.annotations", "os", "sys",
    "uedcli.classindex", "uedcli.classindex.ClassRefError",
    "uedcli.config", "uedcli.config.ConfigError",
    "uedcli.driver", "uedcli.driver.DriverError",
    "uedcli.geometry", "uedcli.geometry.GeometryError",
    "uedcli.model", "uedcli.model.CoordinateError",
    "uedcli.schema_cache", "uedcli.schema_cache.CacheWriteError",
    "uedcli.uprops", "uedcli.uprops.SchemaError",
    "uedcli.cli.errors", "uedcli.cli.errors.CommandError", "uedcli.cli.errors.ProjectError",
}


def test_dispatch_module_scope_imports_only_the_error_owners():
    """Rule 6: `cli.dispatch` imports only the enumerated error owners (plus os/sys/`__future__`) at
    module scope, and routes to the selected family with FUNCTION-LOCAL imports of `cli.commands`."""
    path = CLI / "dispatch.py"
    mod_name, is_pkg = _module_name(path)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    module_scope = _module_scope_imports(tree, mod_name, is_pkg)
    extra = sorted(module_scope - _DISPATCH_MODULE_SCOPE_ALLOWED)
    assert not extra, (
        "cli.dispatch imports these at module scope, but rule 6 allows only os/sys and the eight "
        f"error owners there (every family/orchestrator/service loads function-locally): {extra}")
    all_imports = _imported_names(tree, mod_name, is_pkg)
    assert any(n.startswith(_COMMANDS_PKG) for n in all_imports), (
        "cli.dispatch must route to the command families via function-local imports of cli.commands "
        "(rule 6) — none found")
    assert not any(n.startswith(_COMMANDS_PKG) for n in module_scope), (
        "cli.dispatch must import command families function-locally, not at module scope (rule 6)")


def test_no_module_outside_cli_imports_a_cli_module():
    """Rule 7: no production module outside `cli/`, except `__main__.py`, imports any `cli` module."""
    offenders = []
    for path in _production_modules():
        mod_name, is_pkg = _module_name(path)
        if mod_name == "uedcli.__main__" or mod_name == "uedcli.cli" \
                or mod_name.startswith("uedcli.cli."):
            continue
        imported = _imported_names(ast.parse(path.read_text(encoding="utf-8")), mod_name, is_pkg)
        for imp in imported:
            if imp == "uedcli.cli" or imp.startswith("uedcli.cli."):
                offenders.append(f"{mod_name} imports {imp}")
    assert not offenders, (
        "these non-cli production modules import a cli module (only __main__.py may — rule 7): "
        f"{'; '.join(offenders)}")


def _resolve_to_module(name: str, modules: dict) -> str | None:
    """The longest dotted prefix of `name` that is a known production module, or None. Maps an
    imported name like `uedcli.cli.resources.mover_index` to its module `uedcli.cli.resources`."""
    parts = name.split(".")
    for i in range(len(parts), 0, -1):
        cand = ".".join(parts[:i])
        if cand in modules:
            return cand
    return None


def _strongly_connected_components(graph: dict) -> list[list[str]]:
    """Tarjan's SCC over a {node: {successors}} graph, iterative (the graph is large)."""
    index_of: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    sccs: list[list[str]] = []
    counter = 0

    for root in graph:
        if root in index_of:
            continue
        work = [(root, iter(graph[root]))]
        index_of[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, succ = work[-1]
            advanced = False
            for nxt in succ:
                if nxt not in index_of:
                    index_of[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, iter(graph[nxt])))
                    advanced = True
                    break
                if nxt in on_stack:
                    low[node] = min(low[node], index_of[nxt])
            if advanced:
                continue
            if low[node] == index_of[node]:
                comp = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.append(w)
                    if w == node:
                        break
                sccs.append(comp)
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
    return sccs


def test_no_strongly_connected_component_contains_a_cli_module():
    """Rule 9: no SCC of the whole production import graph (function-body imports included) contains
    a `cli` module. Pre-existing low-level cycles are tolerated only because they hold no cli
    module."""
    paths = _production_modules()
    modules = {}
    for p in paths:
        name, is_pkg = _module_name(p)
        modules[name] = (p, is_pkg)
    graph: dict[str, set[str]] = {name: set() for name in modules}
    for name, (p, is_pkg) in modules.items():
        for imp in _imported_names(ast.parse(p.read_text(encoding="utf-8")), name, is_pkg):
            target = _resolve_to_module(imp, modules)
            if target is not None and target != name:
                graph[name].add(target)
    bad = [sorted(scc) for scc in _strongly_connected_components(graph)
           if len(scc) > 1 and any(n.startswith("uedcli.cli") for n in scc)]
    assert not bad, (
        "these strongly connected components contain a cli module (rule 9 forbids any CLI cycle): "
        f"{bad}")
