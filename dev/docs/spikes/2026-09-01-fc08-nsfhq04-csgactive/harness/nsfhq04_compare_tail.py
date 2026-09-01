#!/usr/bin/env python3
"""Diff the editor's AddBrushToWorldFunc trace tail (n=513 minus n=512 line-count prefix) against
native's own LEAF trace for NSFHQ04's `Brush842`, to see exactly which fragments the editor
classifies differently (add vs discard) than native for the SAME brush against the SAME
(byte-exact at n=512) world state. Same technique as Area51's `area51_compare_tail.py`.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
LOGDIR = ROOT / "_scratch/nsfhq04-oracle-logs"

log512 = (LOGDIR / "nsfhq04-addfunc-512.log").read_text().splitlines()
log513 = (LOGDIR / "nsfhq04-addfunc-513.log").read_text().splitlines()
lines512 = [l for l in log512 if l.startswith("AFUNC")]
lines513 = [l for l in log513 if l.startswith("AFUNC")]
print(f"editor n=512: {len(lines512)} AFUNC calls")
print(f"editor n=513: {len(lines513)} AFUNC calls")
tail = lines513[len(lines512):]
print(f"editor Brush842 tail: {len(tail)} AFUNC calls")


def is_kept(line):
    filt = int(line.split("filter=")[1].split()[0])
    pf = int(line.split("pf=")[1].split()[0], 16)
    return filt in (0, 2) or (filt == 5 and (pf & 0x20) == 0)


kept = [l for l in tail if is_kept(l)]
print(f"editor Brush842 tail: {len(kept)} of those actually ADDED (rest discarded by filter)")

out = LOGDIR / "nsfhq04_brush842_editor_afunc_tail.log"
out.write_text("\n".join(tail) + "\n")
print("wrote", out)
for l in tail:
    print(l)

# --- compare against native's own LEAF trace (nsfhq04_native_leaf_dump.py) ---
native_leaf = ROOT / "_scratch/nsfhq04_brush842_native_leaf.log"
if native_leaf.exists():
    nl = native_leaf.read_text().splitlines()
    n_kept = [l for l in nl if l.rstrip().endswith("add=true")]
    n_disc = [l for l in nl if l.rstrip().endswith("add=false")]
    print(f"\nnative LEAF (actor=512): total={len(nl)} kept={len(n_kept)} discarded={len(n_disc)}")
    print(f"editor AFUNC tail (actor=Brush842): total={len(tail)} kept={len(kept)} "
          f"discarded={len(tail) - len(kept)}")
