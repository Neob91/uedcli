"""Full-corpus offline A/B: native geometry counts (nodes/surfs/leaves/verts) for
UEDCLI_BSPCSG_RING_NEAR, UEDCLI_BSPCSG_MERGE_NEIGHBOR_SAME, and both together, vs the OFF baseline,
against every cached golden in /tmp/uedcli-parity-cache (status "complete" only).

No editor -- builds native in-process against the cached parity trunk, reads golden node/surf/leaf/
verts/points/vectors counts from the cached golden .dx. Adapted from
dev/docs/spikes/2026-09-02-csg-pipeline-breadth-decompile/harness/measure_flag.py (same WORKER
subprocess trick, generalized to 3 configs and the full cached-golden set instead of a fixed 11-level
subset). See dev/docs/native-materialize-findings.md "INDEPENDENT PASS -- full-breadth decompile" for
the single-level (Vandenberg) finding this round measures across the whole corpus.

Each (level, config) pair runs in its own subprocess so the env flag takes effect (read at Rust build
time -- no, at CALL time via std::env::var, but re-reading per-process keeps this identical in
structure to measure_flag.py and avoids any caching surprise from a shared native import).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path("/workspace/uedcli/.claude/worktrees/ring-threshold-corpus-measurement")
PARITY_HARNESS = ROOT / "dev/docs/spikes/2026-08-31-native-parity-report/harness"
CACHE = Path("/tmp/uedcli-parity-cache")
PY = str(ROOT / ".venv/bin/python")

CONFIGS = {
    "OFF": [],
    "RING_NEAR": ["UEDCLI_BSPCSG_RING_NEAR"],
    "MERGE_NEIGHBOR_SAME": ["UEDCLI_BSPCSG_MERGE_NEIGHBOR_SAME"],
    "BOTH": ["UEDCLI_BSPCSG_RING_NEAR", "UEDCLI_BSPCSG_MERGE_NEIGHBOR_SAME"],
}

WORKER = r'''
import sys, json
from pathlib import Path
ROOT = Path("%s")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, "%s")
import parity_pipeline as pp
import parity_compare as pc
dx_path = Path(sys.argv[1])
layout, level_name, trunk_dir, cache_hit = pp.ensure_golden(dx_path, cache_root=Path("/tmp/uedcli-parity-cache"))
g = pc.compare_geometry(trunk_dir, layout.golden)
out = {}
for f in ("nodes","surfs","leaves","verts","points","vectors"):
    out[f] = [getattr(g.native, f), getattr(g.golden, f)]
print("RESULT " + json.dumps(out))
''' % (ROOT, PARITY_HARNESS)


def all_complete_levels() -> list[tuple[str, Path]]:
    """(level_name, source_dx) for every cache entry with status "complete"."""
    out = []
    for m in sorted(CACHE.glob("*/meta.json")):
        d = json.load(open(m))
        if d.get("status") != "complete":
            continue
        p = Path(d.get("source_dx", ""))
        if not p.is_file():
            continue
        out.append((d["level_name"], p))
    return out


def _run_once(dx: Path, flags: list[str]) -> dict | str:
    env = dict(os.environ)
    for fl in CONFIGS["BOTH"]:
        env.pop(fl, None)
    for fl in flags:
        env[fl] = "1"
    p = subprocess.run([PY, "-c", WORKER, str(dx)],
                        env=env, capture_output=True, text=True, timeout=1800)
    for line in p.stdout.splitlines():
        if line.startswith("RESULT "):
            return json.loads(line[7:])
    return f"FAIL rc={p.returncode}: {(p.stderr.strip()[-500:] or p.stdout.strip()[-300:])}"


def run(dx: Path, flags: list[str]) -> dict | str:
    """Retry once on failure -- this host runs many concurrent agent worktrees and transient
    resource contention (e.g. EMFILE from a co-running process) has been observed to fail a single
    subprocess call spuriously; a clean retry after a short pause distinguishes that from a real
    pipeline error."""
    r = _run_once(dx, flags)
    if isinstance(r, dict):
        return r
    import time
    time.sleep(5)
    return _run_once(dx, flags)


def main():
    sel = sys.argv[1:]
    levels = all_complete_levels()
    if sel:
        levels = [(n, p) for n, p in levels if n in sel]

    results: dict[str, dict[str, dict | str]] = {}
    for level, dx in levels:
        print(f"=== {level} ===", file=sys.stderr)
        results[level] = {}
        for cfg, flags in CONFIGS.items():
            r = run(dx, flags)
            results[level][cfg] = r
            print(f"  {cfg}: {'OK' if isinstance(r, dict) else r}", file=sys.stderr)

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
