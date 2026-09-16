#!/usr/bin/env python3
"""Sparse regression spot-check: verify AT MOST 10 evenly-spaced N's across a range, never a full
sequential sweep (owner ruling, 2026-09-15 -- a full N=1..NX re-verify is prohibitively expensive
after a core change; a spread sample is the standing re-verification method, not `ladder_run.py`'s
exhaustive walk). Reuses the exact same build/gate primitives as `ladder_run.py`/`actor_parity.py` --
only the N-selection differs.

Usage (venv python):
  spot_check.py --dx <shipped.dx> --to N [--from N] [--count 10]

Always includes both endpoints. Reuses a cached ref (`ap.ref_is_reusable`) where one already exists;
builds fresh only where missing. Exit 0 iff every checked N passes.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import actor_parity as ap   # noqa: E402
import parity_gate as pg    # noqa: E402


def spaced_points(lo: int, hi: int, count: int) -> list[int]:
    """Up to `count` evenly-spaced ints in [lo, hi], endpoints always included."""
    if hi <= lo:
        return [hi]
    if hi - lo + 1 <= count:
        return list(range(lo, hi + 1))
    step = (hi - lo) / (count - 1)
    return sorted({round(lo + i * step) for i in range(count)})


def main() -> int:
    ap_ = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                  formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap_.add_argument("--dx", required=True, help="the shipped .dx to check against")
    ap_.add_argument("--from", type=int, default=1, dest="start")
    ap_.add_argument("--to", type=int, required=True, dest="stop")
    ap_.add_argument("--count", type=int, default=10, help="max N's to check (default 10)")
    ap_.add_argument("--game", default="deusex")
    ap_.add_argument("--timeout", type=float, default=3600.0)
    args = ap_.parse_args()

    dx_path = Path(args.dx).resolve()
    full_trunk, name = ap._resolve_trunk(dx_path, args.game)
    points = spaced_points(args.start, args.stop, args.count)
    print(f"[{name}] spot-checking {len(points)} of {args.stop - args.start + 1} N's: {points}",
          flush=True)

    all_ok = True
    for n in points:
        subset = ap.make_subset(full_trunk, name, n)
        native = ap.build_native(subset, name, n)
        ref = ap.ref_path(name, n)
        if not ap.ref_is_reusable(name, n):
            ref = ap.build_ref(subset, name, n, timeout=args.timeout)
        ok, fails = pg.gate(str(native), str(ref))
        native.unlink(missing_ok=True)
        shutil.rmtree(subset.parent.parent, ignore_errors=True)
        status = "PASS" if ok else f"FAIL -- {fails[0] if fails else '<no detail>'}"
        print(f"  N={n}: {status}", flush=True)
        all_ok = all_ok and ok

    print("ALL PASS" if all_ok else "SOME FAILED", flush=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
