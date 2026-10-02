#!/usr/bin/env python3
"""Targeted probe (not a full binary search) around Training Final's STATIC per-brush attribution
lead (world-CSG idx 660-668, `Brush907`/`909`/`911`/`915`) -- checks whether the FIRST live
divergence actually falls in that window before spending a full log2(764) binary search's worth of
editor builds. Each `editor_counts` call retries once on a `RuntimeError`/`TimeoutError` (the editor
wedges/GC-dialog-stalls probabilistically per `unrealed/quirks.md` "Stability" -- confirmed twice
live this session on the trivial n=1 build, unrelated to level content) before giving up on that n.
Usage: tf_probe.py N [N ...]  -- prints compare(n) for each N given, in order.
"""
import sys
import time
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[5]
assert (WORKTREE / "uedcli").is_dir(), f"unexpected WORKTREE resolution: {WORKTREE}"
sys.path.insert(0, str(WORKTREE))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-09-01-fc08-nsfhq04-csgactive/harness"))

import prefix_search_lib as psl  # noqa: E402
psl.ROOT = Path("/workspace/uedcli")
psl.WORKTREE = WORKTREE
psl.BUILD_SCRIPT = WORKTREE / "dev/docs/spikes/2026-07-15-native-materialize/harness/build_ued_golden.py"
psl.PYEXE = str(WORKTREE / ".venv/bin/python")

SRC_TRUNK = WORKTREE / "_scratch/tf_trunk_src/trunk/maps/00_trainingfinal"
PREFIX_ROOT = WORKTREE / "_scratch/tf_prefix"
PROJECT_ENV = SRC_TRUNK.parent.parent


def compare_with_retry(ps, n, attempts=2):
    for i in range(attempts):
        try:
            return ps.compare(n)
        except (RuntimeError, TimeoutError) as e:
            print(f"  [n={n}] attempt {i+1}/{attempts} FAILED: {e}", flush=True)
            if i + 1 == attempts:
                raise
            time.sleep(5)


if __name__ == "__main__":
    ns = [int(a) for a in sys.argv[1:]]
    ps = psl.PrefixSearch("00_trainingfinal", SRC_TRUNK, PREFIX_ROOT, PROJECT_ENV)
    for n in ns:
        compare_with_retry(ps, n)
