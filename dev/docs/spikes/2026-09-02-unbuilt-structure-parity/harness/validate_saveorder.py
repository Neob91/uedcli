#!/usr/bin/env python3
"""Validate the save-order model against a saveorder_oracle.py dump + the saved .dx.

Checks, in order:
  1. NMAP_PRE is ascending in global FName index (collection = FName-table scan order).
  2. The editor's per-name counters equal count_refs.py's recomputation from the saved file.
  3. msvc_qsort(NMAP_PRE, desc by count) == NMAP_POST (the qsort port is exact).
  4. NMAP_POST == the saved file's name table.
  5. Same chain for IMAP (pre ascending in GObjObjects index, counters match incl.
     outer-chain propagation, qsort port maps pre -> post, post == file import table).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from uedcli.upackage import load_package                  # noqa: E402
from count_refs import collect, import_totals             # noqa: E402
from msvc_qsort import msvc_qsort                         # noqa: E402


def parse_dump(path: Path) -> dict:
    d = {"NAME": [], "OBJ": [], "NMAP_PRE": [], "NMAP_POST": [],
         "IMAP_PRE": [], "IMAP_POST": []}
    for line in path.read_text().splitlines():
        parts = line.split()
        if parts and parts[0] in d:
            d[parts[0]].append(parts[1:])
    return d


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{'OK ' if ok else 'FAIL'} {label}" + (f" -- {detail}" if detail and not ok else ""))
    return ok


def main() -> int:
    dump = parse_dump(Path(sys.argv[1]))
    pkg = load_package(sys.argv[2])
    golden = load_package(sys.argv[3]) if len(sys.argv) > 3 else None
    ok = True

    # --- names ---
    pre = [(int(p[1]), int(p[2]), p[3] if len(p) > 3 else "") for p in dump["NMAP_PRE"]]
    post = [(int(p[1]), int(p[2]), p[3] if len(p) > 3 else "") for p in dump["NMAP_POST"]]
    ok &= check("NMAP_PRE ascending by global name index",
                all(pre[i][0] < pre[i + 1][0] for i in range(len(pre) - 1)))

    ev = collect(pkg)
    # editor counter vs recomputed: match via text (file table order == NMAP_POST order)
    ok &= check("NMAP_POST text == file name table",
                [t for _, _, t in post] == list(pkg.names),
                f"{[t for _, _, t in post][:6]} vs {pkg.names[:6]}")
    mycount = {pkg.names[i]: ev.names.get(i, 0) for i in range(len(pkg.names))}
    edcount = {t: c for _, c, t in pre}
    diffs = {t: (edcount[t], mycount.get(t)) for t in edcount
             if mycount.get(t) != edcount[t]}
    ok &= check("editor NameIndices counters == count_refs recomputation",
                not diffs, str(list(diffs.items())[:10]))

    arr = [(gi, c) for gi, c, _ in pre]
    msvc_qsort(arr, lambda a, b: b[1] - a[1])
    ok &= check("msvc_qsort(NMAP_PRE) == NMAP_POST",
                [gi for gi, _ in arr] == [gi for gi, _, _ in post],
                f"first diffs {[(i, arr[i][0], post[i][0]) for i in range(len(arr)) if arr[i][0] != post[i][0]][:6]}")

    # --- imports ---
    ipre = [(int(p[1], 16), int(p[2]), int(p[4]), p[5]) for p in dump["IMAP_PRE"]]
    ipost = [(int(p[1], 16), p[5]) for p in dump["IMAP_POST"]]
    ok &= check("IMAP_PRE ascending by GObjObjects index",
                all(ipre[i][1] < ipre[i + 1][1] for i in range(len(ipre) - 1)))
    ok &= check("IMAP_POST identities == file import table",
                [t for _, t in ipost] == [pkg.names[i[3]] for i in pkg.imports])
    totals = import_totals(pkg, ev)
    bytext = {}
    for j, imp in enumerate(pkg.imports):
        bytext.setdefault(pkg.names[imp[3]], []).append(totals[j])
    idiffs = [(t, c, bytext.get(t)) for _, _, c, t in ipre if c not in bytext.get(t, [])]
    ok &= check("editor ObjectIndices counters == count_refs recomputation (incl. outer chain)",
                not idiffs, str(idiffs[:10]))
    iarr = [(xo, c) for xo, _, c, _ in ipre]
    msvc_qsort(iarr, lambda a, b: b[1] - a[1])
    ok &= check("msvc_qsort(IMAP_PRE) == IMAP_POST",
                [xo for xo, _ in iarr] == [xo for xo, _ in ipost])

    if golden is not None:
        ok &= check("traced save name table == golden name table",
                    list(pkg.names) == list(golden.names))
        ok &= check("traced save import identities == golden import identities",
                    [pkg.names[i[3]] for i in pkg.imports] ==
                    [golden.names[i[3]] for i in golden.imports])
    print("ALL OK" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
