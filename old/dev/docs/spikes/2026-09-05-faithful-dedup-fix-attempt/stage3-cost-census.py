#!/usr/bin/env python3
"""Stage 3 COST CENSUS — how much does the pruned-descent dedup regress across the ladder?

For each cell, build native BOTH ways (UEDCLI_BSPCSG_FNV_DEDUP off=linear scan / on=surf-base descent)
and gate each against its cached editor ref with the tie-mask DISABLED (`gate_nomask.py`). A cell
REGRESSES if it PASSES descent-off but FAILS descent-on — the descent exposing a native/editor
incremental-tree difference the linear scan hid (like N8's Z=240). The count of regressing cells, and
the count of DISTINCT offending faces across them, bounds the remaining faithful-fix work.

Descent stays DEFAULT OFF in the shipped build; this script flips it per subprocess only.
Run: `python3 stage3-cost-census.py`  (writes results to stdout + census_results.txt in this dir).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # <root>/dev/docs/spikes/<slug>/this.py
AP = ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/actor_parity.py"
GATE = ROOT / "dev/docs/spikes/2026-09-05-faithful-dedup-fix-attempt/harness/gate_nomask.py"
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


def build(dx: str, n: int, on: bool) -> bool:
    env = dict(os.environ)
    if on:
        env["UEDCLI_BSPCSG_FNV_DEDUP"] = "1"
    else:
        env.pop("UEDCLI_BSPCSG_FNV_DEDUP", None)
    r = subprocess.run([str(PY), str(AP), "--dx", str(MAPS / dx), "native", str(n)],
                       capture_output=True, text=True, env=env)
    return r.returncode == 0


def gate(nat: Path, ref: Path) -> bool:
    r = subprocess.run([str(PY), str(GATE), str(nat), str(ref)], capture_output=True, text=True)
    return "PARITY: YES" in r.stdout


def main() -> int:
    out = open(Path(__file__).with_name("census_results.txt"), "w")
    def emit(s):
        print(s, flush=True)
        out.write(s + "\n"); out.flush()
    regress, fixed, both_fail, total = [], [], [], 0
    for level, dx, ns in CELLS:
        d = SCRATCH / level
        for n in ns:
            ref = d / f"ref_N{n}.dx"
            if not ref.exists():
                emit(f"{level} N{n}: NO REF (skip)"); continue
            total += 1
            nat = d / f"native_N{n}.dx"
            if not build(dx, n, False):
                emit(f"{level} N{n}: BUILD-OFF FAILED"); continue
            off_nat = d / f"native_N{n}_off.dx"; shutil.copy(nat, off_nat)
            off = gate(off_nat, ref)
            if not build(dx, n, True):
                emit(f"{level} N{n}: BUILD-ON FAILED"); continue
            on_nat = d / f"native_N{n}_on.dx"; shutil.copy(nat, on_nat)
            on = gate(on_nat, ref)
            tag = ""
            if off and not on:
                tag = "  <== REGRESS"; regress.append(f"{level} N{n}")
            elif not off and on:
                tag = "  <== FIX"; fixed.append(f"{level} N{n}")
            elif not off and not on:
                both_fail.append(f"{level} N{n}")
            emit(f"{level} N{n}: off={'PASS' if off else 'FAIL'} on={'PASS' if on else 'FAIL'}{tag}")
    emit("\n=== SUMMARY ===")
    emit(f"cells censused: {total}")
    emit(f"REGRESS (off PASS -> on FAIL): {len(regress)}  {regress}")
    emit(f"FIX (off FAIL -> on PASS): {len(fixed)}  {fixed}")
    emit(f"both FAIL (nomask, pre-existing): {len(both_fail)}  {both_fail}")
    out.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
