#!/usr/bin/env python3
"""00_trainingfinal prefix binary search (first diverging brush, native vs live editor).

Same shape as `pu_prefix_search.py`. The 2026-09-02 attempt (see
`native-materialize-findings.md`) was blocked by the GC-dialog `_wait_idle` gap, since fixed;
static lead: `Brush907`/`909`/`911`/`915`, world-CSG idx 660-668. `baseline` compares native(full)
against the cached lit golden offline; numeric args are targeted `compare(n)` probes.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import prefix_search_lib as PSL  # noqa: E402

CACHE = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-check/_scratch/uedcli-parity-cache"
             "/f3e6539d9ed950dcf1dfb5929040e2da07b37f263727c360fdf2de63e2e73d27/trunk")
GOLDEN = Path("/tmp/uedcli-parity-cache"
              "/f3e6539d9ed950dcf1dfb5929040e2da07b37f263727c360fdf2de63e2e73d27/golden.dx")


def main():
    wt = HERE.parents[4]  # <slug>/spikes/docs/dev -> worktree root
    ps = PSL.PrefixSearch(
        "00_trainingfinal",
        CACHE / "maps/00_trainingfinal",
        wt / "_scratch/tf-prefix",
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
