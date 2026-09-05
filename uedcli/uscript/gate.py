"""`.u` package parity gate: is uedcli's compile byte-identical to UCC's, modulo the closed
exclusion set? The VERDICT is a raw byte compare with the excluded regions masked; the DIAGNOSTICS
parse both packages structurally to locate and name the first divergence (header field / name table
/ import table / export table / a specific export body), so a failing compile points straight at the
byte to fix.

Exclusion set (only per-build-random engine fields; see `dev/docs/unrealed/unrealscript/parity.md`):
- the 16-byte package GUID in the header (v>=68).

Anything else that differs is a REAL divergence and fails. New exclusions need evidence + owner
sign-off (board item `uedcli-unrealscript-compiler`), never a silent mask here.
"""
from __future__ import annotations

import struct
from collections import Counter
from dataclasses import dataclass

from ..upackage import (MAGIC, _parse_package, read_compact_index, read_fstring,
                        read_property_tags)
from ..uprops.base import PROPERTY_TYPES
from .bytecode import decode_script

_HEADER_FIXED = 36  # nine little-endian u32: tag, version, flags, (count,offset)*3


@dataclass(frozen=True, kw_only=True)
class Header:
    version: int          # file version (low 16 bits)
    licensee: int         # licensee version (high 16 bits)
    flags: int
    name_count: int
    name_offset: int
    export_count: int
    export_offset: int
    import_count: int
    import_offset: int
    guid_range: tuple[int, int] | None   # (start, end) of the 16-byte GUID, or None (v<68)


def _parse_header(buf: bytes) -> Header:
    tag, ver, flags, nc, no, ec, eo, ic, io = struct.unpack_from("<9I", buf, 0)
    if tag != MAGIC:
        raise ValueError(f"bad magic {tag:#010x} (not an Unreal package)")
    version = ver & 0xFFFF
    # v>=68 stores FGuid(16) + TArray<FGenerationInfo> right after the fixed header; v<68 stores a
    # heritage table instead (no GUID). The GUID is the only per-save-random header field.
    guid_range = (_HEADER_FIXED, _HEADER_FIXED + 16) if version >= 68 else None
    return Header(version=version, licensee=ver >> 16, flags=flags, name_count=nc, name_offset=no,
                  export_count=ec, export_offset=eo, import_count=ic, import_offset=io,
                  guid_range=guid_range)


def _masked(buf: bytes, ranges: list[tuple[int, int]]) -> bytes:
    if not ranges:
        return buf
    out = bytearray(buf)
    for start, end in ranges:
        for i in range(start, min(end, len(out))):
            out[i] = 0
    return out


def _name_table_raw(buf: bytes, hdr: Header) -> list[tuple[str, int]]:
    """(name, flags) in table order — flags matter for byte parity (v>=64 stores u32 after each)."""
    out, pos = [], hdr.name_offset
    for _ in range(hdr.name_count):
        if hdr.version < 64:
            end = buf.index(b"\x00", pos)
            out.append((buf[pos:end].decode("latin-1"), 0))
            pos = end + 1
        else:
            s, pos = read_fstring(buf, pos)
            flags = struct.unpack_from("<I", buf, pos)[0]
            pos += 4
            out.append((s, flags))
    return out


def _first_diff(a: bytes, b: bytes) -> int | None:
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return None if len(a) == len(b) else n


def _locate(hdr: Header, off: int) -> str:
    """Human-readable region for a byte offset, given one package's layout."""
    if off < _HEADER_FIXED:
        fields = ["tag", "version", "flags", "name_count", "name_offset",
                  "export_count", "export_offset", "import_count", "import_offset"]
        return f"header.{fields[off // 4]}"
    if hdr.guid_range and hdr.guid_range[0] <= off < hdr.guid_range[1]:
        return "header.guid (EXCLUDED — should be masked)"
    # order the three tables by offset to attribute the byte
    segs = sorted([("name-table", hdr.name_offset), ("export-table", hdr.export_offset),
                   ("import-table", hdr.import_offset), ("header-guid+generations", _HEADER_FIXED)],
                  key=lambda s: s[1])
    label = "post-header"
    for name, start in segs:
        if off >= start:
            label = name
    return label


