#!/usr/bin/env python3
"""06_hongkong_wanchai_garage prefix binary search (first diverging brush, native vs live editor).

Same shape as `pu_prefix_search.py` (see its and `prefix_search_lib.py`'s docstrings). Run with no
args for the full binary search; with `baseline` to compare native(full world-CSG set) against the
cached full lit golden offline first; with numbers for targeted `compare(n)` probes.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import prefix_search_lib as PSL  # noqa: E402

CACHE = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-check/_scratch/uedcli-parity-cache"
             "/21326d2b4c841cc3e3e2424699c2f5f07f1b9daa41eefbd4efa00bf9bf30af1e/trunk")
GOLDEN = Path("/tmp/uedcli-parity-cache"
              "/21326d2b4c841cc3e3e2424699c2f5f07f1b9daa41eefbd4efa00bf9bf30af1e/golden.dx")


def main():
    wt = HERE.parents[4]  # <slug>/spikes/docs/dev -> worktree root
    ps = PSL.PrefixSearch(
        "06_hongkong_wanchai_garage",
        CACHE / "maps/06_hongkong_wanchai_garage",
        wt / "_scratch/wg-prefix",
        CACHE,
    )
    args = sys.argv[1:]
    if args == ["baseline"]:
        nm = ps.native_counts(len(ps.brush_names))
        gm = ps._parse_golden(GOLDEN)
        print(f"native full: nodes={len(nm.nodes)} surfs={len(nm.surfs)} leaves={len(nm.leaves)}")
        print(f"cached lit golden: nodes={len(gm.nodes)} surfs={len(gm.surfs)} leaves={len(gm.leaves)}")
        print(f"d_nodes={len(nm.nodes)-len(gm.nodes):+d} d_surfs={len(nm.surfs)-len(gm.surfs):+d} "
              f"d_leaves={len(nm.leaves)-len(gm.leaves):+d}")
    elif args:
        for n in args:
            ps.compare(int(n))
    else:
        ps.binary_search()


if __name__ == "__main__":
    main()
