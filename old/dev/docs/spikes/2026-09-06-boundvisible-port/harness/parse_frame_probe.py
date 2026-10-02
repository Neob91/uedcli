#!/usr/bin/env python3
"""Parse `boundvisible_frame_probe.py`'s gdb log into per-call records.

Emits JSON (`--json out.json`) and a short summary: which nodes were box-tested, the frame each
call ran under, the box, and the call's return value + `FScreenBounds`. `--last` prints the FINAL
test outcome per node, i.e. the `NF_BoxOccluded` state the shadow-ray walker then reads.

`ret` is `BoundVisible`'s own return, which under `bUseZones` is only HALF the box-occlusion
decision: the `FSpanBuffer*` argument is NULL there and `OccludeBsp` runs the span test itself
afterwards, once per active zone. `2026-09-07-gather-box-verdict/harness/box_verdict_probe.py`
breaks on the three outcome sites and emits `VERDICT hit=<n> path=geo|zone|accept` lines; when a log
carries them, each record also gets `verdict` and the derived `visible` — the real per-node
outcome. Without them `visible` falls back to `bool(ret)`, which over-reports visibility.
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
VERDICT_RE = re.compile(r"^VERDICT hit=(\d+) path=(\w+)")


def _f(s):
    return [float(x) for x in s.split(",")]


def parse(path: Path) -> list[dict]:
    recs, cur, by_hit = [], None, {}
    for line in path.read_text(errors="replace").splitlines():
        if m := IN_RE.match(line):
            cur = {"hit": int(m.group(1)), "frame": m.group(2), "span": m.group(3),
                   "node": int(m.group(4))}
        elif m := VERDICT_RE.match(line):
            # A verdict site is reached AFTER the call's OUT line, i.e. with no record open — so
            # this arm has to sit above the `cur is None` guard, and pairs by hit number instead.
            if (r := by_hit.get(int(m.group(1)))) is not None:
                r.setdefault("verdict", m.group(2))
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
                by_hit[cur["hit"]] = cur
                cur = None
    for r in recs:
        # An unzoned accept takes `0x10019450 je`, which has no site of its own, so it carries no
        # verdict line; a log from a probe without the verdict sites at all degrades to
        # `BoundVisible`'s return, which over-reports visibility (see `has_verdicts`).
        r["probed"] = "verdict" in r
        r["visible"] = r.setdefault("verdict", "accept" if r["ret"] else "geo") == "accept"
    return recs


def has_verdicts(recs: list[dict]) -> bool:
    """Whether these records come from a probe that captured the outcome sites, i.e. whether
    `visible` is the real box-occlusion verdict rather than `BoundVisible`'s return alone."""
    return any(r["probed"] for r in recs)


def main() -> int:
    log = Path(sys.argv[1])
    recs = parse(log)
    print(f"{len(recs)} complete BoundVisible calls")
    gather = [r for r in recs if r["sx"] == 1024 and r["sy"] == 1024]
    print(f"{len(gather)} of them from the 1024x1024 gather viewport")
    last: dict[int, dict] = {}
    for r in gather:
        last[r["node"]] = r
    print(f"outcome sites captured: {has_verdicts(gather)}")
    print("final per-node outcome in the gather pass (verdict != accept => NF_BoxOccluded set):")
    for n in sorted(last):
        print(f"  node {n:5d}  verdict={last[n]['verdict']:6s} ret={last[n]['ret']}  "
              f"zone={last[n]['zone']}  sb={last[n]['sb']}")
    for i, a in enumerate(sys.argv):
        if a == "--json":
            Path(sys.argv[i + 1]).write_text(json.dumps(gather, indent=1))
            print("wrote", sys.argv[i + 1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
