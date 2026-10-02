#!/usr/bin/env python3
"""Read the probe2 captures.

Part 1 — the guard brackets: for each near-threshold wedge, did the mode under test CHANGE its test
face, or leave it alone?
Part 2 — arguments, grammar and scope: which exports differ from their control?

    guards.py <outdir2>
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixture2                                                    # noqa: E402
from uedcli.model import parse_t3d                                 # noqa: E402
from uedcli.polyalign import _world_verts                          # noqa: E402
from uedcli.texframe import newell, world_uv_frame                 # noqa: E402


def frames(path: Path):
    lvl = parse_t3d(path.read_text())
    out = {}
    for name, a in lvl.actors.items():
        if a.brush is None or not any(k == "CsgOper" for k, _ in (a.props or [])):
            continue
        for i, p in enumerate(a.brush.polys):
            wv = _world_verts(a, p)
            if len(wv) < 3:
                continue
            n = newell(wv)
            m = sum(c * c for c in n) ** 0.5
            base, tu, tv, pan = world_uv_frame(a, p)
            out[(name, i)] = (tuple(c / m for c in n), base, tu, tv, (pan[0], pan[1]))
    return out


def same(a, b, tol=1e-4):
    for x, y in zip(a[1:4], b[1:4]):
        if any(abs(p - q) > tol for p, q in zip(x, y)):
            return False
    return tuple(a[4]) == tuple(b[4])


def diff_count(outdir, ctrl_tag, test_tag):
    ctrl, test = outdir / f"{ctrl_tag}.t3d", outdir / f"{test_tag}.t3d"
    if not (ctrl.exists() and test.exists()):
        return None
    a, b = frames(ctrl), frames(test)
    return sum(1 for k in a if not same(a[k], b[k])), len(a)


def write_golden(outdir: Path, dest: Path):
    """Distil the guard brackets into the committed golden the regression test asserts against:
    for each near-threshold face, its normal, the mode applied, and whether the editor touched it."""
    import json
    rows = []
    for case, (t, _ax, _sw, mode) in fixture2.CASES.items():
        ctrl, test = outdir / f"{case}-CTRL.t3d", outdir / f"{case}-{mode}.t3d"
        if not (ctrl.exists() and test.exists()):
            raise SystemExit(f"{case}: not captured — cannot write a complete golden")
        a, b = frames(ctrl), frames(test)
        key = (case, fixture2.TEST_POLY)
        rows.append({"case": case, "target": t, "mode": mode,
                     "n_surf": [round(c, 6) for c in a[key][0]],
                     "changed": not same(a[key], b[key])})
    dest.write_text(json.dumps(
        {"_note": "near-threshold faces: did POLY TEXALIGN <mode> touch this face? spike "
                  "2026-07-26-unrealed-texalign-semantics",
         "cases": rows}, indent=1) + "\n")
    print(f"wrote {dest}")


def main():
    outdir = Path(sys.argv[1])
    if len(sys.argv) > 2:
        write_golden(outdir, Path(sys.argv[2]))
    print("GUARD BRACKETS (the mode under test vs the same level unaligned)\n")
    print(f"{'case':<8}{'|N| target':<12}{'mode':<9}{'test-face normal':<30}"
          f"{'test face':<12}{'other faces'}")
    for case, (t, _ax, _sw, mode) in fixture2.CASES.items():
        ctrl, test = outdir / f"{case}-CTRL.t3d", outdir / f"{case}-{mode}.t3d"
        if not (ctrl.exists() and test.exists()):
            print(f"{case:<8}{t:<12}{mode:<9}(not captured)")
            continue
        a, b = frames(ctrl), frames(test)
        key = (case, fixture2.TEST_POLY)
        n = a[key][0]
        verdict = "UNCHANGED" if same(a[key], b[key]) else "CHANGED"
        others = sum(1 for k in a if k != key and not same(a[k], b[k]))
        print(f"{case:<8}{t:<12}{mode:<9}"
              f"({n[0]:+.4f},{n[1]:+.4f},{n[2]:+.4f})        {verdict:<12}{others}/{len(a)-1} changed")

    print("\nARGUMENTS / GRAMMAR / SCOPE (faces differing from the named control)\n")
    for ctrl, test, note in [
            ("arg-FLOOR", "arg-FLOOR-TEXELS64", "TEXELS= ignored by FLOOR?"),
            ("arg-WALLDIR", "arg-WALLDIR-TEXELS64", "TEXELS= ignored by WALLDIR?"),
            ("arg-ONETILE", "arg-ONETILE-TEXELS64", "TEXELS= ignored by ONETILE?"),
            # ONETILE's control is the state IMMEDIATELY BEFORE it in the same script (the modes in
            # that round compound), not the round's unaligned export.
            ("arg-WALLDIR-TEXELS64", "arg-ONETILE", "ONETILE changes nothing?"),
            ("sel-CTRL", "arg-NOTOKEN", "`POLY TEXALIGN` with no mode token"),
            ("sel-CTRL", "arg-BOGUS", "`POLY TEXALIGN BOGUS`"),
            ("sel-CTRL", "sel-NONE", "WALLDIR with an EMPTY surface selection"),
            ("sel-CTRL", "sel-ALL", "WALLDIR with everything selected (positive control)"),
            ("sel-CTRL", "norebuild-WALLDIR", "WALLDIR with NO MAP REBUILD (no BSP surfaces)")]:
        r = diff_count(outdir, ctrl, test)
        if r is None:
            print(f"  {test:<24} vs {ctrl:<12} (not captured)")
        else:
            print(f"  {test:<24} vs {ctrl:<12} {r[0]}/{r[1]} faces differ    # {note}")


if __name__ == "__main__":
    main()
