#!/usr/bin/env python3
"""Structural byte-parity diff of two UE1 packages (native unbuilt vs editor MAP SAVE golden).

Reports, in order: header fields, name table (set + order), import table (set + order), export
table (set + order + flags/ssize), and per-export BODY bytes for exports matched by identity
(class + outer-chain name). Order differences are named explicitly, never smeared positionally.

Usage: structure_diff.py <native.dx> <editor.dx> [--bodies N]
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))

from uedcli.native.pkg_write import parse_package, ParsedPackage  # noqa: E402

SEP = "=" * 78


def load(path: str) -> ParsedPackage:
    return parse_package(Path(path).read_bytes())


def imp_path(p: ParsedPackage, j: int) -> str:
    cp, cn, pi, on = p.imports[j]
    chain, ref = [], pi
    while ref < 0:
        k = -ref - 1
        chain.append(p.names[p.imports[k][3]])
        ref = p.imports[k][2]
    outer = ".".join(reversed(chain))
    who = f"{outer}.{p.names[on]}" if outer else p.names[on]
    return f"{p.names[cp]}.{p.names[cn]} '{who}'"


def exp_identity(p: ParsedPackage, i: int) -> str:
    e = p.exports[i]
    chain, outer = [], e["outer"]
    while outer > 0:
        oe = p.exports[outer - 1]
        chain.append(p.names[oe["nm"]])
        outer = oe["outer"]
    prefix = ".".join(reversed(chain))
    nm = p.names[e["nm"]]
    full = f"{prefix}.{nm}" if prefix else nm
    return f"{p.class_of_export(i) or '<Class>'} {full}"


def diff_seq(label: str, a: list, b: list, *, show: int = 12) -> bool:
    """Set + order diff; returns True when identical."""
    print(SEP)
    print(f"{label}  A={len(a)}  B={len(b)}")
    sa, sb = set(a), set(b)
    only_a = [x for x in a if x not in sb]
    only_b = [x for x in b if x not in sa]
    if only_a:
        print(f"  only in A ({len(only_a)}):")
        for x in only_a[:show]:
            print(f"     + {x}")
    if only_b:
        print(f"  only in B ({len(only_b)}):")
        for x in only_b[:show]:
            print(f"     - {x}")
    firstdiff = next((i for i in range(min(len(a), len(b))) if a[i] != b[i]), None)
    if firstdiff is None and len(a) == len(b):
        print("  ORDER: identical")
        return not (only_a or only_b)
    print(f"  ORDER: first divergence at index {firstdiff}")
    lo = max(0, (firstdiff or 0) - 2)
    for i in range(lo, min(max(len(a), len(b)), (firstdiff or 0) + show)):
        x = a[i] if i < len(a) else "<none>"
        y = b[i] if i < len(b) else "<none>"
        mark = "  " if x == y else "!!"
        print(f"     {mark} [{i:3}] A={x!r}")
        print(f"     {mark}           B={y!r}")
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("a", help="native .dx")
    ap.add_argument("b", help="editor .dx")
    ap.add_argument("--bodies", type=int, default=20, help="max mismatching bodies to detail")
    args = ap.parse_args()
    A, B = load(args.a), load(args.b)
    buf_a, buf_b = Path(args.a).read_bytes(), Path(args.b).read_bytes()

    same = buf_a == buf_b
    print(f"A: {args.a} ({len(buf_a)} bytes)")
    print(f"B: {args.b} ({len(buf_b)} bytes)")
    print(f"RAW BYTES: {'IDENTICAL' if same else 'DIFFER'}")
    if same:
        return 0

    print(SEP)
    print("HEADER")
    ok = True
    for label, x, y in [("version", A.version, B.version), ("licensee", A.licensee, B.licensee),
                        ("package_flags", hex(A.flags), hex(B.flags)),
                        ("name_count", len(A.names), len(B.names)),
                        ("import_count", len(A.imports), len(B.imports)),
                        ("export_count", len(A.exports), len(B.exports))]:
        mark = "  " if x == y else "!!"
        ok &= x == y
        print(f"  {mark} {label:<14} A={x!r:<20} B={y!r}")
    ga = struct.unpack_from("<I", buf_a, 36 + 16)[0] if A.version >= 68 else None
    gb = struct.unpack_from("<I", buf_b, 36 + 16)[0] if B.version >= 68 else None
    print(f"     generations count A={ga} B={gb} "
          f"(guid excluded: A={A.guid.hex() if A.guid else None} B={B.guid.hex() if B.guid else None})")

    names_ok = diff_seq("NAME TABLE", list(A.names), list(B.names))
    imports_ok = diff_seq("IMPORT TABLE", [imp_path(A, j) for j in range(len(A.imports))],
                          [imp_path(B, j) for j in range(len(B.imports))])
    ids_a = [exp_identity(A, i) for i in range(len(A.exports))]
    ids_b = [exp_identity(B, i) for i in range(len(B.exports))]
    exports_ok = diff_seq("EXPORT TABLE", ids_a, ids_b)

    print(SEP)
    print("EXPORT FIELDS + BODY BYTES (matched by identity)")
    idx_b = {x: i for i, x in enumerate(ids_b)}
    n_field = n_body = 0
    for i, x in enumerate(ids_a):
        j = idx_b.get(x)
        if j is None:
            continue
        ea, eb = A.exports[i], B.exports[j]
        if ea["flags"] != eb["flags"] or ea["ssize"] != eb["ssize"]:
            n_field += 1
            if n_field <= args.bodies:
                print(f"  !! {x}: flags A={ea['flags']:#010x} B={eb['flags']:#010x} "
                      f"ssize A={ea['ssize']} B={eb['ssize']}")
        body_a = buf_a[ea["soff"]:ea["soff"] + ea["ssize"]]
        body_b = buf_b[eb["soff"]:eb["soff"] + eb["ssize"]]
        if body_a != body_b:
            n_body += 1
            if n_body <= args.bodies:
                off = next((k for k in range(min(len(body_a), len(body_b)))
                            if body_a[k] != body_b[k]), min(len(body_a), len(body_b)))
                print(f"  !! BODY {x}: sizes {len(body_a)}/{len(body_b)}, "
                      f"first byte diff at +{off}: "
                      f"A[{off}:{off+8}]={body_a[off:off+8].hex()} "
                      f"B[{off}:{off+8}]={body_b[off:off+8].hex()}")
    print(f"  field mismatches: {n_field}; body mismatches: {n_body} "
          f"(of {len(idx_b.keys() & set(ids_a))} matched exports)")
    print(SEP)
    verdict = ok and names_ok and imports_ok and exports_ok and n_field == 0 and n_body == 0
    print(f"STRUCTURAL PARITY: {'YES (raw bytes may still differ in guid/offsets)' if verdict else 'NO'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
