#!/usr/bin/env python3
"""Decode the saved probe .dx: for every probe actor, report whether UED22 stamped `Base`, its
resolved target, plus the class-default flags + ancestry -> the truth table.

Uses the parity-gate's `Ident` + `uedcli.upackage.read_property_tags`. Actors carry a StateFrame
prefix when RF_HasStack; it is skipped before the tagged props.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path("/workspace/uedcli/.claude/worktrees/native-parity-incremental")
GATE = ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(GATE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from uedcli.upackage import load_package, read_property_tags   # noqa: E402
from uedcli.classdefaults import ClassDefaults                 # noqa: E402
from uedcli.classindex import ClassIndex                       # noqa: E402
from parity_gate import Ident, RF_HasStack, _stateframe        # noqa: E402
from probe_classes import MOVER_PROBE, PROBES                  # noqa: E402

SYS = Path("/workspace/uedcli/dev/games/deusex/system")
BASES = ["Engine.Decoration", "Engine.Inventory", "Engine.Pawn", "Engine.Effects",
         "Engine.Projectile", "Engine.Light", "Engine.Keypoint", "Engine.Triggers",
         "Engine.NavigationPoint", "Engine.Mover", "Engine.Brush"]


def _flags():
    paths = {f.stem.casefold(): str(f) for f in SYS.glob("*.u")}
    cd = ClassDefaults(lambda p: paths.get(p.casefold()))
    ci = ClassIndex.from_files([(f.stem, str(f)) for f in SYS.glob("*.u")])

    def phys(c):
        v = cd.for_class(c).defaults.get(("physics", 0))
        return v or "PHYS_None"

    def boolflag(c, f):
        return str(cd.for_class(c).defaults.get((f, 0))) == "True"

    def anc(c):
        return "/".join(b.split(".")[-1] for b in BASES if ci.descends_from(c, b)) or "-"

    return phys, boolflag, anc


def _base_of(idt: Ident, i0: int):
    """(stamped?, resolved-target-identity | None) for export i0."""
    p = idt.p
    e = p.exports[i0]
    pos, end = e["soff"], e["soff"] + e["ssize"]
    if e["flags"] & RF_HasStack:
        _sf, pos = _stateframe(idt, pos)
    tags, _ = read_property_tags(p, pos, end)
    for t in tags:
        if t.name.casefold() == "base":
            from parity_gate import _canon_value
            v = _canon_value(idt, t)          # ("obj", identity)
            return True, v[1]
    return False, None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dx")
    args = ap.parse_args()

    p = load_package(args.dx)
    idt = Ident(p)
    # name -> export index
    by_name: dict[str, int] = {}
    for i, e in enumerate(p.exports):
        by_name[p.names[e["nm"]].casefold()] = i

    phys, boolflag, anc = _flags()
    specs = list(PROBES) + [MOVER_PROBE]

    rows = []
    for name, cls, note in specs:
        i0 = by_name.get(name.casefold())
        if i0 is None:
            rows.append((name, cls, note, "MISSING", "", "", "", "", ""))
            continue
        stamped, target = _base_of(idt, i0)
        rows.append((name, cls, note, "YES" if stamped else "no",
                     target or "", anc(cls), phys(cls),
                     "T" if boolflag(cls, "bcollideworld") else "F",
                     "T" if boolflag(cls, "bstatic") else "F"))

    w = max(len(r[1]) for r in rows)
    print(f"{'class':{w}}  {'anc':22}  {'phys':16}  bCW bStat  Base  target")
    print("-" * (w + 70))
    for name, cls, note, base, target, ancestry, physv, bcw, bstat in rows:
        print(f"{cls:{w}}  {ancestry:22}  {physv:16}   {bcw}   {bstat}    {base:4}  {target}")
    # summary: which ancestries got stamped
    print("\nSTAMPED:", sorted({r[5] for r in rows if r[3] == 'YES'}))
    print("NOT   :", sorted({r[5] for r in rows if r[3] == 'no'}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