@dataclass(frozen=True, kw_only=True)
class GateResult:
    passed: bool
    messages: list[str]

    def __bool__(self) -> bool:
        return self.passed


def gate(uedcli_u: bytes, ucc_u: bytes, *, ucc_name: str = "ucc", mine_name: str = "uedcli") -> GateResult:
    """Compare two `.u` packages. Returns a `GateResult`; `.passed` is the byte-parity verdict
    (excluded regions masked), `.messages` explains the first divergence structurally."""
    msgs: list[str] = []
    try:
        ha, hb = _parse_header(uedcli_u), _parse_header(ucc_u)
    except ValueError as e:
        return GateResult(passed=False, messages=[f"header parse: {e}"])

    ranges_a = [ha.guid_range] if ha.guid_range else []
    ranges_b = [hb.guid_range] if hb.guid_range else []
    ma, mb = _masked(uedcli_u, ranges_a), _masked(ucc_u, ranges_b)
    if ma == mb:
        return GateResult(passed=True, messages=[f"byte-identical modulo GUID ({len(ucc_u)} bytes)"])

    # Diverged — build diagnostics.
    if len(uedcli_u) != len(ucc_u):
        msgs.append(f"SIZE differs: {mine_name}={len(uedcli_u)} bytes, {ucc_name}={len(ucc_u)} bytes")

    diff = _first_diff(ma, mb)
    if diff is not None:
        region = _locate(hb, diff)
        av = ma[diff:diff + 16].hex()
        bv = mb[diff:diff + 16].hex()
        msgs.append(f"first byte diff at offset {diff} (0x{diff:x}) in {region}: "
                    f"{mine_name}={av} {ucc_name}={bv}")

    # Structured comparisons for a targeted message.
    _structured_diffs(uedcli_u, ucc_u, ha, hb, msgs, ucc_name, mine_name)
    return GateResult(passed=False, messages=msgs)


def _structured_diffs(a: bytes, b: bytes, ha: Header, hb: Header, msgs: list[str],
                      ucc_name: str, mine_name: str) -> None:
    if (ha.version, ha.licensee) != (hb.version, hb.licensee):
        msgs.append(f"VERSION differs: {mine_name}={ha.version}/{ha.licensee} "
                    f"{ucc_name}={hb.version}/{hb.licensee}")
    if ha.flags != hb.flags:
        msgs.append(f"PACKAGE FLAGS differ: {mine_name}={ha.flags:#x} {ucc_name}={hb.flags:#x}")
    if (ha.name_count, ha.export_count, ha.import_count) != \
       (hb.name_count, hb.export_count, hb.import_count):
        msgs.append(f"TABLE COUNTS differ: {mine_name}=(names={ha.name_count},exp={ha.export_count},"
                    f"imp={ha.import_count}) {ucc_name}=(names={hb.name_count},exp={hb.export_count},"
                    f"imp={hb.import_count})")
        return
    na, nb = _name_table_raw(a, ha), _name_table_raw(b, hb)
    for i, (x, y) in enumerate(zip(na, nb)):
        if x != y:
            msgs.append(f"NAME[{i}] differs: {mine_name}={x!r} {ucc_name}={y!r}")
            break
    # Export body sizes/offsets, positional.
    ea = _parse_package(a, "<uedcli>", mine_name).exports
    eb = _parse_package(b, "<ucc>", ucc_name).exports
    for i, (x, y) in enumerate(zip(ea, eb)):
        if x["ssize"] != y["ssize"]:
            msgs.append(f"EXPORT[{i}] body size differs: {mine_name}={x['ssize']} {ucc_name}={y['ssize']}")
            break
        bodya = a[x["soff"]:x["soff"] + x["ssize"]]
        bodyb = b[y["soff"]:y["soff"] + y["ssize"]]
        if bodya != bodyb:
            d = _first_diff(bodya, bodyb)
            msgs.append(f"EXPORT[{i}] body diverges at body-offset {d}: "
                        f"{mine_name}={bodya[d:d+12].hex()} {ucc_name}={bodyb[d:d+12].hex()}")
            break


