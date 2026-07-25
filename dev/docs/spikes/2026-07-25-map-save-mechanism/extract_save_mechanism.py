#!/usr/bin/env python3
"""Extract HOW UnrealEd 2.2 writes a package on `MAP SAVE`, from `core.dll` alone.

Two questions, because a wrong answer to the second one produced a published retraction:

  Q1  What does `UObject::SavePackage` do, in order?      -> UTF-16 string-table run
  Q2  Is the final move a rename or a byte copy?          -> PE import table (answer: UNKNOWABLE
                                                             from here; see below)

Run:  python3 extract_save_mechanism.py [path/to/core.dll]
(defaults to the committed substrate at Tools/uedctl/uned/UED22/core.dll)

The findings are pinned by `uedctl/tests/test_engine_facts.py::
test_save_package_writes_a_temp_and_moves_it_and_never_reads_a_file_through_its_imports`.
"""
import struct
import sys
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[4] / "uned" / "UED22" / "core.dll"


def rva_to_offset(data: bytes, rva: int) -> int:
    pe = data.index(b"PE\0\0")
    coff = pe + 4
    n = struct.unpack_from("<H", data, coff + 2)[0]
    opt_size = struct.unpack_from("<H", data, coff + 16)[0]
    sec = coff + 20 + opt_size
    for i in range(n):
        b = sec + 40 * i
        vsize, vaddr = struct.unpack_from("<II", data, b + 8)
        raw = struct.unpack_from("<I", data, b + 20)[0]
        if vaddr <= rva < vaddr + vsize:
            return raw + (rva - vaddr)
    raise SystemExit(f"RVA {rva:#x} not in any section")


def imports(data: bytes) -> dict[str, list[str]]:
    """{dll: [imported symbol names]} straight out of the PE import directory."""
    pe = data.index(b"PE\0\0")
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    imp_rva = struct.unpack_from("<I", data, opt + (96 if magic == 0x10B else 112) + 8)[0]
    out: dict[str, list[str]] = {}
    d = rva_to_offset(data, imp_rva)
    while True:
        ilt, _ts, _fc, name_rva, iat = struct.unpack_from("<IIIII", data, d)
        if name_rva == 0:
            break
        off = rva_to_offset(data, name_rva)
        dll = data[off:data.index(b"\0", off)].decode("latin-1")
        names: list[str] = []
        t = rva_to_offset(data, ilt or iat)
        while True:
            entry = struct.unpack_from("<I", data, t)[0]
            if entry == 0:
                break
            if entry & 0x80000000:
                names.append(f"#{entry & 0xFFFF}")            # by ordinal
            else:
                o = rva_to_offset(data, entry) + 2
                names.append(data[o:data.index(b"\0", o)].decode("latin-1"))
            t += 4
        out[dll] = names
        d += 20
    return out


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    data = path.read_bytes()
    print(f"== {path} ({len(data)} bytes)\n")

    print("Q1: the UObject::SavePackage string run (UTF-16LE), by file offset")
    for lit in ("UObject::SavePackage", "SaveExports", "SaveImportMap", "SaveExportMap",
                "RewriteSummary", "Save.tmp", "Moving '%s' to '%s'", "Saving %s"):
        raw = lit.encode("utf-16-le")
        print(f"   {data.index(raw):#010x}  {lit!r}" if raw in data else f"   ABSENT     {lit!r}")
    print("   -> serialize into a temp; RewriteSummary patches the header LAST; then move it.\n")

    imp = imports(data)
    fileish = sorted(n for ns in imp.values() for n in ns
                     if any(k in n for k in ("File", "Move", "Copy", "Read", "Write", "Map")))
    print(f"Q2: file-related imports ({sum(len(v) for v in imp.values())} imports over "
          f"{len(imp)} DLLs)")
    for n in fileish:
        print("   ", n)
    absent = [n for n in ("ReadFile", "MoveFileW", "MoveFileExW", "CopyFileW", "CopyFileExW",
                          "CreateFileMappingW", "MapViewOfFile")
              if not any(n in ns for ns in imp.values())]
    print(f"   ABSENT: {', '.join(absent)}")
    print("   -> NOTE the absence of ReadFile: this DLL demonstrably READS packages, so its file")
    print("      I/O does not go through the import table at all. The missing MoveFile*/CopyFile*")
    print("      therefore proves NOTHING about rename-vs-copy. (An earlier revision inferred")
    print("      'therefore it is a copy' from exactly this and had to retract it.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
