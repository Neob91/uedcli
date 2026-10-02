"""Import-layering gate for the split packages `uedcli/uprops/` and `uedcli/propedit/`.

Each package is a stack of layers: a module may import a layer BELOW it, never one above. The
rank tables below are the layer order; `__init__` ranks last in both because it is pure
re-export and therefore imports from every sibling.

Two things this walks that a naive scan would miss:

- **Function bodies, not just module scope** (`ast.walk`, not `tree.body`). A lazy in-function
  import is exactly the reflex a cycle invites, and the spec forbids it as an escape hatch.
  `test_import_boundary.py` walks the same way for the same reason.
- **Every spelling, by resolving each import rather than matching its shape.** Relative,
  absolute, parent-relative and `import x.y.z` all name the same module, and an import of the
  package ROOT counts as `__init__` — that is the partially-initialised-package cycle. `..upackage`
  resolves outside the package and is ignored, as it must be.

The `test_the_layering_gate_reports_*` cases are the negative controls — one per spelling the gate
must catch. Two positive controls guard the other direction:
`..._passes_a_downward_edge_and_an_out_of_package_one`, and
`..._allows_a_submodule_imported_off_the_package_root`, which is the only thing standing between
`from uedcli.uprops import base` and being falsely flagged as a root cycle.
The real check is green-by-skip until the packages exist, and a check nobody has watched fail is a
check nobody knows works.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Sequence

import pytest

PKG = Path(__file__).resolve().parent.parent          # the `uedcli` package dir

# Package name -> its layer order, lowest first. A module NOT listed here is not checked at all,
# so `test_the_rank_table_names_every_module` asserts the table and the directory agree.
LAYERS: dict[str, tuple[str, ...]] = {
    "uprops": ("base", "ufield", "uclass", "values", "__init__"),
    "propedit": ("base", "tokens", "paths", "structtext", "fields", "edit", "__init__"),
}


def _sibling_imports(tree: ast.AST, pkg: str, siblings: frozenset[str]) -> set[str]:
    """Every in-package sibling a tree imports, anywhere in it (function bodies included).

    Each import is RESOLVED to an absolute module name and then tested against the package, rather
    than pattern-matched per spelling — `from .values import X`, `from uedcli.uprops.values import
    X`, `import uedcli.uprops.values` and `from ..uprops.values import X` all name one module, and a
    gate that recognised only some of them would pass an upward edge written the other way.

    Importing a SYMBOL from the package root resolves to `__init__`, ranked last, so a submodule
    reaching back through the root — the partially-initialised-package cycle `spec.md` warns about —
    reads as the upward edge it is. Importing a SUBMODULE from the root
    (`from uedcli.uprops import base`) is not that: at runtime it is identical to `from . import
    base` and binds no root attribute, so it counts as an edge to `base`, not to `__init__`.
    `..upackage` resolves outside `pkg` and is ignored.
    """
    parent = pkg.rpartition(".")[0]
    out: set[str] = set()

    def take(absolute: str) -> None:
        if absolute == pkg:
            out.add("__init__")
        elif absolute.startswith(f"{pkg}."):
            out.add(absolute[len(pkg) + 1:].split(".")[0])

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                take(alias.name)
        elif isinstance(node, ast.ImportFrom):
            base = {0: "", 1: pkg, 2: parent}.get(node.level)
            if base is None:                          # `...x` and deeper: never in this package
                continue
            root = ".".join(p for p in (base, node.module) if p)
            names = {a.name for a in node.names}
            if not (root == pkg and names <= siblings):
                take(root)                            # a SYMBOL off the root is the cycle
            for alias in node.names:                  # `from . import base, values`
                take(f"{root}.{alias.name}" if root else alias.name)
    return out


def _upward_edges(pkg_dir: Path, order: Sequence[str]) -> list[str]:
    """Every import that points at a layer ranked at or above the importer's own."""
    rank = {name: i for i, name in enumerate(order)}
    offenders: list[str] = []
    for path in sorted(pkg_dir.glob("*.py")):
        me = path.stem
        if me not in rank:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        siblings = frozenset(order)
        for target in sorted(_sibling_imports(tree, f"uedcli.{pkg_dir.name}", siblings)):
            if target in rank and rank[target] >= rank[me]:
                offenders.append(f"{pkg_dir.name}/{path.name} imports .{target}")
    return offenders


@pytest.mark.parametrize("pkg_name", sorted(LAYERS))
def test_the_rank_table_names_every_module(pkg_name: str) -> None:
    """Every module in the package is ranked. An unranked one is silently unchecked — a rename
    would otherwise drop a whole layer out of the gate with the suite still green."""
    pkg_dir = PKG / pkg_name
    if not pkg_dir.is_dir():
        pytest.skip(f"{pkg_name} is not a package yet")
    found = {p.stem for p in pkg_dir.glob("*.py")}
    assert found == set(LAYERS[pkg_name]), (
        f"uedcli/{pkg_name}/ and the rank table disagree: "
        f"unranked {sorted(found - set(LAYERS[pkg_name]))}, "
        f"missing {sorted(set(LAYERS[pkg_name]) - found)}")
    # A SUBPACKAGE is invisible to `*.py`, so it would be neither ranked nor checked — the gate
    # would stay green over a whole unchecked subtree. These packages are flat by design; if that
    # ever changes, the rank model has to change with it rather than silently stop covering.
    subpackages = sorted(d.name for d in pkg_dir.iterdir()
                         if d.is_dir() and any(d.glob("*.py")))   # namespace packages too
    assert not subpackages, (
        f"uedcli/{pkg_name}/ gained subpackage(s) {subpackages}; the layer model is flat and the "
        f"gate only walks *.py, so these would be unchecked")