# ══ identity/permutation parity gate (perm_gate) ══════════════════════════════════════════════════
# Mirrors the map-parity gate (`dev/docs/spikes/.../parity_gate.py`) for `.u` CODE packages: resolve
# every ref by IDENTITY (class + outer-chain + object-name, casefolded per the FName-case exclusion)
# so name/import/export TABLE ORDER is neutralised WITHOUT masking a genuine wrong-target ref. A
# UFunction/UState script body is decoded index-independently (`bytecode.decode_script`) and compared
# as a token stream. Exclusions (all documented): the 16-byte package GUID, name/import/export table
# ORDER (permutation), and FName CASE. A genuine wrong body / flag / name still FAILS.


class _RawView:
    """A minimal `read_property_tags` target over a standalone value buffer (a struct's nested
    tagged-property bytes) that borrows the owning package's name table."""

    def __init__(self, buf: bytes, names: list[str]) -> None:
        self.buf = buf
        self.names = names


class _UPkg:
    """A parsed `.u` package with identity resolution for the perm gate."""

    def __init__(self, buf: bytes, tag: str) -> None:
        self.p = _parse_package(buf, f"<{tag}>", tag)
        self.buf = self.p.buf

    # ── identities (casefolded) ──
    def _nm(self, idx: int) -> str:
        names = self.p.names
        return names[idx].casefold() if 0 <= idx < len(names) else f"<name#{idx}>"

    def export_identity(self, i0: int) -> str:
        p = self.p
        cls = (p.object_class_name(i0 + 1) or "Class").casefold()
        chain, outer = [], p.exports[i0]["outer"]
        for _ in range(64):
            if outer <= 0:
                break
            oe = p.exports[outer - 1]
            chain.append(self._nm(oe["nm"]))
            outer = oe["outer"]
        leaf = self._nm(p.exports[i0]["nm"])
        return f"{cls} {'.'.join(reversed(chain + [leaf]))}"

    def import_identity(self, j: int) -> str:
        p = self.p
        cp, cn, _pi, _on = p.imports[j]
        chain, k = [], j
        for _ in range(64):
            chain.append(self._nm(p.imports[k][3]))
            o = p.imports[k][2]
            if o >= 0:
                break
            k = -o - 1
        return f"import {self._nm(cp)}.{self._nm(cn)} '{'.'.join(reversed(chain))}'"

    def ref_identity(self, ref: int) -> str:
        if ref == 0:
            return "none"
        if ref > 0:
            return self.export_identity(ref - 1) if ref <= len(self.p.exports) else f"<exp#{ref}>"
        j = -ref - 1
        return self.import_identity(j) if j < len(self.p.imports) else f"<imp#{ref}>"

    def _script_resolve(self):
        def resolve(kind: str, index: int) -> str:
            return self._nm(index) if kind == "name" else self.ref_identity(index)
        return resolve

    # ── body canonicalisation ──
    def canon_body(self, i0: int):
        """A permutation-stable canonical form of export `i0`'s body: every name ref → its (casefolded)
        name string, every object ref → its target identity, scripts → decoded token streams. Two
        identity-matched bodies are byte-equal iff their canon forms compare equal."""
        p, buf = self.p, self.buf
        e = p.exports[i0]
        pos, end = e["soff"], e["soff"] + e["ssize"]
        cls = (p.object_class_name(i0 + 1) or "Class").casefold()
        if e["cls"] == 0:
            return ("class", *self._canon_class(pos, end))
        if cls == "textbuffer":
            _none, pos = read_compact_index(buf, pos)
            po, to = struct.unpack_from("<II", buf, pos); pos += 8
            text, pos = read_fstring(buf, pos)
            return ("textbuffer", po, to, text)
        if cls == "function":
            return ("function", *self._canon_function(pos, end))
        if cls == "enum":
            _none, pos = read_compact_index(buf, pos)
            _sup, pos = read_compact_index(buf, pos)
            nxt, pos = read_compact_index(buf, pos)
            cnt, pos = read_compact_index(buf, pos)
            vals = []
            for _ in range(cnt):
                v, pos = read_compact_index(buf, pos)
                vals.append(self._nm(v))
            return ("enum", self.ref_identity(nxt), tuple(vals))
        if cls == "const":
            _none, pos = read_compact_index(buf, pos)
            _sup, pos = read_compact_index(buf, pos)
            nxt, pos = read_compact_index(buf, pos)
            val, pos = read_fstring(buf, pos)
            return ("const", self.ref_identity(nxt), val)
        if cls == "struct":
            _none, pos = read_compact_index(buf, pos)
            sup, pos = read_compact_index(buf, pos)
            nxt, pos = read_compact_index(buf, pos)
            _st, pos = read_compact_index(buf, pos)
            ch, pos = read_compact_index(buf, pos)
            fn, pos = read_compact_index(buf, pos)
            line, tp, ss = struct.unpack_from("<III", buf, pos)
            return ("struct", self.ref_identity(sup), self.ref_identity(nxt),
                    self.ref_identity(ch), self._nm(fn), line, tp, ss)
        if cls in _CF_PROPERTY_TYPES:
            return ("property", *self._canon_property(pos, end))
        # Any other class = a plain UObject instance (e.g. a ConSys conversation object from
        # `#exec CONVERSATION IMPORT`): its body is a None-terminated tagged-property list, then any
        # native-Serialize trailer. Canonicalise the tags (order/case/ref-target neutral) and keep the
        # trailer raw so a native tail still compares.
        tags, after = read_property_tags(self.p, pos, end)
        return ("object", cls, self._canon_tags(tags), buf[after:end].hex())

    def _canon_property(self, pos: int, end: int):
        buf = self.buf
        _none, pos = read_compact_index(buf, pos)
        _sup, pos = read_compact_index(buf, pos)
        nxt, pos = read_compact_index(buf, pos)
        adim, flags = struct.unpack_from("<II", buf, pos); pos += 8
        cat, pos = read_compact_index(buf, pos)
        tail = []
        while pos < end:
            ref, pos = read_compact_index(buf, pos)
            tail.append(self.ref_identity(ref))
        return (self.ref_identity(nxt), adim, flags, self._nm(cat), tuple(tail))

    def _canon_function(self, pos: int, end: int):
        buf = self.buf
        _none, pos = read_compact_index(buf, pos)
        sup, pos = read_compact_index(buf, pos)
        nxt, pos = read_compact_index(buf, pos)
        _st, pos = read_compact_index(buf, pos)
        ch, pos = read_compact_index(buf, pos)
        fn, pos = read_compact_index(buf, pos)
        line, tp, ss = struct.unpack_from("<III", buf, pos); pos += 12
        toks, pos = decode_script(buf, pos, ss, self._script_resolve())
        inative, prec = struct.unpack_from("<HB", buf, pos); pos += 3
        flags = struct.unpack_from("<I", buf, pos)[0]; pos += 4
        rep = None
        if flags & 0x40:
            rep = struct.unpack_from("<H", buf, pos)[0]
        return (self.ref_identity(sup), self.ref_identity(nxt), self.ref_identity(ch),
                self._nm(fn), line, tp, ss, tuple(toks), inative, prec, flags, rep)

    def _canon_class(self, pos: int, end: int):
        buf = self.buf
        sup, pos = read_compact_index(buf, pos)
        nxt, pos = read_compact_index(buf, pos)
        st, pos = read_compact_index(buf, pos)
        ch, pos = read_compact_index(buf, pos)
        fn, pos = read_compact_index(buf, pos)
        line, tp, ss = struct.unpack_from("<III", buf, pos); pos += 12
        pos += ss                                        # class script is empty
        probe, ignore = struct.unpack_from("<QQ", buf, pos); pos += 16
        lto, sflags, cflags = struct.unpack_from("<HII", buf, pos); pos += 10
        guid = buf[pos:pos + 16]; pos += 16              # ClassGuid (all-zero, deterministic)
        depcnt, pos = read_compact_index(buf, pos)
        deps = []
        for _ in range(depcnt):
            dcls, pos = read_compact_index(buf, pos)
            deep, crc = struct.unpack_from("<II", buf, pos); pos += 8
            deps.append((self.ref_identity(dcls), deep, crc))
        picnt, pos = read_compact_index(buf, pos)
        pis = []
        for _ in range(picnt):
            n, pos = read_compact_index(buf, pos)
            pis.append(self._nm(n))
        within, pos = read_compact_index(buf, pos)
        cfg, pos = read_compact_index(buf, pos)
        defaults = self._canon_props(pos, end)
        return (self.ref_identity(sup), self.ref_identity(nxt), self.ref_identity(st),
                self.ref_identity(ch), self._nm(fn), line, tp, ss, probe, ignore, lto, sflags,
                cflags, guid, tuple(deps), tuple(pis), self.ref_identity(within), self._nm(cfg),
                defaults)

    def _canon_props(self, pos: int, end: int):
        return self._canon_tags(read_property_tags(self.p, pos, end)[0])

    def _canon_tags(self, tags):
        return tuple((t.name.casefold(), t.array_index, (t.struct_name or "").casefold(),
                     self._canon_value(t)) for t in tags)

    def _canon_value(self, t):
        from ..upackage import PT_BOOL, PT_NAME, PT_OBJECT, PT_STRUCT
        if t.ptype == PT_BOOL:
            return ("bool", t.bool_value)
        if t.ptype == PT_NAME:
            idx, _ = read_compact_index(t.raw, 0)
            return ("name", self._nm(idx))
        if t.ptype == PT_OBJECT:
            ref, _ = read_compact_index(t.raw, 0)
            return ("obj", self.ref_identity(ref))
        if t.ptype == PT_STRUCT:
            # A struct value is a nested None-terminated tagged-property list; its member-name (and
            # any nested name/object) refs are name-table-ORDER-dependent, so canonicalise them
            # structurally — raw hex would false-FAIL a correct compile whose name order differs.
            tags, _ = read_property_tags(_RawView(t.raw, self.p.names), 0, len(t.raw))
            return ("struct", (t.struct_name or "").casefold(), self._canon_tags(tags))
        return ("raw", t.raw.hex())


