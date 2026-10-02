"""Native writer for a UE1 object's tagged-property body (`FPropertyTag` list) — the
inverse of the Spike-1 reader (`utexture_decode.read_props`). This closes the
"actor bodies are writable" gap: it proves we can SERIALIZE an actor's properties to
bytes the loader accepts, demonstrated by a write -> read-back round-trip on the
common UE1 property types.

The writer controls the encoding (the loader accepts any valid `FPropertyTag`
encoding — byte-match with the editor is NOT required), so it uses simple canonical
size codes. Property tag layout (per property, then a final `None`):
    Name : ci (name-table index)        # "None" terminates
    Info : u8  bits0-3 type, bits4-6 size code, bit7 array(=bool value for Bool)
    [if Struct] StructName : ci
    [size extension per code: 5->u8, 6->u16, 7->u32]
    [if array and not Bool] array index byte(s)
    value : <size> bytes                # Bool has no value bytes (value is bit7)

Round-trip proof: build a name table + a property set covering Byte/Int/Bool/Float/
Name/Object/Struct, serialize, then parse with the reader and assert values match.
"""
from __future__ import annotations

import struct
import sys

sys.path.insert(0, ".")
from utexture_decode import read_props, ci  # the reader we invert
from package_rw import write_ci

PT_BYTE, PT_INT, PT_BOOL, PT_FLOAT, PT_OBJECT, PT_NAME, PT_STRUCT = 1, 2, 3, 4, 5, 6, 10


def _info(ptype, size_code, array_or_bool):
    return (ptype & 0x0F) | ((size_code & 0x07) << 4) | (0x80 if array_or_bool else 0)


def write_prop(names, name, ptype, value, struct_name=None):
    """Encode one property tag. `names` is the name table (list[str]); name/struct/Name
    values are resolved to indices via it (caller must have added them)."""
    out = bytearray()
    out += write_ci(names.index(name))
    if ptype == PT_BOOL:
        out.append(_info(PT_BOOL, 0, bool(value)))
        return bytes(out)                       # no value bytes; value is bit 7
    if ptype == PT_BYTE:
        out.append(_info(PT_BYTE, 0, False)); out.append(value & 0xFF)
    elif ptype == PT_INT:
        out.append(_info(PT_INT, 2, False)); out += struct.pack("<i", value)
    elif ptype == PT_FLOAT:
        out.append(_info(PT_FLOAT, 2, False)); out += struct.pack("<f", value)
    elif ptype in (PT_NAME, PT_OBJECT):
        body = write_ci(names.index(value)) if ptype == PT_NAME else write_ci(value)
        out.append(_info(ptype, 5, False)); out.append(len(body)); out += body
    elif ptype == PT_STRUCT:
        out.append(_info(PT_STRUCT, 5, False))
        out += write_ci(names.index(struct_name))
        out.append(len(value)); out += value     # value = raw struct bytes
    else:
        raise ValueError(f"unsupported ptype {ptype}")
    return bytes(out)


def write_props(names, props):
    """props: list of (name, ptype, value[, struct_name]). Returns the full body incl.
    the trailing `None`."""
    out = bytearray()
    for p in props:
        out += write_prop(names, *p)
    out += write_ci(names.index("None"))
    return bytes(out)


def main():
    # A point-actor-like property set covering every common type.
    names = ["None", "LightBrightness", "bHidden", "Tag", "DrawScale", "Health",
             "SpikeProbe", "Location", "Vector", "Brush"]
    vec = struct.pack("<3f", 12345.0, 6789.0, -4242.0)   # FVector raw
    props = [
        ("LightBrightness", PT_BYTE, 200),
        ("bHidden", PT_BOOL, True),
        ("Health", PT_INT, 1337),
        ("DrawScale", PT_FLOAT, 2.5),
        ("Tag", PT_NAME, "SpikeProbe"),
        ("Location", PT_STRUCT, vec, "Vector"),
        ("Brush", PT_OBJECT, 7),                 # object ref (export 7)
    ]
    body = write_props(names, props)
    print(f"serialized body = {len(body)} bytes: {body.hex()}")

    got, end = read_props(body, 0, len(body), names)
    print(f"read back {len(got)} props, terminated at {end}/{len(body)}")
    checks = {
        "LightBrightness": got["LightBrightness"][1] == 200,
        "bHidden": got["bHidden"][1] is True,
        "Health": got["Health"][1] == 1337,
        "DrawScale": abs(got["DrawScale"][1] - 2.5) < 1e-6,
        "Tag(name idx)": got["Tag"][1] == names.index("SpikeProbe"),
        "Brush(obj ref)": got["Brush"][1] == 7,
        "Location(struct raw)": got["Location"][1] == vec,
        "terminated-at-EOF": end == len(body),
    }
    allok = all(checks.values())
    for k, v in checks.items():
        print(f"  {'OK ' if v else 'FAIL'} {k}")
    print("ROUND-TRIP:", "PASS" if allok else "FAIL")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