@pytest.mark.parametrize("pkg_name", sorted(LAYERS))
def test_no_module_imports_a_later_layer(pkg_name: str) -> None:
    pkg_dir = PKG / pkg_name
    if not pkg_dir.is_dir():
        pytest.skip(f"{pkg_name} is not a package yet")
    offenders = _upward_edges(pkg_dir, LAYERS[pkg_name])
    assert not offenders, (
        f"these imports point up the layer order {' < '.join(LAYERS[pkg_name])}: "
        f"{', '.join(offenders)}")


# --- the gate's own regression ------------------------------------------------------------

def _fixture_package(tmp_path: Path, files: dict[str, str]) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    pkg_dir = tmp_path / "uprops"                     # a name the rank table DOES carry
    pkg_dir.mkdir()
    for name, body in files.items():
        (pkg_dir / name).write_text(body, encoding="utf-8")
    return pkg_dir


def test_the_layering_gate_reports_an_upward_edge(tmp_path: Path) -> None:
    pkg_dir = _fixture_package(tmp_path, {
        "base.py": "def f():\n    from .values import CLI_STYLE\n    return CLI_STYLE\n",
        "values.py": "CLI_STYLE = 1\n",
    })
    assert _upward_edges(pkg_dir, LAYERS["uprops"]) == ["uprops/base.py imports .values"]


def test_the_layering_gate_reports_an_absolute_upward_edge(tmp_path: Path) -> None:
    """The same edge written absolutely is still an edge — both spellings reach `.values`."""
    pkg_dir = _fixture_package(tmp_path, {
        "base.py": "from uedcli.uprops.values import CLI_STYLE\n",
        "values.py": "CLI_STYLE = 1\n",
    })
    assert _upward_edges(pkg_dir, LAYERS["uprops"]) == ["uprops/base.py imports .values"]

    pkg_dir2 = _fixture_package(tmp_path / "b", {
        "base.py": "import uedcli.uprops.values\n",
        "values.py": "CLI_STYLE = 1\n",
    })
    assert _upward_edges(pkg_dir2, LAYERS["uprops"]) == ["uprops/base.py imports .values"]


def test_the_layering_gate_reports_a_submodule_reaching_back_through_the_root(
        tmp_path: Path) -> None:
    """The partially-initialised-package cycle `spec.md` warns about: a submodule importing its own
    package root. `__init__` is ranked last precisely so this reads as an upward edge."""
    for i, body in enumerate(("from uedcli.uprops import Prop\n", "from uedcli import uprops\n")):
        pkg_dir = _fixture_package(tmp_path / str(i), {
            "base.py": "Prop = 1\n",
            "values.py": body,
        })
        assert _upward_edges(pkg_dir, LAYERS["uprops"]) == [
            "uprops/values.py imports .__init__"], f"missed the root edge in {body!r}"


def test_the_layering_gate_reports_a_parent_relative_sibling_edge(tmp_path: Path) -> None:
    """`..uprops.values` names the same module as `.values` — the depth rewrite slice 2 requires
    (`.upackage` -> `..upackage`) makes this exact spelling a live reflex."""
    pkg_dir = _fixture_package(tmp_path, {
        "base.py": "from ..uprops.values import CLI_STYLE\n",
        "values.py": "CLI_STYLE = 1\n",
    })
    assert _upward_edges(pkg_dir, LAYERS["uprops"]) == ["uprops/base.py imports .values"]


def test_the_layering_gate_passes_a_downward_edge_and_an_out_of_package_one(
        tmp_path: Path) -> None:
    """A green run must be reachable, and out-of-package imports must not read as in-package edges.

    `..values` inside `base.py` is the discriminating case: its last component is a ranked layer
    name, but it resolves to `uedcli.values`, outside the package. It sits in the LOWEST-ranked
    module on purpose — a gate that matched basenames, or resolved level 2 against the package
    instead of its parent, would read it as `base -> values`, an upward edge, and go red. Put the
    same import in a high-ranked module and the mis-resolution lands as a legal downward edge, so
    the control could never fail.
    """
    pkg_dir = _fixture_package(tmp_path, {
        "base.py": "from ..upackage import Package\nfrom ..values import Unrelated\n",
        "values.py": "from .base import Prop\nfrom ..upackage import SchemaError\n",
    })
    assert _upward_edges(pkg_dir, LAYERS["uprops"]) == []


def test_the_layering_gate_reports_a_symbol_imported_off_the_package_root(tmp_path: Path) -> None:
    """`from . import Prop` is the spelling `spec.md` names as the cycle, and the one an implementer
    under cycle pressure actually types. Every OTHER spelling of it was caught for three revisions
    while this one was not, which is why it has its own control."""
    for i, body in enumerate(("from . import Prop\n",
                              "from . import base, Prop\n",
                              "def f():\n    from . import Prop\n")):
        pkg_dir = _fixture_package(tmp_path / f"sym{i}", {
            "base.py": "Prop = 1\n",
            "values.py": body,
        })
        assert _upward_edges(pkg_dir, LAYERS["uprops"]) == [
            "uprops/values.py imports .__init__"], f"missed the cycle in {body!r}"


def test_the_layering_gate_allows_a_submodule_imported_off_the_package_root(
        tmp_path: Path) -> None:
    """`from uedcli.uprops import base` binds no root attribute — at runtime it is `from . import
    base`, a legal downward edge. Only a SYMBOL off the root is the partially-initialised cycle."""
    for i, body in enumerate(("from uedcli.uprops import base\n", "from ..uprops import base\n",
                              "from . import base\n")):
        pkg_dir = _fixture_package(tmp_path / f"ok{i}", {
            "base.py": "Prop = 1\n",
            "values.py": body,
        })
        assert _upward_edges(pkg_dir, LAYERS["uprops"]) == []
