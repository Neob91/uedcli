"""Shared setup for the Vandenberg Gas first-divergent-brush trace: worktree-local imports
(never the shared main checkout -- see `prefix_search_lib.py`'s contamination warning), the
cached trunk/golden locations, and the level's world-CSG brush list.
"""
import os
import sys
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(WORKTREE))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))

CACHE = Path("/tmp/uedcli-parity-cache/7d06dd6155e5daa7c78e76ed19a66068852973670d1c56dddd9628b2ca393c13")
TRUNK_CACHE = Path("/workspace/uedcli/.claude/worktrees/uedcli-parity-trunk-cache"
                   "/7d06dd6155e5daa7c78e76ed19a66068852973670d1c56dddd9628b2ca393c13/trunk")
GOLDEN_DX = CACHE / "golden.dx"
TRUNK = TRUNK_CACHE / "maps/12_vandenberg_gas"

os.environ.setdefault("UEDCLI_PROJECT", str(TRUNK_CACHE))

from uedcli import trunk as trunk_mod              # noqa: E402
from uedcli.native import brush_marshal as BM      # noqa: E402
from spike_classindex import class_index           # noqa: E402


def world_csg_names():
    """(level, [world-CSG brush actor names] in build order)."""
    level, _ = trunk_mod.read_level(TRUNK)
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    return level, names
