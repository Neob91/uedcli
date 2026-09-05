#!/usr/bin/env python3
"""Print WHERE two built packages' identity-matched export bodies differ, token by token.

`parity_gate.py` says which export body diverged; this says which token inside it. For a `model`
body the tokens are `_model_tail`'s stream (node planes `NW`, node flags `NF`, masked orphan verts
`MV`, object refs `O`, and literal byte spans `b`), so a diff lands on a named field instead of a
1-MB byte blob. Literal spans are diffed further, down to the first differing byte offset within the
span, with the surrounding bytes shown.

Run: `body_token_diff.py <native.dx> <ued.dx> [export-identity-substring]`
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import parity_gate as g  # noqa: E402
from uedcli.upackage import load_package  # noqa: E402

CONTEXT = 16      # bytes of context either side of a differing byte in a literal span
MAX_TOKENS = 12   # differing tokens reported per body


def _diff_span(a: bytes, b: bytes) -> str:
    n = min(len(a), len(b))
    i = next((k for k in range(n) if a[k] != b[k]), n)
    lo, hi = max(0, i - CONTEXT), i + CONTEXT
    return (f"first differing byte at +{i} of {len(a)}/{len(b)}\n"
            f"        nat={a[lo:hi].hex()}\n        ued={b[lo:hi].hex()}")


def main() -> int:
    if not 3 <= len(sys.argv) <= 4:
        print(__doc__)
        return 2
    want = sys.argv[3].casefold() if len(sys.argv) == 4 else ""
    A, B = load_package(sys.argv[1]), load_package(sys.argv[2])
    ia, ib = g.Ident(A), g.Ident(B)
    ids_a = {ia.export_identity(i): i for i in range(len(A.exports))}
    ids_b = {ib.export_identity(i): i for i in range(len(B.exports))}
    for ident in sorted(set(ids_a) & set(ids_b)):
        if want and want not in ident:
            continue
        ca, cb = g.canon_body(ia, ids_a[ident]), g.canon_body(ib, ids_b[ident])
        if g._bodies_equal(ca, cb):
            continue
        print(f"=== {ident}: {ca[0]} body differs ===")
        if not (isinstance(ca, tuple) and len(ca) == 3 and isinstance(ca[2], list)):
            print(f"  native={g._short(ca)}\n  ued=   {g._short(cb)}")
            continue
        ta, tb = ca[2], cb[2]
        if len(ta) != len(tb):
            print(f"  token COUNT differs: native={len(ta)} ued={len(tb)}")
        shown = 0
        for i, (xa, xb) in enumerate(zip(ta, tb)):
            if xa == xb:
                continue
            shown += 1
            if shown > MAX_TOKENS:
                print("  ... (more)")
                break
            if xa[0] == "b" == xb[0]:
                print(f"  token[{i}] literal span: {_diff_span(xa[1], xb[1])}")
            else:
                print(f"  token[{i}] {xa[0]}: nat={xa[1:]} ued={xb[1:]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
