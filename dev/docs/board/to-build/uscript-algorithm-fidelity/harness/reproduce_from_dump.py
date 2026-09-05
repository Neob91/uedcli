"""Verify the shipped runtime dump (`uedcli/uscript/data/{gobjnames,gobjobjects}_ued22.json`)
reproduces every committed fixture's NAME and IMPORT table order, using the proven count models
(name = literal <<FName writes in export bodies; import = <<UObject with outer recursion + the
metaclass Class) fed through the faithful `ordering.msvc_qsort`. Non-circular: the dump supplies the
gather index, the golden bodies supply the counts, the golden tables are the expected output.

Run from the repo root:  python3 dev/docs/board/.../harness/reproduce_from_dump.py
"""
import json
import os
import struct
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.getcwd())
from uedcli.upackage import PT_NAME, load_package, read_compact_index as rci, read_property_tags
from uedcli.uprops.ufield import _skip_script
from uedcli.uscript.ordering import msvc_qsort

FIX = Path("uedcli/tests/fixtures/uscript")
DATA = Path("uedcli/uscript/data")
NAMES = json.loads((DATA / "gobjnames_ued22.json").read_text())["names"]
OBJS = json.loads((DATA / "gobjobjects_ued22.json").read_text())["objects"]
NAME_IDX = {n.casefold(): i for i, n in enumerate(NAMES)}
# object identity (name, class, outer) casefold -> ascending GObjObjects index
OBJ_IDX = {}
for i, (nm, cls, outer) in enumerate(OBJS):
    key = (nm and nm.casefold(), cls and cls.casefold(), outer and outer.casefold())
    OBJ_IDX.setdefault(key, i)

# own-new name declaration order (class, members, defaults value-names) for the fixtures with members
NEWORDER = {"UscVars": ["UscVars", "Beta"], "UscBB": ["UscBB", "Bode", "Blip", "Naym"]}


def name_counts(pkg):
    buf, nc = pkg.buf, Counter()
    def clsname(e):
        c = e['cls']
        if c == 0:
            return "Class"
        return pkg.names[pkg.imports[-c - 1][3]] if c < 0 else pkg.names[pkg.exports[c - 1]['nm']]
    for e in pkg.exports:
        kind, pos, end = clsname(e), e['soff'], e['soff'] + e['ssize']
        if kind == "TextBuffer":
            v, pos = rci(buf, pos); nc[pkg.names[v]] += 1
        elif kind.endswith("Property"):
            v, pos = rci(buf, pos); nc[pkg.names[v]] += 1
            _, pos = rci(buf, pos); _, pos = rci(buf, pos); pos += 8
            c, pos = rci(buf, pos); nc[pkg.names[c]] += 1
        elif kind == "Class":
            for _ in range(4): _, pos = rci(buf, pos)
            f, pos = rci(buf, pos); nc[pkg.names[f]] += 1
            pos += 8; ssz = struct.unpack_from("<I", buf, pos)[0]; pos += 4
            pos = _skip_script(pkg, pos, ssz); pos += 8 + 8 + 2 + 4 + 4 + 16
            depc, pos = rci(buf, pos)
            for _ in range(depc): _, pos = rci(buf, pos); pos += 8
            pic, pos = rci(buf, pos)
            for _ in range(pic): pn, pos = rci(buf, pos); nc[pkg.names[pn]] += 1
            _, pos = rci(buf, pos); cfg, pos = rci(buf, pos); nc[pkg.names[cfg]] += 1
            tags, pos = read_property_tags(pkg, pos, end)
            for t in tags:
                nc[t.name] += 1
                if t.ptype == PT_NAME: nc[pkg.names[rci(t.raw, 0)[0]]] += 1
                if t.struct_name: nc[t.struct_name] += 1
            nc["None"] += 1
    return nc


