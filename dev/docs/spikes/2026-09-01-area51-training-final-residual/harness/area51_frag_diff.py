#!/usr/bin/env python3
"""Fragment-level diff: native's kept (NADD) fragments for Brush1852 vs the editor's kept (AFUNC,
filter in {0,2} or 5-non-semisolid) fragments for the SAME n=506->507 transition. Match by
(rounded Base, rounded Normal) since node/parent indices use unrelated numbering schemes.

Run area51_native_leaf_dump.py first (produces _scratch/area51_brush1852_native_nadd_v2.log) and
area51_addfunc_oracle.py for n=506 and n=507 + area51_compare_tail.py (produces
_scratch/area51-oracle-logs/area51_brush1852_editor_afunc_tail.log)."""
import re
from collections import Counter
from pathlib import Path

ROOT = Path("/workspace/uedcli/.claude/worktrees/agent-a38a132200c3a063b")


def parse_native(path):
    out = []
    for line in path.read_text().splitlines():
        if not line.startswith("NADD"):
            continue
        n = re.search(r"N=([-\d.]+),([-\d.]+),([-\d.]+)", line)
        b = re.search(r"B=([-\d.]+),([-\d.]+),([-\d.]+)", line)
        out.append((tuple(round(float(x), 2) for x in n.groups()),
                     tuple(round(float(x), 2) for x in b.groups())))
    return out


def parse_editor(path):
    kept, discarded = [], []
    for line in path.read_text().splitlines():
        if not line.startswith("AFUNC"):
            continue
        filt = int(re.search(r"filter=(-?\d+)", line).group(1))
        pf = int(re.search(r"pf=(0x[0-9a-fA-F]+)", line).group(1), 16)
        n = re.search(r"N=([-\d.]+),([-\d.]+),([-\d.]+)", line)
        b = re.search(r"B=([-\d.]+),([-\d.]+),([-\d.]+)", line)
        key = (tuple(round(float(x), 2) for x in n.groups()),
               tuple(round(float(x), 2) for x in b.groups()))
        add = filt in (0, 2) or (filt == 5 and (pf & 0x20) == 0)
        (kept if add else discarded).append((key, filt, pf, line))
    return kept, discarded


native = parse_native(ROOT / "_scratch/area51_brush1852_native_nadd_v2.log")
kept, discarded = parse_editor(ROOT / "_scratch/area51-oracle-logs/area51_brush1852_editor_afunc_tail.log")

print(f"native kept: {len(native)} fragments")
print(f"editor kept: {len(kept)} fragments; editor discarded (filter=F_INSIDE etc): {len(discarded)}")

nat_c = Counter(native)
ed_c = Counter(k for k, *_ in kept)

only_native = nat_c - ed_c
only_editor = ed_c - nat_c

print(f"\n=== only in NATIVE's kept set ({sum(only_native.values())} frags) ===")
for k, c in only_native.items():
    print(f"  x{c}  N={k[0]} B={k[1]}")

print(f"\n=== only in EDITOR's kept set ({sum(only_editor.values())} frags) ===")
for k, c in only_editor.items():
    print(f"  x{c}  N={k[0]} B={k[1]}")

print("\n=== editor's DISCARDED fragments (filter=F_INSIDE=1, etc) -- does native ALSO produce these as kept? ===")
for key, filt, pf, line in discarded:
    hit = "  <-- NATIVE KEPT THIS ONE TOO (native disagrees: kept what editor discarded)" if key in nat_c else ""
    print(f"  filter={filt} pf={pf:#x} N={key[0]} B={key[1]}{hit}")
