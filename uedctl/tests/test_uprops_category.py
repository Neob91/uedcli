"""Locks the v68 UProperty body layout RE'd 2026-07-18 (empirical + `Core.dll UProperty::Serialize`
disassembly, both agreeing byte-exact — see `unrealed/class-schema.md`):

    [None term: compact] [SuperField: compact] [Next: compact]
    [ArrayDim: u32] [PropertyFlags: u32] [Category: FName compact]
    [RepOffset: u16 — only if PropertyFlags & CPF_NET] [type tail: compact ref(s)]

The OLD decoder read the leading None-terminator AS "category" (always 0) and mis-offset the header,
so `property_flags` was garbage and `array_dim` wrong for large static arrays. These synthetic bodies
pin the corrected decode without needing the gitignored v68 install.
"""
import struct

from uedctl import uprops


def _pkg(body: bytes, kind: str, names: list[str], *, prop_name="P"):
    """A one-property `uprops.Package`: import 0 names the property KIND (so `cls=-1` resolves to it);
    the property export's body is `body` at offset 0."""
    all_names = list(names)
    if kind not in all_names:
        all_names.append(kind)
    if prop_name not in all_names:
        all_names.append(prop_name)
    imports = [(0, 0, 0, all_names.index(kind))]         # import[-1] → ObjectName = the kind
    exports = [{"cls": -1, "sup": 0, "outer": 0, "nm": all_names.index(prop_name),
                "flags": 0, "ssize": len(body), "soff": 0}]
    return uprops.Package(name="T", version=68, names=all_names, imports=imports,
                          exports=exports, buf=body)


def _cidx(v: int) -> bytes:
    """FCompactIndex for a small non-negative index (< 64 → single byte)."""
    assert 0 <= v < 64
    return bytes([v])


def _body(*, array_dim: int, flags: int, category_idx: int, names: list[str],
           rep_offset: bool = False, tail: bytes = b"") -> bytes:
    b = _cidx(0) + _cidx(0) + _cidx(0)                   # None term, SuperField, Next
    b += struct.pack("<I", array_dim) + struct.pack("<I", flags)
    b += _cidx(category_idx)
    if rep_offset:
        b += struct.pack("<H", 208)                     # a RepOffset value (only present if CPF_NET)
    return b + tail


def test_decodes_category_arraydim_and_full_flags():
    names = ["None", "Movement"]
    body = _body(array_dim=1, flags=0x1, category_idx=names.index("Movement"), names=names)
    pkg = _pkg(body, "FloatProperty", names, prop_name="Mass")
    p = uprops._decode_property(pkg, 1, "Engine.Actor")
    assert p.category == "Movement"
    assert p.array_dim == 1
    assert p.property_flags == 0x1                        # FULL 32-bit flags (old decode was garbage)


def test_large_static_array_dim():
    names = ["None", "AI"]
    body = _body(array_dim=32, flags=0x0, category_idx=names.index("AI"), names=names)
    pkg = _pkg(body, "ObjectProperty", names, prop_name="PRIArray")
    p = uprops._decode_property(pkg, 1, "Engine.TeamInfo")
    assert p.array_dim == 32                              # the old `>>16 & 0xFF` hack read this as 1
    assert p.category == "AI"


def test_no_explicit_category_is_none():
    names = ["None"]
    body = _body(array_dim=1, flags=0x0, category_idx=0, names=names)   # category name-index 0 == None
    pkg = _pkg(body, "IntProperty", names, prop_name="numThings")
    p = uprops._decode_property(pkg, 1, "X.Y")
    assert p.category is None


def test_cpf_net_repoffset_is_skipped_before_the_type_tail():
    # A StructProperty with CPF_NET set: a 2-byte RepOffset sits between Category and the Struct ref.
    # The decode must skip it so type_ref reads the real tail, not the RepOffset bytes.
    names = ["None", "Movement", "Vector", "Velocity", "StructProperty"]
    tail = _cidx(2)                                      # a positive export ref → export[2] ("Vector")
    body = _body(array_dim=1, flags=uprops.CPF_NET, category_idx=names.index("Movement"),
                 names=names, rep_offset=True, tail=tail)
    exports = [
        {"cls": -1, "sup": 0, "outer": 0, "nm": names.index("Velocity"),   # export 1: the property
         "flags": 0, "ssize": len(body), "soff": 0},
        {"cls": 0, "sup": 0, "outer": 0, "nm": names.index("Vector"),      # export 2: the referenced struct
         "flags": 0, "ssize": 0, "soff": 0},
    ]
    pkg = uprops.Package(name="T", version=68, names=names,
                         imports=[(0, 0, 0, names.index("StructProperty"))],  # import 0 → the kind
                         exports=exports, buf=body)
    p = uprops._decode_property(pkg, 1, "Engine.Actor")
    assert p.category == "Movement"
    assert p.property_flags == uprops.CPF_NET
    assert p.type_name == "Vector"                       # tail read correctly PAST the RepOffset
