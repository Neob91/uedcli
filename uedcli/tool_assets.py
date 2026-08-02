"""Tool-INSTALL asset anchors (direction/projects-and-config.md 2026-07-17 20:58 §6).

The uedcli *installation* owns assets that belong to no project: the docker-compose dir + the
committed UED22 editor substrate (`Tools/uedcli/uned/`) and the umodel mesh extractor
(`Tools/umodel_win32/`). They resolve **package-relative** — from this installed `uedcli`
package's own location (`__file__`), never from a repo/project root, an env var, or a
CLAUDE.md-marker walk-up (all retired with `repo_paths.py`). Zero config for the dev checkout;
how these assets ship under a pipx/Nuitka install is the (to-be-respecced) global-CLI packaging
item's problem — including the known `__file__`-inside-a-onefile caveat, accepted there.
"""
from __future__ import annotations

from pathlib import Path


def tool_root() -> Path:
    """The tool's source root `Tools/uedcli/` — the dir HOLDING the `uedcli` package
    (`…/uedcli/tool_assets.py` → two levels up)."""
    return Path(__file__).resolve().parent.parent


def uned_dir() -> Path:
    """`<tool_root>/uned/` — the docker-compose dir: docker-compose.yml, the committed UED22
    substrate (`uned/UED22/`, incl. the pre-bake `UnrealEd.ini`/`unrealtournament.ini`), and the
    gitignored user-supplied `DeusExAssets/` install."""
    return tool_root() / "uned"


def umodel_dir() -> Path:
    """`Tools/umodel_win32/` — umodel is a SIBLING of the tool dir, i.e. it deliberately escapes
    the package-relative anchor (one level above `tool_root()`); the packaging item inherits this
    explicitly (plan 2026-07-18 slice 3)."""
    return tool_root().parent / "umodel_win32"
