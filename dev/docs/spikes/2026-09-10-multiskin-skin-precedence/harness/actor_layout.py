"""Lay out `Engine.Actor`'s own properties in the order the `.u` stores them, with C-struct
alignment.

**Negative result, kept so nobody repeats it:** a class's `Children` chain in the `.u` is NOT the
declaration order the C++ header uses, so this does not reproduce the DLL's field offsets — it puts
`MultiSkins` at 0xa4 where `AActor::GetSkin` reads 0x164. Recover the layout from the class's stored
SOURCE instead (`dump_script.py`), which is what the spike's offset table is built on.

    python3 actor_layout.py <path-to-Engine.u> [start_offset_of_first_own_prop]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from uedcli.upackage import load_package  # noqa: E402
from uedcli.uprops.uclass import own_class_properties  # noqa: E402

# (size, alignment) of one element of each UProperty kind in the UE1 C++ layout.
SIZES = {
    "ByteProperty": (1, 1),
    "IntProperty": (4, 4),
    "BoolProperty": (4, 4),          # DWORD bitfield word (a run of bools shares one)
    "FloatProperty": (4, 4),
    "ObjectProperty": (4, 4),
    "NameProperty": (4, 4),
    "StrProperty": (12, 4),
    "StringProperty": (16, 4),       # fixed-size char array (UE1 legacy)
    "ArrayProperty": (12, 4),
    "MapProperty": (60, 4),
    "ClassProperty": (4, 4),
    "DelegateProperty": (12, 4),
}
STRUCTS = {  # struct sizes needed for Actor's own list
    "Vector": (12, 4),
    "Rotator": (12, 4),
    "Color": (4, 4),
    "Plane": (16, 4),
    "Coords": (48, 4),
    "Scale": (20, 4),
    "PointRegion": (12, 4),
    "Region": (12, 4),
}


def main() -> None:
    pkg = load_package(sys.argv[1])
    props = own_class_properties(pkg, "Actor", owner_fqcn="Engine.Actor")
    off = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0
    bool_word = None  # (offset, bits_used) of the DWORD a bool run packs into
    for p in props:
        if p.kind == "StructProperty":
            size, align = STRUCTS.get(p.type_name or "", (0, 4))
            if not size:
                print(f"  !! unknown struct {p.type_name} — layout beyond here is wrong")
        else:
            size, align = SIZES.get(p.kind, (0, 4))
            if not size:
                print(f"  !! unknown kind {p.kind}")
        if p.kind == "BoolProperty":
            if bool_word is not None and bool_word[1] < 32 and p.array_dim == 1:
                print(f"  {bool_word[0]:#06x}  {p.name} (bit {bool_word[1]})")
                bool_word = (bool_word[0], bool_word[1] + 1)
                continue
            off = (off + 3) & ~3
            bool_word = (off, 1)
            print(f"  {off:#06x}  {p.name} (bit 0)")
            off += 4
            continue
        bool_word = None
        off = (off + align - 1) & ~(align - 1)
        print(f"  {off:#06x}  {p.name}  [{p.kind}{'' if p.array_dim == 1 else f'[{p.array_dim}]'}]")
        off += size * p.array_dim


if __name__ == "__main__":
    main()
