#!/usr/bin/env python3
"""nsfhq04 sibling of `fc08_prefix_search.py`, using the shared `prefix_search_lib.PrefixSearch`.

Usage: .venv/bin/python nsfhq04_prefix_search.py [N ...]   -- build+compare specific prefix sizes
       .venv/bin/python nsfhq04_prefix_search.py --search   -- binary search 1..660
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prefix_search_lib import PrefixSearch  # noqa: E402

ROOT = Path("/workspace/uedcli")
SRC_TRUNK = ROOT / "_scratch/nsfhq04-structural-only/maps/nsfhq04"
PREFIX_ROOT = ROOT / "_scratch/nsfhq04-prefix"
PROJECT_ENV = ROOT / "_scratch/nsfhq04-structural-only"


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
