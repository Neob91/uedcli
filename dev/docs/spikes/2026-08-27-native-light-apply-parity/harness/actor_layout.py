"""Recover the in-memory field offsets (and bool bit positions) of an UnrealScript class from a `.u`.

Why: `Editor.dll`'s light-gather pass tests raw actor offsets (`[actor+0x28] & 5`,
`[actor+0x11c] & 4`, `[actor+0x1a8] & 1`). Naming them needs the AActor field layout, and
`UProperty::Offset` is NOT serialized — UE1 recomputes it in `UStruct::Link`. This replays that
layout: walk the class's fields in DECLARATION order (the `UField.Next` chain, since the export
table order is not declaration order), lay each property out at `Align(prev_end, align)`, and pack
runs of consecutive `BoolProperty`s into one 32-bit bitfield (mask `1<<n`, a new dword when the run
would overflow 32) — which is what `UBoolProperty::Link` does.

Trust check: the printed offsets must reproduce the three anchors read independently out of the
disassembly — `Location = 0xd0` (`Editor.dll` 0x100a59cc reads `[light+0xd0/0xd4/0xd8]` as the light
position), `LightType = 0x19c` (0x100a4cc7), `LightRadius = 0x1a1`. `--check` asserts them.

Usage:
    python actor_layout.py            # AActor, full table
    python actor_layout.py --check    # anchors only, exit 1 on mismatch
    ENGINE_U=/path/to/Engine.u python actor_layout.py
"""
import os
import sys

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                 "..", "..", "..", "..", "..")))

from uedcli.upackage import load_package, read_compact_index
from uedcli.uprops.base import PROPERTY_TYPES
from uedcli.uprops.ufield import _decode_property, find_struct_export, struct_members
from uedcli.uprops.uclass import class_export_index

ENGINE_U = os.environ.get("ENGINE_U") or os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "..", "..", "..", "..", "..", "uned", "UED22", "Engine.u"))

# sizeof(UObject) in this build: vtable + HashNext + StateFrame + _Linker + _LinkerIndex + Index
# + Outer + ObjectFlags + Name + Class = 10 dwords. Validated by the anchors above.
UOBJECT_SIZE = 0x28

FIXED = {"IntProperty": (4, 4), "FloatProperty": (4, 4), "ObjectProperty": (4, 4),
         "ClassProperty": (4, 4), "NameProperty": (4, 4), "PointerProperty": (4, 4),
         "ByteProperty": (1, 1), "StrProperty": (12, 4), "ArrayProperty": (12, 4),
         "BoolProperty": (4, 4)}

# Structs declared in Core's Object.uc, so absent from Engine.u: (size, align).
CORE_STRUCTS = {"Vector": (12, 4), "Plane": (16, 4), "Rotator": (12, 4), "Coords": (48, 4),
                "Scale": (20, 4), "Color": (4, 1), "Quat": (16, 4), "Range": (8, 4),
                "RangeVector": (24, 4), "Box": (28, 4), "BoundingVolume": (44, 4),
                "Matrix": (64, 4)}

ANCHORS = {"Location": 0xD0, "LightType": 0x19C, "LightRadius": 0x1A1}


def align_up(x, a):
    return (x + a - 1) // a * a


def struct_size(pkg, name, depth=0):
    si = find_struct_export(pkg, name)
    if si is None or depth > 6:
        return None
    end, align = 0, 1
    for m in struct_members(pkg, si, owner=name):
        sz, al = elem_size_align(pkg, m, depth + 1)
        if sz is None:
            return None
        end = align_up(end, al) + sz * m.array_dim
        align = max(align, al)
    return align_up(end, align), align


def elem_size_align(pkg, prop, depth=0):
    if prop.kind == "StructProperty":
        if prop.type_name in CORE_STRUCTS:                # declared in Core, not in this package
            return CORE_STRUCTS[prop.type_name]
        return struct_size(pkg, prop.type_name, depth) or (None, None)
    return FIXED.get(prop.kind, (None, None))


def field_next(pkg, idx1):
    e = pkg.exports[idx1 - 1]
    buf, p = pkg.buf, e["soff"]
    _none, p = read_compact_index(buf, p)
    _sup, p = read_compact_index(buf, p)
    nxt, _p = read_compact_index(buf, p)
    return nxt


def ordered_fields(pkg, class_name):
    """The class's own fields in declaration order. The `Next` chain of a UClass's children is
    split into several runs (functions/enums/structs interleave), so every run is walked and the
    runs are emitted in export order of their heads — which is declaration order here."""
    ci = class_export_index(pkg, class_name)
    kids = {i + 1 for i, e in enumerate(pkg.exports) if e["outer"] == ci}
    nexts = {i: field_next(pkg, i) for i in kids}
    heads = sorted(kids - {n for n in nexts.values() if n in kids})
    out = []
    for h in heads:
        cur = h
        while cur in kids and cur not in out:
            out.append(cur)
            cur = nexts[cur]
    return [(i, pkg.name_of_ref(pkg.exports[i - 1]["cls"])) for i in out]


def layout(pkg, class_name, start, verbose=True):
    off, bool_off, bool_bit = start, None, 0
    found = {}
    for idx1, kind in ordered_fields(pkg, class_name):
        if kind not in PROPERTY_TYPES:
            continue
        p = _decode_property(pkg, idx1, class_name)
        if kind == "BoolProperty":
            if bool_off is None or bool_bit >= 32:
                bool_off, bool_bit = align_up(off, 4), 0
                off = bool_off + 4
            if verbose:
                print(f"  +{bool_off:#05x}  bit {bool_bit:<2} mask {1 << bool_bit:#010x}  {p.name}")
            found[p.name] = (bool_off, 1 << bool_bit)
            bool_bit += 1
            continue
        bool_off = None
        sz, al = elem_size_align(pkg, p)
        if sz is None:
            print(f"  !! unknown size: {kind} {p.type_name} {p.name}")
            return None, found
        off = align_up(off, al)
        found[p.name] = (off, None)
        if verbose:
            dim = "" if p.array_dim == 1 else f"[{p.array_dim}]"
            print(f"  +{off:#05x}  size {sz * p.array_dim:<3} {kind[:-8].lower():7}{p.name}{dim}")
        off += sz * p.array_dim
    return off, found


if __name__ == "__main__":
    check = "--check" in sys.argv
    pkg = load_package(ENGINE_U, name="Engine")
    end, found = layout(pkg, "Actor", UOBJECT_SIZE, verbose=not check)
    print(f"sizeof(AActor) = {end:#x}")
    bad = [(n, hex(v), hex(found[n][0])) for n, v in ANCHORS.items() if found[n][0] != v]
    print("anchors:", "OK" if not bad else f"MISMATCH {bad}")
    for n in ("bStatic", "bNoDelete", "bLightChanged", "bHiddenEd", "bSelected", "bSpecialLit"):
        o, m = found[n]
        print(f"  {n:14} +{o:#05x} mask {m:#x}")
    sys.exit(1 if bad else 0)