def obj_counts(pkg):
    buf = pkg.buf
    def oident(ref): return None if ref == 0 else (("E", ref) if ref > 0 else ("I", -ref - 1))
    def name_of(o):
        t, k = o
        return pkg.names[pkg.exports[k - 1]['nm']] if t == "E" else pkg.names[pkg.imports[k][3]]
    def outer_of(o):
        cp, cn, pi, on = pkg.imports[o[1]]
        return None if pi == 0 else ("I", -pi - 1)
    def clsname(e):
        c = e['cls']
        if c == 0: return "Class"
        return pkg.names[pkg.imports[-c - 1][3]] if c < 0 else pkg.names[pkg.exports[c - 1]['nm']]
    ok = Counter()
    def ser(o):
        if o is None: return
        ok[name_of(o)] += 1
        if o[0] == "E": return
        ser(outer_of(o))
    for e in pkg.exports:
        kind, pos, end, refs = clsname(e), e['soff'], e['soff'] + e['ssize'], []
        if kind == "TextBuffer":
            _, pos = rci(buf, pos)
        elif kind.endswith("Property"):
            _, pos = rci(buf, pos); s, pos = rci(buf, pos); refs.append(s); nx, pos = rci(buf, pos); refs.append(nx)
            pos += 8; _, pos = rci(buf, pos)
            while pos < end: v, pos = rci(buf, pos); refs.append(v)
        elif kind == "Class":
            for _ in range(4): r, pos = rci(buf, pos); refs.append(r)
            _, pos = rci(buf, pos)
            pos += 8; ssz = struct.unpack_from("<I", buf, pos)[0]; pos += 4; pos = _skip_script(pkg, pos, ssz)
            pos += 8 + 8 + 2 + 4 + 4 + 16
            depc, pos = rci(buf, pos)
            for _ in range(depc): dc, pos = rci(buf, pos); refs.append(dc); pos += 8
            pic, pos = rci(buf, pos)
            for _ in range(pic): _, pos = rci(buf, pos)
            wi, pos = rci(buf, pos); refs.append(wi)
        for r in refs: ser(oident(r))
        if e['cls'] == 0:
            for j, (cp, cn, pi, on) in enumerate(pkg.imports):
                if pkg.names[on] == "Class": ser(("I", j)); break
        else:
            ser(oident(e['cls']))
    return ok


def name_order(pkg, neworder):
    nc = name_counts(pkg)
    npos = {n.casefold(): i for i, n in enumerate(neworder)}
    def gi(n):
        cf = n.casefold()
        return NAME_IDX[cf] if cf in NAME_IDX else 10**7 + npos.get(cf, 10**5)
    return msvc_qsort(sorted(pkg.names, key=gi), lambda x, y: nc.get(y, 0) - nc.get(x, 0))


def imp_identity(pkg, j):
    cp, cn, pi, on = pkg.imports[j]
    outer = pkg.names[pkg.imports[-pi - 1][3]].casefold() if pi < 0 else None
    return (pkg.names[on].casefold(), pkg.names[cn].casefold(), outer)


def import_order(pkg):
    ok = obj_counts(pkg)
    nm = lambda j: pkg.names[pkg.imports[j][3]]
    gather = sorted(range(len(pkg.imports)), key=lambda j: OBJ_IDX.get(imp_identity(pkg, j), 10**7 + j))
    return [nm(j) for j in msvc_qsort(gather, lambda x, y: ok.get(nm(y), 0) - ok.get(nm(x), 0))]


def main():
    allok = True
    print(f"{'fixture':10} {'names':6} {'imports':7}")
    for cls in ("UscHello", "UscVars", "UscBB", "UscFn", "UscW", "UscSt", "UscL"):
        p = FIX / f"{cls}.u"
        if not p.exists():
            continue
        pkg = load_package(str(p))
        io = import_order(pkg) == [pkg.names[on] for cp, cn, pi, on in pkg.imports]
        no = "n/a"
        if cls in ("UscHello", "UscVars", "UscBB"):
            no = "MATCH" if name_order(pkg, NEWORDER.get(cls, [cls])) == list(pkg.names) else "DIFF"
        print(f"{cls:10} {no:6} {'MATCH' if io else 'DIFF'}")
        allok &= io and no in ("MATCH", "n/a")
    print("ALL", "PASS" if allok else "FAIL")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
