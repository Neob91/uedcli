#!/usr/bin/env python3
"""Prefix binary search to localize Area51 Entrance's +85 node / +51 leaf residual (surfs exact
d=+0) to a first-diverging brush -- same methodology as fc08_prefix_search.py/
nsfhq04_prefix_search.py (`dev/docs/spikes/2026-09-01-fc08-nsfhq04-csgactive/harness/
prefix_search_lib.py`), adapted to this worktree.
"""
import os
import sys
from pathlib import Path

WORKTREE = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-fresh")
sys.path.insert(0, str(WORKTREE))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-09-01-fc08-nsfhq04-csgactive/harness"))

# Patch prefix_search_lib's hardcoded WORKTREE/paths before importing PrefixSearch.
import prefix_search_lib as psl  # noqa: E402
psl.ROOT = Path("/workspace/uedcli")
psl.WORKTREE = WORKTREE
psl.BUILD_SCRIPT = WORKTREE / "dev/docs/spikes/2026-07-15-native-materialize/harness/build_ued_golden.py"
psl.PYEXE = str(WORKTREE / ".venv/bin/python")

SRC_TRUNK = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-check/_scratch/uedcli-parity-cache/"
                  "65b9261c371bdf8573cb7bf9128a3f6664b14d2ac360ef6fbfd4a0d292986ece/trunk/maps/15_area51_entrance")
PREFIX_ROOT = WORKTREE / "_scratch/a51_prefix"
PROJECT_ENV = SRC_TRUNK.parent.parent

if __name__ == "__main__":
    ps = psl.PrefixSearch("15_area51_entrance", SRC_TRUNK, PREFIX_ROOT, PROJECT_ENV)
    ps.binary_search()
