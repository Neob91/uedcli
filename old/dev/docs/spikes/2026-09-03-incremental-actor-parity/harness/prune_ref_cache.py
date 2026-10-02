#!/usr/bin/env python3
"""Cap the cached-editor-ref cache (`_scratch/actor-parity/<level>/ref_N*.dx`) at a total size budget.

`ladder_run.py` deliberately never deletes a ref -- reuse is the whole point, and a re-verification
sweep after a core-algorithm change replays every cached N far cheaper than rebuilding it. But a ref
is kept FOREVER by design, and a level's actor count can be in the thousands (Island has 3653), so
the cache grows unboundedly as the ladder climbs. This script evicts the OLDEST refs (by mtime, a
ref file is never touched after creation so mtime == "how long ago this N was last (re)built") once
the total cache size crosses a budget -- LRU by creation time, not by N, since a re-verification sweep
from N=1 touches low Ns just as much as a fresh push touches high ones.

The single HIGHEST-N ref per level is always kept regardless of budget (it's the one a forward push
resumes from, so evicting it forces an immediate rebuild on the very next run).

Usage:
    prune_ref_cache.py [--root _scratch/actor-parity] [--max-mb 500] [--dry-run]
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

REF_RE = re.compile(r"^ref_N(\d+)\.dx$")


def find_refs(root: Path) -> list[tuple[Path, int, float, int]]:
    """Return (path, size, mtime, N) for every cached ref under root, across all levels."""
    out = []
    for level_dir in root.iterdir() if root.is_dir() else []:
        if not level_dir.is_dir():
            continue
        for f in level_dir.glob("ref_N*.dx"):
            m = REF_RE.match(f.name)
            if not m:
                continue
            st = f.stat()
            out.append((f, st.st_size, st.st_mtime, int(m.group(1))))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path,
                     default=Path(__file__).resolve().parents[5] / "_scratch" / "actor-parity")
    ap.add_argument("--max-mb", type=float, default=500.0,
                     help="total cache budget in MB (default 500)")
    ap.add_argument("--dry-run", action="store_true", help="report what would be evicted, don't delete")
    args = ap.parse_args()

    refs = find_refs(args.root)
    if not refs:
        print(f"no cached refs found under {args.root}")
        return 0

    total = sum(r[1] for r in refs)
    budget = int(args.max_mb * 1024 * 1024)
    print(f"cache: {len(refs)} refs, {total / 1e6:.1f} MB (budget {args.max_mb:.0f} MB)")
    if total <= budget:
        print("under budget, nothing to evict")
        return 0

    # keep the single highest-N ref per level unconditionally
    highest_per_level: dict[Path, Path] = {}
    for path, _size, _mtime, n in refs:
        level_dir = path.parent
        cur = highest_per_level.get(level_dir)
        if cur is None or n > int(REF_RE.match(cur.name).group(1)):
            highest_per_level[level_dir] = path
    protected = set(highest_per_level.values())

    # evict oldest-mtime first among the unprotected set until under budget
    evictable = sorted((r for r in refs if r[0] not in protected), key=lambda r: r[2])
    freed = 0
    evicted = 0
    for path, size, _mtime, _n in evictable:
        if total - freed <= budget:
            break
        if args.dry_run:
            print(f"would evict {path} ({size / 1e6:.1f} MB)")
        else:
            path.unlink()
        freed += size
        evicted += 1

    verb = "would evict" if args.dry_run else "evicted"
    print(f"{verb} {evicted} refs, {freed / 1e6:.1f} MB "
          f"(kept {len(protected)} highest-N refs, {len(refs) - evicted} refs remain)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
