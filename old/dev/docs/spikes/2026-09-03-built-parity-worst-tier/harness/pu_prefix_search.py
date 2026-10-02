#!/usr/bin/env python3
"""11_paris_underground prefix binary search (first diverging brush, native vs live editor).

Wraps this dir's `prefix_search_lib.py` copy (paths self-resolved to THIS worktree — see the
original's contamination warning). The level's remaining residual is `d_nodes=-108 d_leaves=-4`
(surf-exact) with final-tree node-owner attribution concentrated on the earliest brushes
(`Brush1246` idx 0 — the CsgOper-absent default 256-cube — d=-17; `Brush328` idx 1 d=-15).

Usage: .venv/bin/python pu_prefix_search.py [n ...]   (no args: full binary search)
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import prefix_search_lib as PSL  # noqa: E402

TRUNK = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-check/_scratch/uedcli-parity-cache"
             "/bdf66b5dc02df008a53f5018b5aeab950cf13481c2a49bd0f683dd714429c718/trunk")


def main():
    wt = HERE.parents[4]  # <slug>/spikes/docs/dev -> worktree root
    ps = PSL.PrefixSearch(
        "11_paris_underground",
        TRUNK / "maps/11_paris_underground",
        wt / "_scratch/pu-prefix",
        TRUNK,
    )
    if len(sys.argv) > 1:
        for n in sys.argv[1:]:
            ps.compare(int(n))
    else:
        ps.binary_search()


if __name__ == "__main__":
    main()
