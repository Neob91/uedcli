"""Compute UCC's true name/import/export table order for an already-compiled package by DECODING
its object bodies into the `<<FName` / `<<UObject` reference streams the save-time tag pass counts,
then running the RE'd `order_package` (dumped global-index gather + faithful `msvc_qsort`).

The compiler emits the package once in any valid provisional order; this re-derives the real order
from the bytes (stream membership + counts are order-independent) and the caller re-emits with it. No
fitted tables: the streams come straight from the serialized bodies (`serialize.py` layouts, reversed),
the tie-break from `data/gobjnames_ued22.json` / `gobjobjects_ued22.json`.
"""
from __future__ import annotations

import struct

from ..upackage import (PT_NAME, PT_OBJECT, PT_STRUCT, _parse_package, read_compact_index as _rci,
                        read_fstring, read_property_tags)
from .bytecode import decode_script
from .global_index import default_global_index
from .ordering import ObjInput, order_package

_PROP_KINDS = frozenset({"ByteProperty", "IntProperty", "BoolProperty", "FloatProperty",
                         "ObjectProperty", "NameProperty", "StringProperty", "StrProperty",
                         "ClassProperty", "ArrayProperty", "StructProperty", "VectorProperty",
                         "RotatorProperty", "MapProperty", "FixedArrayProperty", "PointerProperty",
                         "DelegateProperty"})


