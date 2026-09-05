"""Where things are: the code root (this checkout, possibly a worktree) and the asset root (the main
checkout, which owns the gitignored `dev/games/` and is where `uned/UED22/` binaries are read from)."""
from __future__ import annotations

import subprocess
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[5]


def _asset_root() -> Path:
    common = subprocess.run(["git", "-C", str(CODE_ROOT), "rev-parse", "--git-common-dir"],
                            capture_output=True, text=True, check=True).stdout.strip()
    return (CODE_ROOT / common).resolve().parent


ASSET_ROOT = _asset_root()
UED22 = ASSET_ROOT / "uned/UED22"
GAME = ASSET_ROOT / "dev/games/deusex"
