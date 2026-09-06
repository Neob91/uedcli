#!/usr/bin/env python3
"""The lockstep-ladder RUNNER: walk N=1..NX for one or more levels, bail at the first non-parity N.

Replaces the earlier practice of a subagent driving `actor_parity.py`/`parity_gate.py` by hand, one N
at a time, in a loop. One invocation re-verifies (or extends) the whole ladder for any number of
levels and stops each level's walk at its first failing N -- the exact thing "does the corpus still
hold N=1..NX" needs.

Per level, per N (ascending from `--from`, default 1, to `--to`, default the level's actor count):
  - native  is ALWAYS rebuilt (`actor_parity.build_native`) -- cheap, and the whole point of a
    re-verification run is that native's binary may have changed.
  - ref (the UED22 editor build) is REUSED from `_scratch/actor-parity/<level>/ref_N<n>.dx` if it
    already exists; pass `--force-ref` to rebuild it (the editor build is the slow half).
  - the pair is scored with `parity_gate.gate()` (the ONE canonical gate; see NATIVE-MATERIALIZE.md).
  - the native build + its subset scaffold dir are DELETED right after gating, every N, pass or fail
    -- they are cheap to regenerate and a long walk must not accumulate disk. The ref is KEPT (the
    expensive half) for reuse by a later run; pass `--keep-native` to keep native.dx too (debugging).
  - on FAIL: print the failure, STOP walking this level (do not build N+1..), move to the next level.
  - on PASS: continue to N+1.

Usage (venv python):
  ladder_run.py --dx <shipped.dx> [--dx <shipped2.dx> ...] [--from N] [--to N] [--force-ref]
                [--timeout SECONDS] [--json out.json]

Exit code: 0 iff EVERY level reached its `--to` (or full actor count) with all N PASSing;
1 if any level bailed early. Prints a per-level running log plus a final one-line-per-level summary.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import actor_parity as ap    # noqa: E402
import parity_gate as pg     # noqa: E402
from uedcli import trunk     # noqa: E402


@dataclass
class LevelResult:
    name: str
    dx: str
    last_pass_n: int = 0     # highest N that PASSed (0 = none, not even N=1)
    bailed_at: int | None = None
    fail_reason: str | None = None
    total_actors: int = 0
    target_n: int = 0


def run_level(dx_path: Path, *, game: str, start: int, stop: int | None,
              force_ref: bool, timeout: float, keep_native: bool) -> LevelResult:
    full_trunk, name = ap._resolve_trunk(dx_path, game)
    total = len(trunk.read_level(full_trunk)[0].order)
    target = min(stop, total) if stop else total
    res = LevelResult(name=name, dx=str(dx_path), total_actors=total, target_n=target)

    for n in range(max(1, start), target + 1):
        subset = ap.make_subset(full_trunk, name, n)
        native = ap.build_native(subset, name, n)
        ref = ap.ref_path(name, n)
        if force_ref or not ap.ref_is_reusable(name, n):
            ref = ap.build_ref(subset, name, n, timeout=timeout)
        ok, fails = pg.gate(str(native), str(ref))
        if ok:
            print(f"[{name}] N={n}/{target}: PASS", flush=True)
            res.last_pass_n = n
        else:
            print(f"[{name}] N={n}/{target}: FAIL -- {fails[0] if fails else '<no detail>'}",
                  flush=True)
            res.bailed_at = n
            res.fail_reason = fails[0] if fails else "<no detail>"
        # Cheap to rebuild, expensive to accumulate: drop native's build + subset scaffold every N,
        # pass or fail. The ref stays cached (it's the slow half) for reuse by a later run.
        if not keep_native:
            native.unlink(missing_ok=True)
        shutil.rmtree(subset.parent.parent, ignore_errors=True)   # <scratch>/<level>/N<n>/
        if res.bailed_at is not None:
            break
    return res


def main() -> int:
    ap_ = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                  formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap_.add_argument("--dx", action="append", required=True, dest="dxs",
                     help="a shipped .dx to re-verify; repeat for multiple levels")
    ap_.add_argument("--game", default="deusex")
    ap_.add_argument("--from", type=int, default=1, dest="start",
                     help="first N to check (default 1)")
    ap_.add_argument("--to", type=int, default=None, dest="stop",
                     help="last N to check (default: the level's full actor count)")
    ap_.add_argument("--force-ref", action="store_true",
                     help="rebuild the editor reference even if cached (slow; default reuses it)")
    ap_.add_argument("--keep-native", action="store_true",
                     help="keep each N's native .dx after gating instead of deleting it (debugging)")
    ap_.add_argument("--timeout", type=float, default=3600.0, help="editor ref-build timeout, seconds")
    ap_.add_argument("--json", help="write the summary as JSON to this path")
    args = ap_.parse_args()

    results: list[LevelResult] = []
    for dx in args.dxs:
        results.append(run_level(Path(dx).resolve(), game=args.game, start=args.start,
                                  stop=args.stop, force_ref=args.force_ref, timeout=args.timeout,
                                  keep_native=args.keep_native))

    print("\n=== ladder summary ===")
    all_ok = True
    for r in results:
        if r.bailed_at is None:
            print(f"  {r.name}: PASS N={args.start}..{r.target_n} (of {r.total_actors} actors)")
        else:
            all_ok = False
            print(f"  {r.name}: FAIL at N={r.bailed_at} -- {r.fail_reason}")

    if args.json:
        Path(args.json).write_text(json.dumps([vars(r) for r in results], indent=2))

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
