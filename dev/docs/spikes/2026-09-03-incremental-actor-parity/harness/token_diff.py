#!/usr/bin/env python3
"""Show WHICH canonical token of a failing export body differs (parity_gate only says "differ").

Usage: token_diff.py <native.dx> <ued22.dx> [<export-identity substring> ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import parity_gate as pg  # noqa: E402


def _fmt(tok, limit: int = 160) -> str:
    s = repr(tok)
    return s if len(s) <= limit else s[:limit] + " ..."


def main() -> int:
    native, ued = sys.argv[1], sys.argv[2]
    wanted = [w.casefold() for w in sys.argv[3:]]
    A, B = pg.load_package(native), pg.load_package(ued)
    ia, ib = pg.Ident(A), pg.Ident(B)
    ids_a = {ia.export_identity(i): i for i in range(len(A.exports))}
    ids_b = {ib.export_identity(i): i for i in range(len(B.exports))}
    for ident in sorted(set(ids_a) & set(ids_b)):
        if wanted and not any(w in ident for w in wanted):
            continue
        ca, cb = pg.canon_body(ia, ids_a[ident]), pg.canon_body(ib, ids_b[ident])
        if pg._bodies_equal(ca, cb):
            continue
        print(f"=== {ident}")
        if not (isinstance(ca, tuple) and ca and ca[0] in ("model", "polys", "level", "actor")):
            print(f"  native={_fmt(ca)}\n  ued=   {_fmt(cb)}")
            continue
        ta, tb = ca[2], cb[2]
        if ca[1] != cb[1]:
            print(f"  stateframe: native={ca[1]!r} ued={cb[1]!r}")
        print(f"  tokens: native={len(ta)} ued={len(tb)}")
        shown = 0
        for k in range(max(len(ta), len(tb))):
            xa = ta[k] if k < len(ta) else "<missing>"
            xb = tb[k] if k < len(tb) else "<missing>"
            if xa == xb:
                continue
            print(f"  [{k}] native={_fmt(xa)}")
            print(f"      ued=   {_fmt(xb)}")
            if isinstance(xa, tuple) and isinstance(xb, tuple) and xa[0] == "b" == xb[0]:
                ba, bb = xa[1], xb[1]
                for o in range(min(len(ba), len(bb))):
                    if ba[o] != bb[o]:
                        print(f"      first byte diff at +{o} of {len(ba)}/{len(bb)}: "
                              f"{ba[o:o+16].hex()} vs {bb[o:o+16].hex()}")
                        break
                else:
                    print(f"      length differs: {len(ba)} vs {len(bb)}")
            shown += 1
            if shown >= 12:
                print("  ... (more)")
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
