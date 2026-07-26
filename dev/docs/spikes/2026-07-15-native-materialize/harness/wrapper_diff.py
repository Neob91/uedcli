#!/usr/bin/env python3
"""PACKAGE-WRAPPER byte-parity diff: native `.dx` vs UnrealEd `.dx`.

Compares the UE1 package WRAPPER — header, name table, import table, export table
(the object map) and generations — field-by-field, EXCLUDING the random GUID and any
save timestamp. The Model geometry BODY (BSP tree order) is out of scope (tracked
separately); this harness only judges the serialization AROUND the objects.

For each table it prints: counts, per-entry decoded tuples, and the first divergence.
Entries are matched by a stable identity key (name/import-identity/export-identity) so
ORDER differences are reported explicitly rather than smeared across a positional diff.

Usage:
  python wrapper_diff.py [NATIVE.dx] [EDITOR.dx]
Defaults: _scratch/NativeCastle_wrapper.dx  vs  DX/Maps/Test_Castle.dx
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
sys.path.insert(0, str(ROOT))

import struct  # noqa: E402

from uedcli.native.pkg_write import parse_package, ParsedPackage  # noqa: E402


def read_generations(buf: bytes):
    """The v>=68 header tail: FGuid(16) + u32 gencount + gencount*(u32 exp, u32 name)."""
    ver_l, = struct.unpack_from("<I", buf, 4)
    if (ver_l & 0xFFFF) < 68:
        return None
    pos = 36 + 16
    gencount, = struct.unpack_from("<I", buf, pos); pos += 4
    gens = [struct.unpack_from("<II", buf, pos + 8 * i) for i in range(gencount)]
    return gens

NATIVE = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/NativeCastle_wrapper.dx"
EDITOR = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx"


def load(path: str) -> ParsedPackage:
    return parse_package(Path(path).read_bytes())


def imp_path(p: ParsedPackage, j: int) -> str:
    """Resolve an import to its fully-qualified identity: ClassPackage.ClassName 'outerchain.Name'."""
    cp, cn, pi, on = p.imports[j]
    chain = []
    ref = pi
    while ref < 0:
        k = -ref - 1
        chain.append(p.names[p.imports[k][3]])
        ref = p.imports[k][2]
    outer = ".".join(reversed(chain))
    who = f"{outer}.{p.names[on]}" if outer else p.names[on]
    return f"{p.names[cp]}.{p.names[cn]} '{who}'"


def exp_identity(p: ParsedPackage, i: int) -> str:
    """Export identity: Class + full outer-chain name (order-independent key)."""
    e = p.exports[i]
    chain = []
    outer = e["outer"]
    while outer > 0:
        oe = p.exports[outer - 1]
        chain.append(p.names[oe["nm"]])
        outer = oe["outer"]
    prefix = ".".join(reversed(chain))
    nm = p.names[e["nm"]]
    full = f"{prefix}.{nm}" if prefix else nm
    return f"{p.class_of_export(i) or '<Class>'} {full}"


SEP = "=" * 78


def hdr(nat: ParsedPackage, ed: ParsedPackage):
    print(SEP); print("HEADER")
    def row(label, a, b):
        mark = "  " if a == b else "!!"
        print(f"  {mark} {label:<18} native={a!r:<24} editor={b!r}")
    row("version", nat.version, ed.version)
    row("licensee", nat.licensee, ed.licensee)
    row("package_flags", hex(nat.flags), hex(ed.flags))
    row("name_count", len(nat.names), len(ed.names))
    row("import_count", len(nat.imports), len(ed.imports))
    row("export_count", len(nat.exports), len(ed.exports))
    ng = read_generations(nat.buf); eg = read_generations(ed.buf)
    row("generations", ng, eg)
    print(f"     (guid excluded: native={nat.guid.hex() if nat.guid else None} "
          f"editor={ed.guid.hex() if ed.guid else None})")
    print("     NOTE: generations SHOULD differ — each is (final export_count, name_count),")
    print("           which track the (unreproducible) editor object/name set, not the wrapper codec.")


def names(nat: ParsedPackage, ed: ParsedPackage):
    print(SEP); print(f"NAME TABLE  native={len(nat.names)}  editor={len(ed.names)}")
    ns, es = nat.names, ed.names
    # set diff
    only_nat = [n for n in ns if n not in set(es)]
    only_ed = [n for n in es if n not in set(ns)]
    print(f"  names only in native ({len(only_nat)}): {only_nat}")
    print(f"  names only in editor ({len(only_ed)}): {only_ed}")
    # order diff on the common prefix
    firstdiff = None
    for i in range(min(len(ns), len(es))):
        if ns[i] != es[i]:
            firstdiff = i; break
    if firstdiff is None and len(ns) == len(es):
        print("  ORDER: identical")
    else:
        print(f"  ORDER: first divergence at index {firstdiff}")
        lo = 0 if firstdiff is None else max(0, firstdiff - 2)
        for i in range(lo, min(max(len(ns), len(es)), (firstdiff or 0) + 12)):
            a = ns[i] if i < len(ns) else "<none>"
            b = es[i] if i < len(es) else "<none>"
            mark = "  " if a == b else "!!"
            print(f"     {mark} [{i:3}] native={a!r:<22} editor={b!r}")


def imports(nat: ParsedPackage, ed: ParsedPackage):
    print(SEP); print(f"IMPORT TABLE  native={len(nat.imports)}  editor={len(ed.imports)}")
    npaths = [imp_path(nat, j) for j in range(len(nat.imports))]
    epaths = [imp_path(ed, j) for j in range(len(ed.imports))]
    only_nat = [x for x in npaths if x not in set(epaths)]
    only_ed = [x for x in epaths if x not in set(npaths)]
    print(f"  imports only in native ({len(only_nat)}):")
    for x in only_nat: print(f"       + {x}")
    print(f"  imports only in editor ({len(only_ed)}):")
    for x in only_ed: print(f"       - {x}")
    # order
    firstdiff = next((i for i in range(min(len(npaths), len(epaths)))
                      if npaths[i] != epaths[i]), None)
    if firstdiff is None and len(npaths) == len(epaths):
        print("  ORDER: identical")
    else:
        print(f"  ORDER: first divergence at import index {firstdiff}")
        lo = 0 if firstdiff is None else max(0, firstdiff - 2)
        for i in range(lo, min(max(len(npaths), len(epaths)), (firstdiff or 0) + 14)):
            a = npaths[i] if i < len(npaths) else "<none>"
            b = epaths[i] if i < len(epaths) else "<none>"
            mark = "  " if a == b else "!!"
            print(f"     {mark} [{i:3}] N: {a}")
            print(f"     {mark}       E: {b}")


def exports(nat: ParsedPackage, ed: ParsedPackage):
    print(SEP); print(f"EXPORT TABLE  native={len(nat.exports)}  editor={len(ed.exports)}")
    nid = [exp_identity(nat, i) for i in range(len(nat.exports))]
    eid = [exp_identity(ed, i) for i in range(len(ed.exports))]
    only_nat = [x for x in nid if x not in set(eid)]
    only_ed = [x for x in eid if x not in set(nid)]
    print(f"  exports only in native ({len(only_nat)}):")
    for x in only_nat[:40]: print(f"       + {x}")
    print(f"  exports only in editor ({len(only_ed)}):")
    for x in only_ed[:40]: print(f"       - {x}")
    # order
    firstdiff = next((i for i in range(min(len(nid), len(eid))) if nid[i] != eid[i]), None)
    if firstdiff is None and len(nid) == len(eid):
        print("  ORDER: identical")
    else:
        print(f"  ORDER: first divergence at export index {firstdiff}")
        lo = 0 if firstdiff is None else max(0, firstdiff - 2)
        for i in range(lo, min(max(len(nid), len(eid)), (firstdiff or 0) + 16)):
            a = nid[i] if i < len(nid) else "<none>"
            b = eid[i] if i < len(eid) else "<none>"
            mark = "  " if a == b else "!!"
            print(f"     {mark} [{i:3}] N: {a}")
            print(f"     {mark}       E: {b}")
    # per-export field encoding for the matched (by identity) exports
    print("  FIELD ENCODING (exports matched by identity, excl. serial_offset):")
    eidx = {x: i for i, x in enumerate(eid)}
    fld_diffs = 0
    for i, x in enumerate(nid):
        if x not in eidx:
            continue
        j = eidx[x]
        en, ee = nat.exports[i], ed.exports[j]
        if en["flags"] != ee["flags"] or en["ssize"] != ee["ssize"]:
            fld_diffs += 1
            if fld_diffs <= 40:
                fl = "" if en["flags"] == ee["flags"] else \
                     f" flags N={en['flags']:#010x} E={ee['flags']:#010x}"
                sz = "" if en["ssize"] == ee["ssize"] else \
                     f" ssize N={en['ssize']} E={ee['ssize']}"
                print(f"     !! {x}{fl}{sz}")
    if fld_diffs == 0:
        print("     all matched exports agree on flags + ssize")
    else:
        print(f"     ({fld_diffs} matched exports differ on flags/ssize)")


def export_flags_by_class(nat: ParsedPackage, ed: ParsedPackage):
    """The tree-INDEPENDENT parity slice: per-class export flags must match the editor's
    convention (independent of object naming/order/count)."""
    print(SEP); print("EXPORT FLAGS BY CLASS  (the tree-independent parity slice)")

    def collect(p):
        from collections import defaultdict
        d = defaultdict(set)
        models = [i for i in range(len(p.exports)) if p.class_of_export(i) == "Model"]
        bsp = max(models, key=lambda i: p.exports[i]["ssize"]) if models else -1
        for i in range(len(p.exports)):
            cl = p.class_of_export(i)
            key = "Model(level-BSP)" if i == bsp else cl
            d[key].add(p.exports[i]["flags"])
        return d
    dn, de = collect(nat), collect(ed)
    for k in sorted(set(dn) | set(de), key=str):
        a = sorted(hex(x) for x in dn.get(k, set()))
        b = sorted(hex(x) for x in de.get(k, set()))
        mark = "  " if dn.get(k) == de.get(k) else ("~~" if k not in dn or k not in de else "!!")
        print(f"  {mark} {str(k):<18} native={a!s:<24} editor={b}")
    print("  (~~ = class present in only one file — editor-only Camera/LevelSummary etc.)")


def residual_summary():
    print(SEP); print("RESIDUAL CLASSIFICATION")
    print("""  FIXED (tree-independent, now matches the editor):
    - Brush actor export flags        0x02070001 -> 0x02340001  (edit-only actor)
    - CSG brush-shape Polys flags     0x00340001 -> 0x00070000  (load-all, no Transactional)

  FUNDAMENTALLY UNREPRODUCIBLE from the trunk (session-encoded editor state; NOT a
  writer bug — the header GUID/timestamps are the same category):
    - Name-TABLE ORDER: the editor writes names in its process-global FName-pool order
      (hardcoded EName prefix, then per-object names in editor object-creation order).
      The object-name suffix + interleave reflect the whole edit session, not the trunk.
    - Object NUMBERING: `Polys176`,`Polys178`,... `Camera6`,`Brush1`,`Model2` — the numeric
      suffix is a session-global UObject counter; the trunk carries no such counter, so a
      from-scratch build cannot reproduce the exact numbers (native uses `Model_<brush>Polys`).
    - EDITOR-ONLY ACTORS: 6 `Camera` viewport actors + `LevelSummary` + editor camera state
      are saved by UnrealEd from its live viewport/browser session; the trunk has none.
    - LevelInfo singleton name: editor `LevelInfo0` vs trunk-carried `LevelInfo_<id>`.
    - Header FileVersion: editor 69 vs native 68 (caller-set in build_native_castle.py;
      the on-disk shape is identical — pass version=69 to match, load-bearing so left to caller).

  DERIVABLE-BUT-DEFERRED (would need an assemble.py re-layout; still cannot byte-match while
  the set/numbering differ, so not worth the regression risk):
    - Export ORDER: editor = actors in placement order, then Model/Polys pairs, LevelSummary,
      MyLevel last; native = LevelInfo, default brush, CSG(polys+model+actor)*, point actors,
      level Model, MyLevel.
    - Import ORDER + texture-group casing (`CoreTexSky.sky` vs `.Sky`).""")


def main():
    nat_p = sys.argv[1] if len(sys.argv) > 1 else NATIVE
    ed_p = sys.argv[2] if len(sys.argv) > 2 else EDITOR
    print(f"NATIVE: {nat_p}")
    print(f"EDITOR: {ed_p}")
    nat, ed = load(nat_p), load(ed_p)
    hdr(nat, ed)
    names(nat, ed)
    imports(nat, ed)
    exports(nat, ed)
    export_flags_by_class(nat, ed)
    residual_summary()


if __name__ == "__main__":
    main()
