#!/usr/bin/env python3
"""Summarise `addvector_call_trace.py`'s log: per `UModel`, the `bspAddVector` proposal sequence.

Prints, for the model with the most `bspAddVector` hits (the world model), every call in order with
its phase (the last `MARK`), the caller return address, the vector, and the returned pool index --
plus, for each pool slot, WHICH call first claimed it.

Usage: parse_addvector_trace.py [log] [--model 0x...]
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_LOG = HERE.parent / "logs" / "addvector-call-trace.log"

AV = re.compile(r"^AV n=(\d+) ret=(0x[0-9a-f]+) model=(0x[0-9a-f]+) exact=(\d+) "
                r"v=\(([^)]*)\) nvec=(-?\d+) nsurf=(-?\d+)")
AVR = re.compile(r"^AVR n=(\d+) idx=(-?\d+)")
AN = re.compile(r"^AN model=(0x[0-9a-f]+) iparent=(-?\d+) place=(-?\d+) nf=(0x[0-9a-f]+) "
                r"edpoly=(0x[0-9a-f]+) N=\(([^)]*)\) nsurf=(-?\d+)")
MARK = re.compile(r"^MARK (\S+)")

CALLERS = {"0x10034f39": "bspAddNode:vNormal", "0x10034f55": "bspAddNode:vTextureU",
           "0x10034f71": "bspAddNode:vTextureV"}


def main() -> int:
    log = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else DEFAULT_LOG
    want = None
    for i, a in enumerate(sys.argv):
        if a == "--model":
            want = sys.argv[i + 1]

    phase = "<pre>"
    brush_i = 0
    calls: list[dict] = []
    pending: dict[int, dict] = {}
    counts: Counter[str] = Counter()
    for line in log.read_text(errors="replace").splitlines():
        if m := MARK.match(line):
            phase = m.group(1)
            if phase == "bspBrushCSG":
                brush_i += 1
                phase = f"bspBrushCSG#{brush_i}"
            continue
        if m := AN.match(line):
            phase_an = m.group(1)
            calls.append({"kind": "AN", "model": phase_an, "phase": phase,
                          "normal": m.group(6), "nsurf": int(m.group(7)),
                          "place": int(m.group(3)), "iparent": int(m.group(2))})
            continue
        if m := AV.match(line):
            n = int(m.group(1))
            rec = {"kind": "AV", "n": n, "ret": m.group(2), "model": m.group(3),
                   "exact": int(m.group(4)), "v": m.group(5), "nvec": int(m.group(6)),
                   "nsurf": int(m.group(7)), "phase": phase, "idx": None}
            calls.append(rec)
            pending[n] = rec
            counts[rec["model"]] += 1
            continue
        if m := AVR.match(line):
            rec = pending.pop(int(m.group(1)), None)
            if rec is not None:
                rec["idx"] = int(m.group(2))

    model = want or (counts.most_common(1)[0][0] if counts else None)
    print(f"models by bspAddVector hits: {counts.most_common()}")
    print(f"=== model {model} ===")
    first: dict[int, int] = {}
    for c in calls:
        if c["model"] != model:
            continue
        if c["kind"] == "AN":
            print(f"  [{c['phase']}] bspAddNode N=({c['normal']}) nsurf={c['nsurf']} "
                  f"place={c['place']} iparent={c['iparent']}")
            continue
        tag = CALLERS.get(c["ret"], c["ret"])
        new = c["idx"] is not None and c["idx"] not in first
        if new:
            first[c["idx"]] = c["n"]
        print(f"    n={c['n']:<4} [{c['phase']}] {tag:<22} exact={c['exact']} "
              f"v=({c['v']}) -> idx={c['idx']}{'  NEW' if new else ''}")
    print("=== pool slot -> first-claiming call ===")
    for idx in sorted(first):
        print(f"  vectors[{idx}] first claimed by call n={first[idx]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
