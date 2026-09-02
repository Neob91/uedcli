#!/usr/bin/env python3
"""Prefix binary search to localize 00_TrainingFinal.dx's +105 node / +13 leaf residual (surfs
exact d=+0) to a first-diverging brush -- same methodology as fc08_prefix_search.py/
nsfhq04_prefix_search.py/area51_prefix_search.py (`dev/docs/spikes/2026-09-01-fc08-nsfhq04-csgactive/
harness/prefix_search_lib.py`), adapted to THIS worktree (fresh off master, own editor-driven
goldens, per the standing no-cross-worktree-reuse rule -- see `native-materialize-findings.md`
"DISPROVEN -- live gdb trace shows its own classify-BSP descent is byte-exact").
"""
import sys
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[5]  # repo root of THIS worktree
assert (WORKTREE / "uedcli").is_dir(), f"unexpected WORKTREE resolution: {WORKTREE}"
sys.path.insert(0, str(WORKTREE))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-09-01-fc08-nsfhq04-csgactive/harness"))

# Patch prefix_search_lib's hardcoded WORKTREE/paths before importing PrefixSearch -- same pattern
# as area51_prefix_search.py, pointed at THIS worktree instead.
import prefix_search_lib as psl  # noqa: E402
psl.ROOT = Path("/workspace/uedcli")
psl.WORKTREE = WORKTREE
psl.BUILD_SCRIPT = WORKTREE / "dev/docs/spikes/2026-07-15-native-materialize/harness/build_ued_golden.py"
psl.PYEXE = str(WORKTREE / ".venv/bin/python")

SRC_TRUNK = WORKTREE / "_scratch/tf_trunk_src/trunk/maps/00_trainingfinal"
PREFIX_ROOT = WORKTREE / "_scratch/tf_prefix"
PROJECT_ENV = SRC_TRUNK.parent.parent

if __name__ == "__main__":
    ps = psl.PrefixSearch("00_trainingfinal", SRC_TRUNK, PREFIX_ROOT, PROJECT_ENV)
    ps.binary_search()
