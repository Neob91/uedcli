#!/usr/bin/env python3
"""Parse `boundvisible_frame_probe.py`'s gdb log into per-call records.

Emits JSON (`--json out.json`) and a short summary: which nodes were box-tested, the frame each
call ran under, the box, and the call's return value + `FScreenBounds`. `--last` prints the FINAL
test outcome per node, i.e. the `NF_BoxOccluded` state the shadow-ray walker then reads.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

IN_RE = re.compile(r"^IN hit=(\d+) frame=(\S+) span=(\S+) node_esi=(-?\d+)")
BOX_RE = re.compile(r"^IN box=\[([^\]]*)\]-\[([^\]]*)\] valid=(-?\d+)")
CO_RE = re.compile(r"^FRAME origin=\[([^\]]*)\] xaxis=\[([^\]]*)\] yaxis=\[([^\]]*)\] zaxis=\[([^\]]*)\]")
FR_RE = re.compile(
    r"^FRAME X=(-?\d+) Y=(-?\d+) XB=(-?\d+) YB=(-?\d+) FX=(\S+) FY=(\S+) F_c0=(\S+) F_c4=(\S+) "
    r"FX15=(\S+) FY15=(\S+) F_d0=(\S+) proj=\[([^\]]*)\] rproj=(\S+) clip=\[([^\]]*)\] zone=(\d+)")
OUT_RE = re.compile(r"^OUT hit=(\d+) ret=(-?\d+) sb=\[([^\]]*)\]")
EXIT_RE = re.compile(r"^EXIT hit=\d+ path=(\w+)")


def _f(s):
    return [float(x) for x in s.split(",")]


def parse(path: Path) -> list[dict]:
    recs, cur = [], None
    for line in path.read_text(errors="replace").splitlines():
        if m := IN_RE.match(line):
            cur = {"hit": int(m.group(1)), "frame": m.group(2), "span": m.group(3),
                   "node": int(m.group(4))}
        elif cur is None:
            continue
        elif m := BOX_RE.match(line):
            cur["box_min"], cur["box_max"], cur["box_valid"] = _f(m.group(1)), _f(m.group(2)), int(m.group(3))
        elif m := CO_RE.match(line):
            cur["origin"], cur["xaxis"], cur["yaxis"], cur["zaxis"] = (
                _f(m.group(1)), _f(m.group(2)), _f(m.group(3)), _f(m.group(4)))
        elif m := FR_RE.match(line):
            cur.update(fx=float(m.group(5)), fy=float(m.group(6)),
                       cx=float(m.group(9)), cy=float(m.group(10)),
                       sx=int(m.group(1)), sy=int(m.group(2)),
                       proj=_f(m.group(12)), clip=_f(m.group(14)), zone=int(m.group(15)))
        elif m := EXIT_RE.match(line):
            # The exit breakpoints sit inside `BoundVisible`, which other callers also reach, so
            # a tag counts only while one of OUR call-site hits is open (between its IN and OUT).
            # `hit=` in the EXIT line is the last IN's number and is unreliable on its own.
            cur.setdefault("exit", m.group(1))
        elif m := OUT_RE.match(line):
            if cur.get("hit") == int(m.group(1)):
                cur["ret"] = int(m.group(2))
                cur["sb"] = _f(m.group(3))
                recs.append(cur)
                cur = None
    return recs


def main() -> int:
    log = Path(sys.argv[1])
    recs = parse(log)
    print(f"{len(recs)} complete BoundVisible calls")
    gather = [r for r in recs if r["sx"] == 1024 and r["sy"] == 1024]
    print(f"{len(gather)} of them from the 1024x1024 gather viewport")
    last: dict[int, dict] = {}
    for r in gather:
        last[r["node"]] = r
    print("final per-node outcome in the gather pass (ret 0 => NF_BoxOccluded set):")
    for n in sorted(last):
        print(f"  node {n:5d}  ret={last[n]['ret']}  zone={last[n]['zone']}  sb={last[n]['sb']}")
    for i, a in enumerate(sys.argv):
        if a == "--json":
            Path(sys.argv[i + 1]).write_text(json.dumps(gather, indent=1))
            print("wrote", sys.argv[i + 1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
