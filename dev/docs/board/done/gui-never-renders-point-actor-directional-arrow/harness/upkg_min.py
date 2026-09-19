"""Minimal standalone UE1 .u package reader (header + name/import/export tables + UClass tail
defaults), written in pure Python with NO dependency on `uedcli_native` (which this sandbox's
rootless docker cannot build — no shared filesystem for a bind mount).

Ported directly from `uedcli-native/src/package_read.rs` (`parse_package`, `read_property_tags`)
and `uedcli/uprops/uclass.py` (`class_default_tags`'s UClass-tail layout walk) — read, not run;
this is an independent re-implementation of already-documented format facts
(`dev/docs/unrealed/unrealscript/u-format.md`), used only for this investigation.
"""
from __future__ import annotations

import struct


def read_ci(buf: bytes, pos: int) -> tuple[int, int]:
    b0 = buf[pos]
    pos += 1
    neg = bool(b0 & 0x80)
    val = b0 & 0x3F
    if b0 & 0x40:
        shift = 6
        while True:
            b = buf[pos]
            pos += 1
            val |= (b & 0x7F) << shift
            if not (b & 0x80) or shift >= 27:
                break
            shift += 7
    return (-val if neg else val), pos


def read_array_index(buf: bytes, pos: int) -> tuple[int, int]:
    b0 = buf[pos]
    if b0 < 0x80:
        return b0, pos + 1
    if (b0 & 0xC0) == 0x80:
        return ((b0 & 0x3F) << 8) | buf[pos + 1], pos + 2
    return (((b0 & 0x3F) << 24) | (buf[pos + 1] << 16) | (buf[pos + 2] << 8) | buf[pos + 3]), pos + 4


_EX_END_FUNCTION_PARMS = 0x16


def _walk_expr(pkg: "Package", pos: int, mem: int) -> tuple[int, int, int]:
    """Port of `uedcli/uprops/ufield.py::_walk_expr` (UStruct::SerializeExpr bytecode walk)."""
    buf = pkg.buf
    tok = buf[pos]; pos += 1; mem += 1

    def obj():
        nonlocal pos, mem
        _v, pos = read_ci(buf, pos)
        mem += 4

    def name():
        nonlocal pos, mem
        _v, pos = read_ci(buf, pos)
        mem += 4

    def fixed(n):
        nonlocal pos, mem
        pos += n; mem += n

    def expr():
        nonlocal pos, mem
        pos, mem, t = _walk_expr(pkg, pos, mem)
        return t

    def parms():
        while expr() != _EX_END_FUNCTION_PARMS:
            pass

    if tok >= 0x70:
        parms()
    elif tok >= 0x60:
        fixed(1); parms()
    elif 0x39 <= tok <= 0x5F:
        expr()
    elif tok in (0x00, 0x01, 0x02):
        obj()
    elif tok == 0x04:
        expr()
    elif tok == 0x05:
        fixed(1); expr()
    elif tok == 0x06:
        fixed(2)
    elif tok == 0x07:
        fixed(2); expr()
    elif tok == 0x08:
        pass
    elif tok == 0x09:
        fixed(2); expr()
    elif tok == 0x0A:
        w = struct.unpack_from("<H", buf, pos)[0]
        fixed(2)
        if w != 0xFFFF:
            expr()
    elif tok == 0x0B:
        pass
    elif tok == 0x0C:
        while True:
            v, pos2 = read_ci(buf, pos)
            pos = pos2; mem += 4
            nm = pkg.names[v] if 0 <= v < len(pkg.names) else None
            fixed(4)
            if nm == "None":
                break
    elif tok == 0x0D:
        expr()
    elif tok == 0x0E:
        expr()
    elif tok in (0x0F, 0x14):
        expr(); expr()
    elif tok == 0x11:
        expr(); expr(); expr(); expr()
    elif tok == 0x12:
        expr(); fixed(3); expr()
    elif tok == 0x13:
        obj(); expr()
    elif tok == 0x16:
        pass
    elif tok == 0x17:
        pass
    elif tok == 0x18:
        fixed(2); expr()
    elif tok == 0x19:
        expr(); fixed(3); expr()
    elif tok == 0x1A:
        expr(); expr()
    elif tok == 0x1B:
        name(); parms()
    elif tok == 0x1C:
        obj(); parms()
    elif tok == 0x1D:
        fixed(4)
    elif tok == 0x1E:
        fixed(4)
    elif tok == 0x1F:
        end = buf.index(b"\x00", pos)
        fixed(end - pos + 1)
    elif tok == 0x20:
        obj()
    elif tok == 0x21:
        name()
    elif tok in (0x22, 0x23):
        fixed(12)
    elif tok == 0x24:
        fixed(1)
    elif tok in (0x25, 0x26, 0x27, 0x28):
        pass
    elif tok == 0x29:
        obj()
    elif tok == 0x2A:
        pass
    elif tok == 0x2C:
        fixed(1)
    elif tok == 0x2D:
        expr()
    elif tok == 0x2E:
        obj(); expr()
    elif tok == 0x2F:
        expr(); fixed(2)
    elif tok in (0x30, 0x31):
        pass
    elif tok in (0x32, 0x33):
        obj(); expr(); expr()
    elif tok == 0x34:
        while struct.unpack_from("<H", buf, pos)[0] != 0:
            fixed(2)
        fixed(2)
    elif tok == 0x36:
        obj(); expr()
    elif tok == 0x38:
        name(); parms()
    else:
        raise ValueError(f"unknown script opcode {tok:#04x} at {pos - 1} in {pkg.name}")
    return pos, mem, tok


