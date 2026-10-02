#!/usr/bin/env python3
"""Offline (no editor, no docker) trace: which brush's incremental CSG step zeros node 5154's
`NumVertices` (marks it dead), using the already-committed `UEDCLI_BSPCSG_BRUSH_STATE=FULL:lo-hi`
diagnostic. Continues the OceanLab N=203 investigation
(`dev/docs/spikes/2026-09-15-oceanlab-n203-bspoptgeom-points/`).

Usage: trace_node_death.py [--node 5154] [--lo 150] [--hi 175]
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ACTOR_PARITY_HARNESS = ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ACTOR_PARITY_HARNESS))

DX_PATH = Path("/workspace/uedcli/dev/games/substrate-deusex/Maps/14_OceanLab_Lab.dx")
N = 203


def main() -> int:
    node = 5154
    lo, hi = 150, 175
    for i, a in enumerate(sys.argv):
        if a == "--node":
            node = int(sys.argv[i + 1])
        elif a == "--lo":
            lo = int(sys.argv[i + 1])
        elif a == "--hi":
            hi = int(sys.argv[i + 1])

    os.environ["UEDCLI_BSPCSG_BRUSH_STATE"] = f"FULL:{lo}-{hi}"
    # Run in a SUBPROCESS: the extension caches env-gated flags read at import/first-call time in
    # some paths, and we want a clean process regardless.
    script = f"""
import sys
from pathlib import Path
sys.path.insert(0, {str(ROOT)!r})
sys.path.insert(0, {str(ACTOR_PARITY_HARNESS)!r})
import actor_parity as ap
subset_full, name = ap._resolve_trunk(Path({str(DX_PATH)!r}), "deusex")
subset = ap.make_subset(subset_full, name, {N})
ap.build_native(subset, name, {N})
"""
    r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                        env=os.environ.copy())
    lines = r.stderr.splitlines()
    print(f"[trace] {len(lines)} stderr lines; filtering for node {node}, k={lo}..{hi}")
    for line in lines:
        if line.startswith("BRUSHSTATE") or (line.startswith(f"P1NODE") and f" i={node} " in line):
            print(line)
    if r.returncode != 0:
        print("---- build FAILED, tail of stderr ----")
        print("\n".join(lines[-40:]))
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
