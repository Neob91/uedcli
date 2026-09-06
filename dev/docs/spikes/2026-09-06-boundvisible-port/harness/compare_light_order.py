#!/usr/bin/env python3
"""Check native bakes lights in UED22's own `LIGHT APPLY` order.

`NF_BoxOccluded` is last-write-wins across lights, so `light::bake`'s replay is only faithful if
native's `lights` slice is ordered the way the editor iterates them. Both sides emit their light
Locations in call order — the editor via `boundvisible_frame_probe.py`, native via
`UEDCLI_VISGATE_TRACE_BOX` — so comparing the two first-seen sequences settles it.

Usage: compare_light_order.py <native-trace.log> <bv_calls.json>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

LINE = re.compile(r"VISGATE_BOX light=\[([^\]]*)\]")


def dedup(seq):
    out = []
    for v in seq:
        if v not in out:
            out.append(v)
    return out


def main() -> int:
    native = dedup(tuple(round(float(x), 2) for x in m.group(1).split(","))
                   for line in Path(sys.argv[1]).read_text(errors="replace").splitlines()
                   if (m := LINE.search(line)))
    editor = dedup(tuple(round(v, 2) for v in r["origin"])
                   for r in json.load(open(sys.argv[2])) if r["sx"] == 1024)
    print(f"native {len(native)} lights, editor {len(editor)}")
    if native == editor:
        print("ORDER MATCHES")
        return 0
    print("ORDER DIFFERS")
    for i, (a, b) in enumerate(zip(native, editor)):
        if a != b:
            print(f"  first divergence at index {i}: native {a} editor {b}")
            break
    print(f"  same SET: {sorted(native) == sorted(editor)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