def _skip_script(pkg: "Package", pos: int, script_size: int) -> int:
    mem = 0
    while mem < script_size:
        pos, mem, _t = _walk_expr(pkg, pos, mem)
    if mem != script_size:
        raise ValueError(f"script walk desync in {pkg.name}: cursor {mem} != {script_size}")
    return pos


class Package:
    def __init__(self, buf: bytes):
        self.buf = buf
        magic, verlic, flags, namecnt, nameoff, expcnt, expoff, impcnt, impoff = \
            struct.unpack_from("<9I", buf, 0)
        assert magic == 0x9E2A83C1, hex(magic)
        self.version = verlic & 0xFFFF
        self.names: list[str] = []
        self.name_flags: list[int] = []
        pos = nameoff
        for _ in range(namecnt):
            length, pos = read_ci(buf, pos)
            nbytes = (-length) * 2 if length < 0 else length
            raw = buf[pos:pos + nbytes]
            pos += nbytes
            if length < 0:
                text = raw.decode("utf-16le", "replace").split("\x00")[0]
            else:
                cut = raw.find(b"\x00")
                text = raw[:cut if cut >= 0 else len(raw)].decode("latin-1")
            (flagsv,) = struct.unpack_from("<I", buf, pos)
            pos += 4
            self.names.append(text)
            self.name_flags.append(flagsv)
        self.imports: list[tuple[int, int, int, int]] = []
        pos = impoff
        for _ in range(impcnt):
            cp, pos = read_ci(buf, pos)
            cn, pos = read_ci(buf, pos)
            (pi,) = struct.unpack_from("<i", buf, pos)
            pos += 4
            on, pos = read_ci(buf, pos)
            self.imports.append((cp, cn, pi, on))
        self.exports: list[dict] = []
        pos = expoff
        for _ in range(expcnt):
            cls, pos = read_ci(buf, pos)
            sup, pos = read_ci(buf, pos)
            (outer,) = struct.unpack_from("<i", buf, pos)
            pos += 4
            nm, pos = read_ci(buf, pos)
            (flagsv,) = struct.unpack_from("<I", buf, pos)
            pos += 4
            ssize, pos = read_ci(buf, pos)
            if ssize > 0:
                soff, pos = read_ci(buf, pos)
            else:
                soff = 0
            self.exports.append(dict(cls=cls, sup=sup, outer=outer, nm=nm, flags=flagsv,
                                      ssize=ssize, soff=soff))

    def name_of_ref(self, ref: int) -> str | None:
        if ref == 0:
            return None
        if ref > 0:
            return self.names[self.exports[ref - 1]["nm"]]
        j = -ref - 1
        return self.names[self.imports[j][3]]

    def class_export_index(self, class_name: str) -> int | None:
        want = class_name.casefold()
        for i, e in enumerate(self.exports):
            if self.names[e["nm"]].casefold() == want and e["cls"] == 0:
                return i + 1
        return None

    def super_fqcn(self, class_name: str) -> str | None:
        ci = self.class_export_index(class_name)
        if ci is None:
            return None
        sup = self.exports[ci - 1]["sup"]
        if sup == 0:
            return None
        name = self.name_of_ref(sup)
        if sup > 0:
            return f"{self.name}.{name}"
        # import: find the import's own package name (its outer's ObjectName)
        j = -sup - 1
        cp, cn, pi, on = self.imports[j]
        if pi < 0:
            outer_j = -pi - 1
            pkg_name = self.names[self.imports[outer_j][3]]
        else:
            pkg_name = self.names[cp] if cp < len(self.names) else "?"
        return f"{pkg_name}.{name}"

    def read_property_tags(self, pos: int, end: int):
        tags = []
        while True:
            if pos >= end:
                raise ValueError(f"tagged-property list overran bounds at {pos} (no None)")
            nidx, pos = read_ci(self.buf, pos)
            name = self.names[nidx]
            if name == "None":
                return tags, pos
            info = self.buf[pos]
            pos += 1
            ptype = info & 0x0F
            size_code = (info >> 4) & 0x07
            bit7 = bool(info & 0x80)
            struct_name = None
            if ptype == 10:  # PT_STRUCT
                sidx, pos = read_ci(self.buf, pos)
                struct_name = self.names[sidx]
            if size_code == 0:
                size = 1
            elif size_code == 1:
                size = 2
            elif size_code == 2:
                size = 4
            elif size_code == 3:
                size = 12
            elif size_code == 4:
                size = 16
            elif size_code == 5:
                size = self.buf[pos]; pos += 1
            elif size_code == 6:
                (size,) = struct.unpack_from("<H", self.buf, pos); pos += 2
            else:
                (size,) = struct.unpack_from("<I", self.buf, pos); pos += 4
            if ptype == 3:  # PT_BOOL
                tags.append(dict(name=name, ptype=ptype, bool_value=bit7))
                continue
            array_index = 0
            if bit7:
                array_index, pos = read_array_index(self.buf, pos)
            raw = self.buf[pos:pos + size]
            pos += size
            tags.append(dict(name=name, ptype=ptype, struct_name=struct_name,
                              array_index=array_index, raw=raw))

    def class_default_tags(self, class_name: str) -> list[dict] | None:
        """Own (not inherited) defaultproperties tags. None if the class has no body (intrinsic/
        native-noexport, no ScriptText/defaults stored) rather than raising — callers walk Super."""
        ci = self.class_export_index(class_name)
        if ci is None:
            return None
        e = self.exports[ci - 1]
        so, sz = e["soff"], e["ssize"]
        if sz <= 0:
            return None
        buf = self.buf
        end = so + sz
        p = so
        _sup, p = read_ci(buf, p)          # SuperField
        _next, p = read_ci(buf, p)         # Next
        _st, p = read_ci(buf, p)           # ScriptText
        _children, p = read_ci(buf, p)     # Children
        _fname, p = read_ci(buf, p)        # FriendlyName
        p += 8                             # Line + TextPos
        (script_size,) = struct.unpack_from("<I", buf, p); p += 4
        if script_size != 0:
            p = _skip_script(self, p, script_size)
        p += 8 + 8 + 2 + 4                 # ProbeMask + IgnoreMask + LabelTableOffset + StateFlags
        p += 4 + 16                        # ClassFlags + ClassGuid
        depcnt, p = read_ci(buf, p)
        for _ in range(depcnt):
            _c, p = read_ci(buf, p)
            p += 8
        impcnt, p = read_ci(buf, p)
        for _ in range(impcnt):
            _n, p = read_ci(buf, p)
        _within, p = read_ci(buf, p)
        _cfg, p = read_ci(buf, p)
        tags, p = self.read_property_tags(p, end)
        if p != end:
            raise ValueError(f"{class_name}: defaults did not consume to body end "
                              f"(cursor {p} != {end}, {end - p} left)")
        return tags


def load(path: str) -> Package:
    pkg = Package(open(path, "rb").read())
    import os
    pkg.name = os.path.splitext(os.path.basename(path))[0]
    return pkg
