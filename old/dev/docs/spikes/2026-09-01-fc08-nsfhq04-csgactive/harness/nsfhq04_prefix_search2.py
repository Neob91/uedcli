#!/usr/bin/env python3
"""Round-2 nsfhq04 prefix-search CLI (post-`528e602` CsgOper::Active fix), over the STRUCTURAL-ONLY
(non-PF_Semisolid) brush set built by `nsfhq04_filter_trunk2.py`. WITHOUT removing Brush8321 (the
CsgOper-absent-first-brush case `528e602` now handles) -- this round is looking for the SECOND,
still-unexplained divergence.

Usage: .venv/bin/python nsfhq04_prefix_search2.py [N ...]   -- build+compare specific prefix sizes
       .venv/bin/python nsfhq04_prefix_search2.py --search   -- binary search 1..N
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prefix_search_lib2 import PrefixSearch  # noqa: E402

WORKTREE = Path(__file__).resolve().parents[5]
SRC_TRUNK = WORKTREE / "_scratch/nsfhq04-structural-only2/maps/nsfhq04"
PREFIX_ROOT = WORKTREE / "_scratch/nsfhq04-prefix2"
PROJECT_ENV = WORKTREE / "_scratch/nsfhq04-structural-only2"


def main():
    ps = PrefixSearch("nsfhq04", SRC_TRUNK, PREFIX_ROOT, PROJECT_ENV)
    args = sys.argv[1:]
    if args and args[0] == "--search":
        ps.binary_search()
        return 0
    ns = [int(a) for a in args] if args else [len(ps.brush_names)]
    for n in ns:
        ps.compare(n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
