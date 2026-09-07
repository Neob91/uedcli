#!/usr/bin/env python3
"""Diff native's permeating-light flood against a live `ActorVisibility` capture, light by light.

    UEDCLI_PERM_TRACE=all <native build>            2> native.log
    actor_visibility_probe.py --trunk <subset>      -> editor.log
    perm_flood_diff.py native.log editor.log [--light X,Y,Z]

Both sides are a flood over the leaf-portal graph, so the comparable things are the MARKED leaf set
and the set of leaf-to-leaf crossings each side recursed through. Lights are paired on the actor
Location (f32 bits), leaves on index (the two leaf arrays are the same `Model.Leaves`).

A crossing native takes and the editor does not is where its beam clip is too permissive; the
reverse is a beam clip too tight. Per `permeating_lights.rs` the error has only ever been the first.
"""
from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

NAT_LIGHT = re.compile(r"^PERM_LIGHT li=(\d+) loc=\[([^\]]*)\] radius=(\S+) seed_leaf=(-?\d+)")
NAT_MARK = re.compile(r"^PERM_MARK light=(\d+) leaf=(-?\d+) depth=(\d+)")
NAT_FACE = re.compile(r"^PERM_FACE light=(\d+) depth=(\d+) (-?\d+)->(-?\d+) d=(\S+) (KEEP|DROP)")
ED_ENTRY = re.compile(r"^AV leaf=(-?\d+) loc=\[([^\]]*)\] clip=(\S+)")
ED_MARK = re.compile(r"^AV_MARK leaf=(-?\d+)")
ED_REC = re.compile(r"^AV_REC from=(-?\d+) to=(-?\d+) nv=(-?\d+)")


def key(loc: list[float]) -> tuple:
    return tuple(struct.pack("<f", v) for v in loc)


def _f(s: str) -> list[float]:
    return [float(x) for x in s.split(",")]


def parse_native(path: Path):
    """{light key: {'marks': set, 'cross': set, 'seed': int, 'li': int}}"""
    out, by_li = {}, {}
    for line in path.read_text(errors="replace").splitlines():
        if m := NAT_LIGHT.match(line):
            k = key(_f(m.group(2)))
            rec = out.setdefault(k, {"marks": set(), "cross": set(), "seed": int(m.group(4)),
                                     "li": int(m.group(1))})
            by_li[m.group(1)] = rec
        elif m := NAT_MARK.match(line):
            if rec := by_li.get(m.group(1)):
                rec["marks"].add(int(m.group(2)))
        elif m := NAT_FACE.match(line):
            if (rec := by_li.get(m.group(1))) and m.group(6) == "KEEP":
                rec["cross"].add((int(m.group(3)), int(m.group(4))))
    return out


def parse_editor(path: Path):
    """Same shape. The capture has no light id, so entries are attributed to the actor Location the
    entry line carries, and a crossing to whichever light was last entered."""
    out, cur = {}, None
    for line in path.read_text(errors="replace").splitlines():
        if m := ED_ENTRY.match(line):
            cur = out.setdefault(key(_f(m.group(2))),
                                 {"marks": set(), "cross": set(), "seed": None, "li": None})
        elif cur is None:
            continue
        elif m := ED_MARK.match(line):
            cur["marks"].add(int(m.group(1)))
        elif m := ED_REC.match(line):
            cur["cross"].add((int(m.group(1)), int(m.group(2))))
    return out


def main() -> int:
    nat = parse_native(Path(sys.argv[1]))
    ed = parse_editor(Path(sys.argv[2]))
    want = None
    for i, a in enumerate(sys.argv):
        if a == "--light":
            want = key([float(x) for x in sys.argv[i + 1].split(",")])
    print(f"native lights {len(nat)}, editor lights {len(ed)}, paired {len(set(nat) & set(ed))}")
    for k in sorted(set(nat) & set(ed)):
        if want and k != want:
            continue
        n, e = nat[k], ed[k]
        loc = [struct.unpack("<f", b)[0] for b in k]
        mark_extra, mark_missing = n["marks"] - e["marks"], e["marks"] - n["marks"]
        cross_extra, cross_missing = n["cross"] - e["cross"], e["cross"] - n["cross"]
        if not (mark_extra or mark_missing or cross_extra or cross_missing):
            print(f"light li={n['li']} {loc}: IDENTICAL "
                  f"({len(n['marks'])} leaves, {len(n['cross'])} crossings)")
            continue
        print(f"light li={n['li']} {loc}: marks {len(n['marks'])} vs {len(e['marks'])}, "
              f"crossings {len(n['cross'])} vs {len(e['cross'])}")
        if mark_extra:
            print(f"    leaves native marks and the editor does not: {sorted(mark_extra)}")
        if mark_missing:
            print(f"    leaves the editor marks and native does not: {sorted(mark_missing)}")
        if cross_extra:
            print(f"    crossings native takes and the editor does not: {sorted(cross_extra)}")
        if cross_missing:
            print(f"    crossings the editor takes and native does not: {sorted(cross_missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