class _Decoder:
    def __init__(self, u: bytes) -> None:
        self.p = _parse_package(u, "<reorder>", "reorder")
        self.buf = self.p.buf
        self.class_i = next(i for i, e in enumerate(self.p.exports) if e["cls"] == 0)

    # ── identities ──
    def ekey(self, i0: int) -> str:
        return f"E{i0}"

    def edisp(self, i0: int) -> str:
        return self.p.names[self.p.exports[i0]["nm"]]

    def idisp(self, j: int) -> str:
        return self.p.names[self.p.imports[j][3]]

    def ename(self, idx: int) -> str:
        return self.p.names[idx]

    def objkey(self, ref: int) -> str | None:
        """A ref's identity for `obj_refs`: an export KEY, an import DISPLAY name, or None (ref 0)."""
        if ref == 0:
            return None
        if ref > 0:
            return self.ekey(ref - 1)
        return self.idisp(-ref - 1)

    def outer_disp(self, outer_ref: int) -> str | None:
        if outer_ref <= 0:
            return None
        return self.edisp(outer_ref - 1)

    def outer_chain(self, i0: int) -> tuple[str, ...]:
        """Outer display names outermost->immediate (e.g. a param's (Class, Function)). Disambiguates
        a leaf whose immediate outer name repeats across classes (two `Build().ReturnValue`)."""
        chain, outer = [], self.p.exports[i0]["outer"]
        for _ in range(64):
            if outer <= 0:
                break
            chain.append(self.edisp(outer - 1))
            outer = self.p.exports[outer - 1]["outer"]
        return tuple(reversed(chain))

    def class_disp(self, i0: int) -> str:
        """The export's class DISPLAY name (an import: IntProperty/Function/Class/…). For the UClass
        (on-disk cls 0) the tag pass counts the real metaclass `Class`."""
        return self.p.object_class_name(i0 + 1) or "Class"

    # ── per-body ordered <<FName / <<UObject streams ──
    def streams(self, i0: int) -> tuple[list[str], list[str]]:
        e = self.p.exports[i0]
        kind = self.class_disp(i0)
        pos, end = e["soff"], e["soff"] + e["ssize"]
        buf = self.buf
        if e["cls"] == 0:
            return self._class_streams(pos, end)
        names: list[str] = []
        objs: list[str] = []

        def rname():
            nonlocal pos
            v, pos = _rci(buf, pos); names.append(self.ename(v))

        def robj():
            nonlocal pos
            r, pos = _rci(buf, pos)
            k = self.objkey(r)
            if k is not None:
                objs.append(k)

        if kind == "TextBuffer":
            rname()                                   # None terminator
            return names, objs
        if kind == "Enum":
            rname(); robj(); robj()                    # None, super, next
            cnt, pos = _rci(buf, pos)
            for _ in range(cnt):
                rname()                                # each enum value (FName)
            return names, objs
        if kind == "Const":
            rname(); robj(); robj()                    # None, super, next
            return names, objs
        if kind == "Struct":
            rname(); robj(); robj(); robj(); robj()    # None, super, next, scripttext(0), children
            v, pos = _rci(buf, pos); names.append(self.ename(v))   # FriendlyName
            return names, objs
        if kind == "Function":
            rname(); robj(); robj(); robj(); robj()    # None, super, next, scripttext(0), children
            v, pos = _rci(buf, pos); names.append(self.ename(v))   # FriendlyName
            pos += 8                                    # Line, TextPos
            ss = struct.unpack_from("<I", buf, pos)[0]; pos += 4
            snames, sobjs, pos = self._script_streams(pos, ss)
            names += snames; objs += sobjs
            return names, objs
        if kind in _PROP_KINDS:
            rname(); robj(); robj()                    # None, super, next
            pos += 8                                    # ArrayDim, PropertyFlags
            rname()                                     # Category
            while pos < end:                            # type-tail object refs
                robj()
            return names, objs
        # plain UObject (tagged-prop list + native trailer)
        tags, _after = read_property_tags(self.p, pos, end)
        return self._tag_streams(tags)

    def _script_streams(self, pos: int, ss: int) -> tuple[list[str], list[str], int]:
        names: list[str] = []
        objs: list[str] = []

        def resolve(kind: str, index: int) -> str:
            if kind == "name":
                names.append(self.ename(index))
            else:
                k = self.objkey(index)
                if k is not None:
                    objs.append(k)
            return ""
        _toks, pos = decode_script(self.buf, pos, ss, resolve)
        return names, objs, pos

    def _tag_streams(self, tags) -> tuple[list[str], list[str]]:
        names: list[str] = []
        objs: list[str] = []
        for t in tags:
            names.append(t.name)
            if t.ptype == PT_NAME:
                names.append(self.ename(_rci(t.raw, 0)[0]))
            elif t.ptype == PT_OBJECT:
                k = self.objkey(_rci(t.raw, 0)[0])
                if k is not None:
                    objs.append(k)
            elif t.ptype == PT_STRUCT and t.struct_name:
                names.append(t.struct_name)
        names.append("None")                            # tagged-list terminator
        return names, objs

    def _class_streams(self, pos: int, end: int) -> tuple[list[str], list[str]]:
        """A non-`self.class_i` class export's ref stream (multi-class packages, e.g.
        `ExtendedBuilders`) — `objinputs()` only special-cases `self.class_i` for the
        `late_name_refs` split, so every OTHER class still routes through here via `streams()`."""
        (names, objs), (tnames, tobjs) = self._class_split_streams(pos, end)
        return names + tnames, objs + tobjs

    def _class_split_streams(self, pos: int, end: int) -> tuple[tuple[list[str], list[str]],
                                                                tuple[list[str], list[str]]]:
        """The class body's HEADER refs (super/next/FriendlyName/dependencies/PackageImports/
        ClassWithin/ClassConfigName — resolved at class-header compile time) separate from its
        TAIL refs (the defaultproperties tag stream — compiled last, after every member/function in
        the source). UCC registers value-only names at these two different points (RE'd 2026-09-05
        from `RahnemBrushBuilders`: its package self-name, a header ref, gathers before a function
        param declared later in source; `GroupName="Landscape"`, a tail ref, gathers after it)."""
        buf = self.buf
        names: list[str] = []
        objs: list[str] = []

        def robj():
            nonlocal pos
            r, pos = _rci(buf, pos)
            k = self.objkey(r)
            if k is not None:
                objs.append(k)

        robj(); robj(); robj(); robj()                  # super, next, ScriptText, Children
        fn, pos = _rci(buf, pos); names.append(self.ename(fn))   # FriendlyName
        pos += 8                                        # Line, TextPos
        ss = struct.unpack_from("<I", buf, pos)[0]; pos += 4
        pos += ss                                       # class script is empty
        pos += 8 + 8 + 2 + 4 + 4 + 16                   # probe, ignore, lto, sflags, cflags, guid
        depc, pos = _rci(buf, pos)
        for _ in range(depc):
            dc, pos = _rci(buf, pos)                     # dependency class (obj ref)
            k = self.objkey(dc)
            if k is not None:
                objs.append(k)
            pos += 8                                     # deep, script_text_crc
        pic, pos = _rci(buf, pos)
        for _ in range(pic):
            n, pos = _rci(buf, pos); names.append(self.ename(n))   # PackageImports (FName)
        wi, pos = _rci(buf, pos)                          # ClassWithin (obj)
        k = self.objkey(wi)
        if k is not None:
            objs.append(k)
        cfg, pos = _rci(buf, pos); names.append(self.ename(cfg))   # ClassConfigName
        tnames, tobjs = self._tag_streams(read_property_tags(self.p, pos, end)[0])
        return (names, objs), (tnames, tobjs)

    # ── children-chain creation order ──
    def _children_ref(self, i0: int) -> int:
        e = self.p.exports[i0]
        pos = e["soff"]
        if e["cls"] == 0:                                # class: super, next, ScriptText, Children
            for _ in range(3):
                _v, pos = _rci(self.buf, pos)
            v, _ = _rci(self.buf, pos)
            return v
        kind = self.class_disp(i0)
        if kind in ("Struct", "Function"):               # None, super, next, ScriptText, Children
            for _ in range(4):
                _v, pos = _rci(self.buf, pos)
            v, _ = _rci(self.buf, pos)
            return v
        return 0

    def _next_ref(self, i0: int) -> int:
        e = self.p.exports[i0]
        pos = e["soff"]
        if e["cls"] == 0:                                # class: super, next
            _v, pos = _rci(self.buf, pos)
            v, _ = _rci(self.buf, pos)
            return v
        _v, pos = _rci(self.buf, pos)                     # None
        _v, pos = _rci(self.buf, pos)                     # super
        v, _ = _rci(self.buf, pos)                        # next
        return v

    def _chain(self, first_child_ref: int) -> list[int]:
        out, cur = [], first_child_ref
        while cur > 0:
            out.append(cur - 1)
            cur = self._next_ref(cur - 1)
        return out

    def _decl_forward(self, i0: int) -> list[int]:
        """A field's children in forward declaration order. The Children list is stored
        [non-property fields reverse-decl] ++ [properties forward-decl], so forward = the property
        suffix as-is then the non-property prefix reversed."""
        children = self._chain(self._children_ref(i0))
        props = [c for c in children if self.class_disp(c) in _PROP_KINDS]
        nonprops = [c for c in children if self.class_disp(c) not in _PROP_KINDS]
        return props + nonprops[::-1]

    def creation_order(self) -> list[str]:
        """Object creation order (forward declaration) — the export gather. Each field is created,
        then its own children inline (a function immediately followed by its params + locals)."""
        scripttext = next((i for i, e in enumerate(self.p.exports)
                           if self.class_disp(i) == "TextBuffer" and e["outer"] == self.class_i + 1),
                          None)
        order = [self.ekey(self.class_i)]
        seen = {self.class_i}
        if scripttext is not None:
            order.append(self.ekey(scripttext)); seen.add(scripttext)

        def add(i0: int) -> None:
            if i0 in seen:
                return
            seen.add(i0)
            order.append(self.ekey(i0))
            for c in self._decl_forward(i0):
                add(c)

        for c in self._decl_forward(self.class_i):
            add(c)
        for i0 in range(len(self.p.exports)):            # leftover array inners
            add(i0)
        return order

    _CPF_PARM = 0x80    # CPF_Parm — set on a function param/return (not on a local)

    def _prop_flags(self, i0: int) -> int:
        pos = self.p.exports[i0]["soff"]
        for _ in range(3):                               # None, super, next
            _v, pos = _rci(self.buf, pos)
        pos += 4                                          # ArrayDim
        return struct.unpack_from("<I", self.buf, pos)[0]

    def name_creation_order(self) -> list[str]:
        """UCC's NAME-registration encounter order for own-new names = forward declaration order. The
        Children linked list is stored reverse-declaration (UE1 prepends), so walk it reversed; a
        function registers its PARAMS/return in pass 1 (inline) and its body LOCALS in pass 2."""
        scripttext = next((i for i, e in enumerate(self.p.exports)
                           if self.class_disp(i) == "TextBuffer" and e["outer"] == self.class_i + 1),
                          None)
        order = [self.ekey(self.class_i)]
        seen = {self.class_i}
        if scripttext is not None:
            order.append(self.ekey(scripttext)); seen.add(scripttext)
        funcs: list[int] = []

        def add(i0: int) -> None:
            if i0 in seen:
                return
            seen.add(i0)
            order.append(self.ekey(i0))
            kids = self._decl_forward(i0)
            if self.class_disp(i0) == "Function":
                funcs.append(i0)
                for c in kids:                            # pass 1: params/return only
                    if self._prop_flags(c) & self._CPF_PARM and c not in seen:
                        seen.add(c); order.append(self.ekey(c))
            else:
                for c in kids:
                    add(c)

        for c in self._decl_forward(self.class_i):
            add(c)
        for fi in funcs:                                  # pass 2: function-body locals
            for c in self._decl_forward(fi):
                if c not in seen:
                    seen.add(c); order.append(self.ekey(c))
        for i0 in range(len(self.p.exports)):             # leftover (array inners)
            if i0 not in seen:
                seen.add(i0); order.append(self.ekey(i0))
        return order

    def objinputs(self) -> list[ObjInput]:
        objs: list[ObjInput] = []
        for i0 in range(len(self.p.exports)):
            late_names: tuple[str, ...] = ()
            if i0 == self.class_i:
                e = self.p.exports[i0]
                (names, orefs), (late_names, late_orefs) = self._class_split_streams(
                    e["soff"], e["soff"] + e["ssize"])
                orefs = orefs + late_orefs
            else:
                names, orefs = self.streams(i0)
            objs.append(ObjInput(name=self.ekey(i0), display=self.edisp(i0),
                                 class_name=self.class_disp(i0),
                                 outer=self.outer_disp(self.p.exports[i0]["outer"]),
                                 in_package=True, name_refs=tuple(names), obj_refs=tuple(orefs),
                                 late_name_refs=tuple(late_names)))
        for j in range(len(self.p.imports)):
            cp, cn, pi, on = self.p.imports[j]
            objs.append(ObjInput(name=self.idisp(j), display=self.idisp(j),
                                 class_name=self.p.names[cn],
                                 outer=(self.idisp(-pi - 1) if pi < 0 else None), in_package=False))
        return objs


def true_order(u: bytes) -> tuple[list[str], list[str], list[tuple[str, tuple[str, ...]]]]:
    """Decode compiled package `u` and return its (names, imports, export_rows) in UCC's table order.
    `export_rows` are (leaf display name, outer-chain) pairs (the shape `order_override` expects); the
    outer-chain is outermost->immediate, disambiguating a leaf whose immediate outer repeats."""
    d = _Decoder(u)
    ordered = order_package(d.objinputs(), d.creation_order(), default_global_index(),
                            name_creation=d.name_creation_order())
    exp_i = {d.ekey(i): i for i in range(len(d.p.exports))}
    export_rows = [(d.edisp(exp_i[k]), d.outer_chain(exp_i[k])) for k in ordered.exports]
    return ordered.names, ordered.imports, export_rows
