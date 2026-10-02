"""Dump UED22 `UCC.exe`'s runtime GObjNames + GObjObjects order at `UObject::SavePackage` — the
count-tie tie-break for the name / import tables (`ordering.order_package`). Emits the per-substrate
data `uedcli/uscript/data/{gobjnames,gobjobjects}_ued22.json`. No table-fitting: raw runtime order.

WHY a runtime dump: both gathers iterate a GLOBAL engine array by ascending index, so the tie order
is a boot+load artifact not derivable from the source under compilation. The static CRT-registrant
order is NOT the runtime index order (UClass/UObject bootstrap before the registrants run).

DISASSEMBLY (core.dll, ImageBase 0x10000000; verified via capstone):
  SavePackage            @ 0x100277c0  (export ?SavePackage@UObject@@...)
  name  gather @0x27ea0  iterates GObjNames   Data@0x10139d50 Count@0x10139d54 ascending index;
                          appends i where FNameEntry->Flags(+4) & 0x10; then msvc_qsort DESC by count.
  import gather @0x28020  iterates GObjObjects Data@0x1013a260 Count@0x1013a264 ascending index;
                          appends obj where obj->ObjectFlags(+0x1c) & tag; then msvc_qsort DESC.
  FNameEntry: Index@+0, Flags@+4, string@+0xc (UTF-16LE, NUL-terminated).
  UObject:    Outer@+0x18, ObjectFlags@+0x1c, Name(FName idx)@+0x20, Class(UClass*)@+0x24.

METHOD (winedbg, piped stdin — bwedbg's own `break` can't insert into core's code, but a direct
`set *(int*)ADDR = ...` memory write CAN, so we plant an INT3 (0xcc) at SavePackage ourselves):
  break at UCC entry (0x409dc2) -> `set` 0xcc at 0x100277c0 -> cont -> at the trap, walk both arrays
  with computed-index `x` expressions. core.dll loads at its fixed ImageBase (no ASLR), so addresses
  are constant across runs. A trivial EMPTY class is placed FIRST in EditPackages so `base` carries
  no probe member names; NULL GObjNames slots (the gather skips them) are omitted.

Run in the UED22 build image (`ued-x86-runtime`), which ships wine-8.0 + winedbg + python3:
    python3 dump_gobj.py            # needs a running container named by CTR (see _sh)
Regenerating the data is a manual, substrate-specific step; the committed JSON is the shipped artifact.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

CTR = "uned-re"                      # a container from the UED22 build image, wineprefix initialised
PKG = "Uscpr"                        # empty probe class, placed first in EditPackages
DATA = Path(__file__).resolve().parents[6] / "uedcli" / "uscript" / "data"

NAMES_DATA, NAMES_CNT = "0x10139d50", "0x10139d54"
OBJS_DATA, OBJS_CNT = "0x1013a260", "0x1013a264"
ENTRY, SAVEPKG_INT3 = "0x409dc2", "set *(int*)0x100277c0 = 0x6aec8bcc"
PRE = ["break *" + ENTRY, "cont", "delete break 1", SAVEPKG_INT3, "cont"]


def _sh(script: str, *, inp: str | None = None, timeout: int = 560) -> str:
    return subprocess.run(["docker", "exec", "-i", CTR, "sh", "-c", script],
                          capture_output=True, text=True, timeout=timeout, input=inp).stdout


def _setup() -> None:
    _sh(f"rm -rf /opt/{PKG}; mkdir -p /opt/{PKG}/Classes; rm -f /opt/UED22/{PKG}.u")
    _sh(f"cat > /opt/{PKG}/Classes/{PKG}.uc", inp=f"class {PKG} expands Object;\n")
    ini = _sh("cat /opt/UED22/unrealtournament.ini")
    lines = [l for l in ini.splitlines() if l.strip() != f"EditPackages={PKG}"]
    out: list[str] = []
    for l in lines:
        out.append(l)
        if l.strip().lower() == "[editor.editorengine]":
            out.append(f"EditPackages={PKG}")
    _sh("cat > /opt/UED22/unrealtournament.ini", inp="\n".join(out) + "\n")


def _winedbg(batch: str) -> str:
    _sh("cat > /re/batch.txt", inp=batch)
    return _sh("cd /opt/UED22 && WINEPREFIX=/wineprefix WINEDEBUG=-all "
               "winedbg UCC.exe make < /re/batch.txt")


def _counts() -> tuple[int, int]:
    _sh(f"rm -f /opt/UED22/{PKG}.u")
    out = _winedbg("\n".join(PRE + [f"print *(int*){NAMES_CNT}", f"print *(int*){OBJS_CNT}", "quit", ""]))
    vals = [int(x, 16) for x in re.findall(r"Wine-dbg>0x([0-9a-f]+)\b", out)]
    return vals[-2], vals[-1]


def _dump(nc: int, oc: int) -> str:
    _sh(f"rm -f /opt/UED22/{PKG}.u")
    b = list(PRE) + ["print 0xFACE0000"]
    b += [f"x/144b *(int*)(*(int*){NAMES_DATA} + {i * 4})" for i in range(nc)]
    b += ["print 0xFACE0001", f"x/{oc}x *(int*){OBJS_DATA}", "print 0xFACE0002"]
    b += [f"x/4x *(int*)(*(int*){OBJS_DATA} + {i * 4}) + 0x18" for i in range(oc)]
    b += ["print 0xFACE0003", "quit", ""]
    return _winedbg("\n".join(b))


_HEAD = re.compile(r'0x[0-9a-f]+:\s+(.*?)\s*$')


def _hexwords(line: str, width: int) -> list[int] | None:
    m = _HEAD.search(line)
    if not m:
        return None
    parts = m.group(1).split()
    if parts and all(re.fullmatch(r'[0-9a-f]{%d}' % width, p) for p in parts):
        return [int(p, 16) for p in parts]
    return None


def _decode(bs: list[int], off: int = 12) -> str:
    out, i = [], off
    while i + 1 < len(bs):
        ch = bs[i] | (bs[i + 1] << 8)
        if ch == 0:
            break
        out.append(ch)
        i += 2
    return "".join(map(chr, out))


def parse(raw: str) -> tuple[list[str], list[list]]:
    def sec(a: str, b: str) -> str:
        return raw[raw.index(a):raw.index(b)]
    names_sec = sec("0xface0000", "0xface0001")
    objptr_sec = sec("0xface0001", "0xface0002")
    objfld_sec = sec("0xface0002", "0xface0003")

    names, idx_of = [], {}          # gather (ascending index, NULL slots skipped) + true index
    idx = 0
    for ch in names_sec.split("Wine-dbg>"):
        if "Invalid address 0x00000000" in ch:
            idx += 1
            continue
        bls = [b for l in ch.splitlines() if (b := _hexwords(l, 2))]
        if not bls:
            continue
        nm = _decode([x for b in bls for x in b])
        names.append(nm)
        idx_of[idx] = nm
        idx += 1

    ptrs: list[int] = []
    for l in objptr_sec.splitlines():
        w = _hexwords(l, 8)
        if w:
            ptrs += w
    ptr2i = {p: i for i, p in enumerate(ptrs) if p}
    flds: list[list[int] | None] = []
    for ch in objfld_sec.split("Wine-dbg>"):
        if "Invalid address" in ch:
            flds.append(None)
            continue
        for l in ch.splitlines():
            w = _hexwords(l, 8)
            if w and len(w) == 4:
                flds.append(w)
                break
    objs = []
    for f in flds:
        if f is None:
            objs.append(None)
            continue
        outer, _flag, nmeidx, clsptr = f
        rn = lambda p: idx_of.get(flds[ptr2i[p]][2]) if p in ptr2i and flds[ptr2i[p]] else None
        objs.append([idx_of.get(nmeidx), rn(clsptr), rn(outer)])
    return names, [o for o in objs if o]


_DOC = ("UED22 runtime GObjNames/GObjObjects gather order at UObject::SavePackage — the count-tie "
        "tie-break for UCC's name/import tables. Dumped by dump_gobj.py (see it for the exact "
        "disassembly + winedbg method). Ascending global index, NULL name slots skipped; trailing "
        "probe/make objects are inert for reproduction.")


def main() -> None:
    _setup()
    nc, oc = _counts()
    print("counts:", nc, oc)
    names, objs = parse(_dump(nc, oc))
    print("names:", len(names), "objects:", len(objs))
    (DATA / "gobjnames_ued22.json").write_text(json.dumps({"_doc": _DOC, "names": names}, indent=0))
    (DATA / "gobjobjects_ued22.json").write_text(json.dumps({"_doc": _DOC, "objects": objs}, indent=0))
    print("wrote", DATA)


if __name__ == "__main__":
    sys.exit(main())
