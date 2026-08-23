"""Import-layering gate for the split packages `uedcli/uprops/` and `uedcli/propedit/`.

Each package is a stack of layers: a module may import a layer BELOW it, never one above. The
rank tables below are the layer order; `__init__` ranks last in both because it is pure
re-export and therefore imports from every sibling.

Two things this walks that a naive scan would miss:

- **Function bodies, not just module scope** (`ast.walk`, not `tree.body`). A lazy in-function
  import is exactly the reflex a cycle invites, and the spec forbids it as an escape hatch.
  `test_import_boundary.py` walks the same way for the same reason.
- **Only single-dot imports are in-package.** `from ..upackage import Package` leaves the
  package and is always legal; counting it as an in-package edge would red-flag correct code.

`test_the_layering_gate_reports_an_upward_edge` is the negative control: the gate below is
green-by-skip until the packages exist, and a check nobody has watched fail is a check nobody
knows works.
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


def _sibling_imports(tree: ast.AST) -> set[str]:
    """Every in-package sibling module a tree imports, anywhere in it (function bodies included).

    Only `level == 1` counts: inside `uedcli/uprops/x.py` AND inside `uedcli/uprops/__init__.py`,
    a single dot anchors on `uedcli.uprops`, so the two cases need no special-casing.
    """
    out: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.level != 1:
            continue
        if node.module:
            out.add(node.module.split(".")[0])        # `from .base import X`
        else:
            out.update(a.name for a in node.names)    # `from . import base, values`
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
        for target in sorted(_sibling_imports(tree)):
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


def test_the_layering_gate_passes_a_downward_edge_and_an_out_of_package_one(
        tmp_path: Path) -> None:
    """A green run must be reachable, and `..upackage` must not read as an in-package edge."""
    pkg_dir = _fixture_package(tmp_path, {
        "base.py": "from ..upackage import Package\n",
        "values.py": "from .base import Prop\nfrom ..upackage import SchemaError\n",
    })
    assert _upward_edges(pkg_dir, LAYERS["uprops"]) == []
