#!/usr/bin/env python3
"""Diff the editor's AddBrushToWorldFunc trace tail (n=507 minus n=506 line-count prefix) against
native's own NADD trace tail for Brush1852, to see exactly which fragments the editor classifies
differently (add vs discard) than native for the SAME brush against the SAME (byte-exact at n=506)
world state."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
LOGDIR = ROOT / "_scratch/area51-oracle-logs"

log506 = (LOGDIR / "area51-addfunc-506.log").read_text().splitlines()
log507 = (LOGDIR / "area51-addfunc-507.log").read_text().splitlines()
lines506 = [l for l in log506 if l.startswith("AFUNC")]
lines507 = [l for l in log507 if l.startswith("AFUNC")]
print(f"editor n=506: {len(lines506)} AFUNC calls")
print(f"editor n=507: {len(lines507)} AFUNC calls")
tail = lines507[len(lines506):]
print(f"editor Brush1852 tail: {len(tail)} AFUNC calls")
kept = [l for l in tail if int(l.split("filter=")[1].split()[0]) in (0, 2) or
        (int(l.split("filter=")[1].split()[0]) == 5 and (int(l.split("pf=")[1].split()[0], 16) & 0x20) == 0)]
print(f"editor Brush1852 tail: {len(kept)} of those actually ADDED (rest discarded by filter)")
out = LOGDIR / "area51_brush1852_editor_afunc_tail.log"
out.write_text("\n".join(tail) + "\n")
print("wrote", out)
for l in tail:
    print(l)
