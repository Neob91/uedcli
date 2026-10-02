#!/usr/bin/env python3
"""C++/script field OFFSETS of a UE1 native class, computed from the `.u` property lists the way
`UStruct::Link` lays them out (declaration order via the `Children`/`Next` chain, root class first;
consecutive class bools pack into one DWORD bitfield; scalars align to min(size,4); structs align 4).

Anchors that validate the rules (see findings/00-method.md): UED22 `FPathBuilder::buildPaths`
stores Scout `GroundSpeed`/`JumpZ`/`MaxStepHeight` at +0x26c/+0x27c/+0x280, and the 2026-07-15
spike's `upstreamPaths`/`Paths`/`prunedPaths` at NavPt+0x214/+0x254/+0x294.

Usage:  layout.py <ued|dx> <Package.Class> [name-regex]
        layout.py <ued|dx> <Package.Class> --at <hex-offset>    # which field covers this offset
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
from uedcli.uprops import load_package                      # noqa: E402
from uedcli.uprops.uclass import _super_fqcn, class_children_ref, class_export_index  # noqa: E402
from uedcli.uprops.ufield import _decode_property, _field_next, find_struct_export, struct_members  # noqa: E402
from uedcli.uprops.base import PROPERTY_TYPES               # noqa: E402

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import GAME as _GAME, UED22 as _UED22  # noqa: E402
SYSDIRS = {"ued": _UED22, "dx": _GAME / "System"}
_pkgs: dict[str, object] = {}


def pkg_for(which: str, name: str):
    key = (which, name.casefold())
    if key not in _pkgs:
        hits = [p for p in SYSDIRS[which].iterdir() if p.name.casefold() == f"{name.casefold()}.u"]
        if not hits:
            sys.exit(f"package {name} not found in {SYSDIRS[which]}")
        _pkgs[key] = load_package(str(hits[0]), name=name)
    return _pkgs[key]


def own_props_in_order(pkg, class_name: str, owner: str):
    ci = class_export_index(pkg, class_name)
    if ci is None:
        sys.exit(f"class {class_name} not in {pkg.name}")
    node = class_children_ref(pkg, ci)
    out = []
    while node > 0:
        e = pkg.exports[node - 1]
        if pkg.name_of_ref(e["cls"]) in PROPERTY_TYPES:
            out.append(_decode_property(pkg, node, owner))
        node = _field_next(pkg, node)
    return out


def struct_size(which: str, pkg, prop) -> int:
    """Size of a StructProperty element; the struct lives in `prop.type_ref`'s package."""
    if prop.type_ref > 0:
        spkg, sidx = pkg, prop.type_ref
    else:
        # imported struct: find by name in the import's package
        imp = pkg.imports[-prop.type_ref - 1]
        spkg = pkg_for(which, pkg.import_package_name(imp) if hasattr(pkg, "import_package_name") else "Engine")
        sidx = find_struct_export(spkg, prop.type_name)
        if sidx is None:
            spkg = pkg_for(which, "Core")
            sidx = find_struct_export(spkg, prop.type_name)
    members = struct_members(spkg, sidx, owner=prop.type_name)
    size = 0
    for m in members:
        es, al = elem_size(which, spkg, m, in_class=False)
        size = (size + al - 1) // al * al
        size += es * m.array_dim
    return (size + 3) // 4 * 4


def elem_size(which: str, pkg, prop, *, in_class: bool) -> tuple[int, int]:
    k = prop.kind
    if k == "ByteProperty":
        return 1, 1
    if k in ("IntProperty", "FloatProperty", "ObjectProperty", "ClassProperty", "NameProperty", "PointerProperty"):
        return 4, 4
    if k == "BoolProperty":
        return 4, 4
    if k in ("StrProperty", "ArrayProperty"):
        return 12, 4                                # TArray {Data,Num,Max}
    if k == "StringProperty":
        return prop.array_dim, 1                    # fixed char[N] (array_dim carries N)
    if k == "StructProperty":
        return struct_size(which, pkg, prop), 4
    if k in ("MapProperty", "FixedArrayProperty"):
        return 12, 4
    raise SystemExit(f"unknown kind {k} for {prop.name}")


def layout(which: str, fqcn: str) -> tuple[list[tuple[int, int, str, str, int, str]], int]:
    """[(offset, size, name, kind, array_dim, owner)], total size. Bools carry the bit in `kind`."""
    chain = []
    cur = fqcn
    while cur is not None:
        pkg_name, cls = cur.split(".", 1)
        pkg = pkg_for(which, pkg_name)
        chain.append((pkg, cls, cur))
        cur = _super_fqcn(pkg, cls)
    rows = []
    size = 0
    for pkg, cls, owner in reversed(chain):
        prev_bool_bit = None
        for p in own_props_in_order(pkg, cls, owner):
            if p.kind == "BoolProperty":
                if prev_bool_bit is not None and prev_bool_bit < 31:
                    bit = prev_bool_bit + 1
                    off = rows[-1][0]
                    rows.append((off, 0, p.name, f"Bool bit{bit} mask={1 << bit:#x}", 1, owner))
                    prev_bool_bit = bit
                    continue
                size = (size + 3) // 4 * 4
                rows.append((size, 4, p.name, "Bool bit0 mask=0x1", 1, owner))
                prev_bool_bit = 0
                size += 4
                continue
            prev_bool_bit = None
            es, al = elem_size(which, pkg, p, in_class=True)
            size = (size + al - 1) // al * al
            kind = p.kind.replace("Property", "") + (f"<{p.type_name}>" if p.type_name and p.kind in ("StructProperty", "ByteProperty", "ObjectProperty", "ClassProperty") else "")
            rows.append((size, es * p.array_dim, p.name, kind, p.array_dim, owner))
            size += es * p.array_dim
        size = (size + 3) // 4 * 4
    return rows, size


def main(argv):
    which, fqcn = argv[0], argv[1]
    rows, total = layout(which, fqcn)
    if len(argv) > 3 and argv[2] == "--at":
        want = int(argv[3], 16)
        for off, sz, name, kind, dim, owner in rows:
            if off <= want < off + max(sz, 4):
                extra = f" (+{want - off:#x} into it{', elem ' + str((want - off) // (sz // dim)) if dim > 1 and sz else ''})" if want != off else ""
                print(f"{off:#06x} {sz:4d} {name:<28} {kind:<30} [{dim}] {owner}{extra}")
        return
    pat = re.compile(argv[2], re.I) if len(argv) > 2 else None
    print(f"; {which} {fqcn} PropertiesSize={total:#x} ({total})")
    for off, sz, name, kind, dim, owner in rows:
        if pat is None or pat.search(name):
            print(f"{off:#06x} {sz:4d} {name:<28} {kind:<30} [{dim}] {owner}")


if __name__ == "__main__":
    main(sys.argv[1:])
