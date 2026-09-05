#!/usr/bin/env python3
"""Stage 3 VALIDATION — build each ladder cell with the DEFAULT native build (descent on, no env) and
gate with the now-maskless `parity_gate.py` (x=448 tie mask + Brush-Region mask removed). Confirms the
whole corpus is byte-exact WITHOUT any dedup mask.

Run: `python3 stage3-validate.py`  (writes validate_results.txt in this dir).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
AP = ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/actor_parity.py"
GATE = ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/parity_gate.py"
PY = ROOT / ".venv/bin/python"
SCRATCH = ROOT / "_scratch/actor-parity"
MAPS = Path(os.environ.get("UED_DX_DIR", "/workspace/uedcli/dev/games/deusex/Maps"))

CELLS = [
    ("03_nyc_unatcohq", "03_NYC_UNATCOHQ.dx", list(range(1, 25))),
    ("02_nyc_bar", "02_NYC_Bar.dx", list(range(1, 17))),
    ("06_hongkong_wanchai_market", "06_HongKong_WanChai_Market.dx", list(range(1, 17)) + [19]),
    ("01_nyc_unatcoisland", "01_NYC_UNATCOIsland.dx", [8, 12]),
    ("14_oceanlab_lab", "14_OceanLab_Lab.dx", [3]),
]


def main() -> int:
    out = open(Path(__file__).with_name("validate_results.txt"), "w")
    def emit(s):
        print(s, flush=True); out.write(s + "\n"); out.flush()
    npass = nfail = 0
    fails = []
    for level, dx, ns in CELLS:
        d = SCRATCH / level
        for n in ns:
            ref = d / f"ref_N{n}.dx"
            if not ref.exists():
                emit(f"{level} N{n}: NO REF (skip)"); continue
            r = subprocess.run([str(PY), str(AP), "--dx", str(MAPS / dx), "native", str(n)],
                               capture_output=True, text=True)  # DEFAULT: descent on
            if r.returncode != 0:
                emit(f"{level} N{n}: BUILD FAILED"); nfail += 1; fails.append(f"{level} N{n} (build)"); continue
            nat = d / f"native_N{n}.dx"
            g = subprocess.run([str(PY), str(GATE), str(nat), str(ref)], capture_output=True, text=True)
            ok = "PARITY: YES" in g.stdout
            emit(f"{level} N{n}: {'PASS' if ok else 'FAIL'}  (maskless parity_gate)")
            if ok:
                npass += 1
            else:
                nfail += 1; fails.append(f"{level} N{n}")
    emit(f"\n=== {npass} PASS / {nfail} FAIL (maskless) ===")
    if fails:
        emit(f"FAILURES: {fails}")
    out.close()
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