_CF_PROPERTY_TYPES = frozenset(c.casefold() for c in PROPERTY_TYPES)


def _name_flag_multiset(u: _UPkg) -> Counter:
    """Multiset of (casefolded name, flags). Content + FLAGS compared; ORDER and CASE excluded."""
    raw = _name_table_raw(u.buf, _parse_header(u.buf))
    return Counter((s.casefold(), fl) for s, fl in raw)


def perm_gate(mine: bytes, ucc: bytes, *, mine_name: str = "uedcli",
              ucc_name: str = "ucc") -> GateResult:
    """Identity/permutation `.u` parity: PASS iff the two packages match modulo the documented
    exclusions (package GUID + name/import/export table ORDER + FName CASE). Exports are matched by
    identity; for each, the export-table Super (canonicalised) and ObjectFlags must match and the
    body must be byte-identical after ref canonicalisation; name-table CONTENT+FLAGS, import CONTENT,
    and the export identity SET must all match. (Super/ObjectFlags added after an adversarial review
    found them uncompared — they are consequential columns, not exclusions.)"""
    try:
        ua, ub = _UPkg(mine, mine_name), _UPkg(ucc, ucc_name)
    except ValueError as e:
        return GateResult(passed=False, messages=[f"parse: {e}"])
    fails: list[str] = []

    ha, hb = _parse_header(mine), _parse_header(ucc)
    for label, x, y in (("version", ha.version, hb.version), ("licensee", ha.licensee, hb.licensee),
                        ("flags", ha.flags, hb.flags),
                        ("name_count", ha.name_count, hb.name_count),
                        ("import_count", ha.import_count, hb.import_count),
                        ("export_count", ha.export_count, hb.export_count)):
        if x != y:
            fails.append(f"header {label}: {mine_name}={x!r} {ucc_name}={y!r}")

    na, nb = _name_flag_multiset(ua), _name_flag_multiset(ub)
    if na != nb:
        fails.append(f"name-table CONTENT+FLAGS differ (casefolded): "
                     f"only-{mine_name}={sorted((na - nb).elements())[:8]} "
                     f"only-{ucc_name}={sorted((nb - na).elements())[:8]}")

    ia = {ua.import_identity(j) for j in range(len(ua.p.imports))}
    ib = {ub.import_identity(j) for j in range(len(ub.p.imports))}
    if ia != ib:
        fails.append(f"import CONTENT differs: only-{mine_name}={sorted(ia - ib)[:8]} "
                     f"only-{ucc_name}={sorted(ib - ia)[:8]}")

    ids_a = {ua.export_identity(i): i for i in range(len(ua.p.exports))}
    ids_b = {ub.export_identity(i): i for i in range(len(ub.p.exports))}
    if len(ids_a) != len(ua.p.exports):
        fails.append(f"{mine_name} export identities not unique")
    if len(ids_b) != len(ub.p.exports):
        fails.append(f"{ucc_name} export identities not unique")
    only_a, only_b = sorted(set(ids_a) - set(ids_b)), sorted(set(ids_b) - set(ids_a))
    if only_a or only_b:
        fails.append(f"export SET differs: only-{mine_name}={only_a[:8]} only-{ucc_name}={only_b[:8]}")

    for ident in sorted(set(ids_a) & set(ids_b)):
        ea, eb = ua.p.exports[ids_a[ident]], ub.p.exports[ids_b[ident]]
        # export-table Super (canonicalised to identity — order-independent) and ObjectFlags: both
        # are real, consequential columns and NOT in the exclusion set (found masked by opus review).
        sa, sb = ua.ref_identity(ea["sup"]), ub.ref_identity(eb["sup"])
        if sa != sb:
            fails.append(f"EXPORT {ident}: Super differs: {mine_name}={sa} {ucc_name}={sb}")
        if ea["flags"] != eb["flags"]:
            fails.append(f"EXPORT {ident}: ObjectFlags differ: "
                         f"{mine_name}={ea['flags']:#x} {ucc_name}={eb['flags']:#x}")
        try:
            ca, cb = ua.canon_body(ids_a[ident]), ub.canon_body(ids_b[ident])
        except Exception as ex:                          # a decode failure is a hard fail, not a pass
            fails.append(f"BODY {ident}: canonicalise failed: {ex}")
            continue
        if ca != cb:
            fails.append(f"BODY {ident}: canonical bodies differ\n"
                         f"      {mine_name}={_perm_short(ca)}\n      {ucc_name}={_perm_short(cb)}")

    return GateResult(passed=not fails,
                      messages=fails or [f"identity-parity OK modulo GUID/table-order/FName-case "
                                         f"({len(ids_a)} exports)"])


def _perm_short(c, limit: int = 300) -> str:
    s = repr(c)
    return s if len(s) <= limit else s[:limit] + " ..."
