#!/usr/bin/env python3
"""The incremental-lockstep-ladder PASS/FAIL gate: native vs UED22 FULL parity, EXCLUDING exactly
the owner-ruled MAP REBUILD GC artifacts + the per-save-random masks, and NOTHING else.

Owner ruling 2026-09-04 + the opus reviewer's soundness conditions. Unlike a raw byte diff, the gate
resolves every reference by IDENTITY (class + outer-chain, permutation-remapped across the two export
orders) before comparing, so an export-order/name-order shift is neutralised WITHOUT masking a
genuine wrong-target ref.

EXCLUSIONS (the only differences tolerated):
  GC-1  export-table ORDER / freed-slot reuse  -> exports matched by identity, order not asserted.
  GC-2  object auto-counter leaf NAMES (Polys3 vs Polys7) -> a Polys export's identity is keyed on
        its OWNING Model (field_0x54), not its counter leaf; a name matching `^Polys\\d+$` folds to
        `Polys#` for the name-table content check. MyLevel and every import name stay literal.
  GC-3  Level `Actors` array None-holes -> null slots dropped; the surviving actors' identities AND
        their relative order are still asserted equal (Actors order = CSG precedence).
  M     per-save-random: 16-byte GUID, StateFrame LatentAction, LevelInfo TimeSeconds/AIProfile,
        ULevel TimeSeconds float, the six viewport Camera bodies.

Everything else must match: header (version/licensee/flags/counts), name-table CONTENT (multiset,
counter-names folded), import-table CONTENT (set of resolved paths, names literal), and every
identity-matched export BODY byte-identical AFTER ref-remap (obj-refs -> target identity, name-refs
-> name string). Name-table ORDER is NOT asserted (the unstable-qsort same-count tie residual is
owner-excluded; body correctness does not depend on it since refs are resolved).

Exit 0 + "PARITY: YES" iff nothing outside the exclusions differs.

Usage: parity_gate.py <native.dx> <ued22.dx>
"""
from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
UNBUILT_HARNESS = ROOT / "dev/docs/spikes/2026-09-02-unbuilt-structure-parity/harness"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(UNBUILT_HARNESS))

from uedcli.upackage import (load_package, read_compact_index, read_fstring,  # noqa: E402
                             read_property_tags)
from uedcli.native.saveorder import _model_polys_map  # noqa: E402

PT_BYTE, PT_INT, PT_BOOL, PT_FLOAT, PT_OBJECT, PT_NAME, PT_ARRAY, PT_STRUCT, PT_STR = \
    1, 2, 3, 4, 5, 6, 9, 10, 13
RF_HasStack = 0x02000000
_POLYS_COUNTER = re.compile(r"^Polys\d+$")
_LI_MASKED_PROPS = {"TimeSeconds", "AIProfile"}


class Ident:
    """Identity resolver for one parsed package: refs -> permutation-stable identity strings."""

    def __init__(self, p) -> None:
        self.p = p
        self.buf = p.buf
        # Polys export -> owning Model identity (so a counter leaf name never enters the identity).
        model_polys = _model_polys_map(p)                      # {model name -> polys name}
        polys_to_model = {v: k for k, v in model_polys.items()}
        self.polys_owner: dict[int, str] = {}
        for i, e in enumerate(p.exports):
            nm = p.names[e["nm"]]
            if (p.object_class_name(i + 1) or "") == "Polys" and nm in polys_to_model:
                mn = polys_to_model[nm]
                self.polys_owner[i] = f"Model {mn}"

    def export_identity(self, i0: int) -> str:
        p = self.p
        cls = p.object_class_name(i0 + 1) or "<Class>"
        chain, outer = [], p.exports[i0]["outer"]
        while outer > 0:
            oe = p.exports[outer - 1]
            chain.append(p.names[oe["nm"]])
            outer = oe["outer"]
        if cls == "Polys" and i0 in self.polys_owner:
            leaf = f"Polys@{self.polys_owner[i0]}"
        else:
            leaf = p.names[p.exports[i0]["nm"]]
        path = ".".join(reversed(chain + [leaf]))
        return f"{cls} {path}"

    def import_identity(self, j: int) -> str:
        p = self.p
        cp, cn, _pi, _on = p.imports[j]
        chain, k = [], j
        while True:
            chain.append(p.names[p.imports[k][3]])
            o = p.imports[k][2]
            if o >= 0:
                break
            k = -o - 1
        return f"import {p.names[cp]}.{p.names[cn]} '{'.'.join(reversed(chain))}'"

    def ref_identity(self, ref: int) -> str:
        if ref == 0:
            return "None"
        if ref > 0:
            return self.export_identity(ref - 1)
        return self.import_identity(-ref - 1)


# --------------------------------------------------------------------------- tagged props

def _canon_value(idt: Ident, t) -> object:
    p = idt.p
    if t.ptype == PT_BOOL:
        return ("bool", t.bool_value)
    if t.ptype == PT_NAME:
        idx, _ = read_compact_index(t.raw, 0)
        return ("name", p.names[idx] if 0 <= idx < len(p.names) else idx)
    if t.ptype == PT_OBJECT:
        ref, _ = read_compact_index(t.raw, 0)
        return ("obj", idt.ref_identity(ref))
    if t.ptype == PT_STRUCT and t.struct_name == "PointRegion":
        ref, pos = read_compact_index(t.raw, 0)
        ileaf = struct.unpack_from("<i", t.raw, pos)[0]
        zn = t.raw[pos + 4]
        return ("region", idt.ref_identity(ref), ileaf, zn)
    # Any other struct/array/primitive: byte-faithful. A nested object ref inside such a value would
    # compare as raw bytes (its ref index may differ across export orders) -> a conservative FALSE
    # FAIL, never a false pass. No such case in the ladder's actors yet; extend if one appears.
    return ("raw", t.raw.hex())


def _canon_props(idt: Ident, pos: int, end: int, *, mask_props: set[str] = frozenset()) -> list:
    tags, _ = read_property_tags(idt.p, pos, end)
    out = []
    for t in tags:
        val = ("MASKED",) if t.name in mask_props else _canon_value(idt, t)
        out.append((t.name, t.array_index, t.struct_name, val))
    return out


def _stateframe(idt: Ident, pos: int) -> tuple:
    """(node identity, probemask) with LatentAction masked; returns (canon, pos_after)."""
    buf = idt.buf
    node, pos = read_compact_index(buf, pos)
    _sn, pos = read_compact_index(buf, pos)
    probemask = struct.unpack_from("<Q", buf, pos)[0]; pos += 8
    pos += 4                                            # LatentAction: masked (stack garbage)
    if node != 0:
        _off, pos = read_compact_index(buf, pos)
    return (idt.ref_identity(node), probemask), pos


# --------------------------------------------------------------------------- binary tails

def _model_tail(idt: Ident, pos: int, end: int) -> list:
    """Canonical token stream for a UModel binary tail (after the leading prop None), mirroring
    `saveorder._walk_model`: literal bytes with each object ref replaced by its target identity."""
    buf = idt.buf
    toks: list = []
    start = [pos]                                       # mutable literal-span cursor
    pos += 25 + 16                                      # FBox(+valid) + FSphere (literal-compared)

    def flush(upto: int) -> None:
        if upto > start[0]:
            toks.append(("b", buf[start[0]:upto]))
        start[0] = upto

    def obj_at(pos: int) -> int:
        ref, npos = read_compact_index(buf, pos)
        flush(pos)
        toks.append(("O", idt.ref_identity(ref)))
        start[0] = npos
        return npos

    for _ in range(2):                                  # Vectors, Points
        n, pos = read_compact_index(buf, pos); pos += 12 * n
    n, pos = read_compact_index(buf, pos)               # Nodes
    for _ in range(n):
        pos += 16 + 8 + 1
        for _ in range(4 + 5 + 1):
            _, pos = read_compact_index(buf, pos)
        pos += 8
    n, pos = read_compact_index(buf, pos)               # Surfs
    for _ in range(n):
        pos = obj_at(pos)                               # Texture
        pos += 4
        for _ in range(4 + 1 + 1):
            _, pos = read_compact_index(buf, pos)
        pos += 4
        pos = obj_at(pos)                               # Actor (brush)
    n, pos = read_compact_index(buf, pos)               # Verts
    for _ in range(n):
        _, pos = read_compact_index(buf, pos)
        _, pos = read_compact_index(buf, pos)
    pos += 4                                            # NumSharedSides
    nz = struct.unpack_from("<i", buf, pos)[0]; pos += 4
    for _ in range(nz):
        pos = obj_at(pos)                               # ZoneActor
        pos += 16
    pos = obj_at(pos)                                   # field_0x54 (Polys)
    n, pos = read_compact_index(buf, pos)               # LightMap
    for _ in range(n):
        pos += 4 + 12
        _, pos = read_compact_index(buf, pos)
        _, pos = read_compact_index(buf, pos)
        pos += 8 + 4
    n, pos = read_compact_index(buf, pos); pos += n     # LightBits
    n, pos = read_compact_index(buf, pos); pos += 25 * n  # Bounds
    n, pos = read_compact_index(buf, pos); pos += 4 * n   # LeafHulls
    n, pos = read_compact_index(buf, pos)               # Leaves
    for _ in range(n):
        for _ in range(3):
            _, pos = read_compact_index(buf, pos)
        pos += 8
    n, pos = read_compact_index(buf, pos)               # Lights
    for _ in range(n):
        pos = obj_at(pos)
    pos += 8
    flush(pos)
    if pos != end:
        raise ValueError(f"model tail not consumed: {pos} != {end}")
    return toks


def _polys_tail(idt: Ident, pos: int, end: int) -> list:
    buf = idt.buf
    toks: list = []
    start = [pos]

    def flush(upto: int) -> None:
        if upto > start[0]:
            toks.append(("b", buf[start[0]:upto]))
        start[0] = upto

    def ref_at(pos: int, kind: str) -> int:
        v, npos = read_compact_index(buf, pos)
        flush(pos)
        toks.append((kind, idt.ref_identity(v) if kind == "O" else idt.p.names[v]))
        start[0] = npos
        return npos

    num = struct.unpack_from("<i", buf, pos)[0]; pos += 8
    for _ in range(num):
        nv, pos = read_compact_index(buf, pos)
        pos += 48 + 12 * nv + 4
        pos = ref_at(pos, "O")                          # Actor (brush owner)
        pos = ref_at(pos, "O")                          # Texture
        pos = ref_at(pos, "N")                          # Item (name)
        _, pos = read_compact_index(buf, pos)
        _, pos = read_compact_index(buf, pos)
        pos += 4
    flush(pos)
    if pos != end:
        raise ValueError(f"polys tail not consumed: {pos} != {end}")
    return toks


def _level_tail(idt: Ident, pos: int, end: int) -> list:
    """Mirrors `saveorder._walk_level`. The `Actors` array is emitted as ONE token = the ordered
    list of SURVIVING (non-None) actor identities (GC-3: null holes ignored, order asserted). The
    trailing TimeSeconds float is masked."""
    buf = idt.buf
    toks: list = []
    start = [pos]

    def flush(upto: int) -> None:
        if upto > start[0]:
            toks.append(("b", buf[start[0]:upto]))
        start[0] = upto

    def obj_at(pos: int) -> int:
        ref, npos = read_compact_index(buf, pos)
        flush(pos)
        toks.append(("O", idt.ref_identity(ref)))
        start[0] = npos
        return npos

    count_off = pos
    num = struct.unpack_from("<i", buf, pos)[0]; pos += 8
    survivors = []
    for _ in range(num):
        ref, pos = read_compact_index(buf, pos)
        if ref != 0:
            survivors.append(idt.ref_identity(ref))
    # Replace count+array bytes (holes included) with the survivor list token (GC-3).
    flush(count_off)
    toks.append(("actors", tuple(survivors)))
    start[0] = pos
    for _ in range(4):                                  # 4 FStrings (URL etc.)
        _, pos = read_fstring(buf, pos)
    nops, pos = read_compact_index(buf, pos)
    for _ in range(nops):
        _, pos = read_fstring(buf, pos)
    pos += 8                                            # 8 literal bytes (pre-Model)
    pos = obj_at(pos)                                   # Model
    nrs, pos = read_compact_index(buf, pos)             # ReachSpecs
    for _ in range(nrs):
        pos += 4
        pos = obj_at(pos)                               # Start
        pos = obj_at(pos)                               # End
        pos += 12 + 1
    flush(pos)                                          # TimeSeconds float (masked)
    toks.append(("M", "level-timeseconds"))
    pos += 4
    start[0] = pos
    _, pos = read_compact_index(buf, pos)               # FirstDeleted
    for _ in range(16):                                 # 16 zone/region refs
        pos = obj_at(pos)
    ntv, pos = read_compact_index(buf, pos)             # TravelInfo
    for _ in range(ntv):
        _, pos = read_fstring(buf, pos)
        _, pos = read_fstring(buf, pos)
    flush(pos)
    if pos != end:
        raise ValueError(f"level tail not consumed: {pos} != {end}")
    return toks


# --------------------------------------------------------------------------- body canonicalisation

def canon_body(idt: Ident, i0: int):
    """Canonical body of export i0, or the sentinel ('MASK', label) for a wholly-masked body."""
    p = idt.p
    e = p.exports[i0]
    cls = p.object_class_name(i0 + 1) or ""
    pos, end = e["soff"], e["soff"] + e["ssize"]
    if cls == "Camera":
        return ("MASK", "camera")                       # viewport state (per-save-random)
    sf = None
    if e["flags"] & RF_HasStack:
        sf, pos = _stateframe(idt, pos)
    if cls == "Model":
        pos = read_property_tags(p, pos, end)[1]
        return ("model", sf, _model_tail(idt, pos, end))
    if cls == "Polys":
        pos = read_property_tags(p, pos, end)[1]
        return ("polys", sf, _polys_tail(idt, pos, end))
    if cls == "Level":
        pos = read_property_tags(p, pos, end)[1]
        return ("level", sf, _level_tail(idt, pos, end))
    mask = _LI_MASKED_PROPS if cls == "LevelInfo" else frozenset()
    return ("actor", sf, _canon_props(idt, pos, end, mask_props=mask))


# --------------------------------------------------------------------------- name/import content

def _fold_name(n: str) -> str:
    return "Polys#" if _POLYS_COUNTER.match(n) else n


def _name_multiset(p) -> dict:
    from collections import Counter
    return Counter(_fold_name(n) for n in p.names)


# --------------------------------------------------------------------------- the gate

def gate(native_path: str, ued_path: str) -> tuple[bool, list[str]]:
    A, B = load_package(native_path), load_package(ued_path)
    ia, ib = Ident(A), Ident(B)
    fails: list[str] = []

    def _hdr(p) -> tuple:
        ver, lic = struct.unpack_from("<HH", p.buf, 4)
        flags = struct.unpack_from("<I", p.buf, 8)[0]
        return ver, lic, flags

    (va, la, fa), (vb, lb, fb) = _hdr(A), _hdr(B)
    for label, x, y in [("version", va, vb), ("licensee", la, lb), ("flags", fa, fb),
                        ("name_count", len(A.names), len(B.names)),
                        ("import_count", len(A.imports), len(B.imports)),
                        ("export_count", len(A.exports), len(B.exports))]:
        if x != y:
            fails.append(f"header {label}: {x!r} != {y!r}")

    na, nb = _name_multiset(A), _name_multiset(B)
    if na != nb:
        fails.append(f"name-table CONTENT differs (counter-folded): "
                     f"only-native={sorted((na - nb).elements())[:12]} "
                     f"only-ued={sorted((nb - na).elements())[:12]}")

    sa = {ia.import_identity(j) for j in range(len(A.imports))}
    sb = {ib.import_identity(j) for j in range(len(B.imports))}
    if sa != sb:
        fails.append(f"import-table CONTENT differs: only-native={sorted(sa - sb)[:8]} "
                     f"only-ued={sorted(sb - sa)[:8]}")

    ids_a = {ia.export_identity(i): i for i in range(len(A.exports))}
    ids_b = {ib.export_identity(i): i for i in range(len(B.exports))}
    if len(ids_a) != len(A.exports):
        fails.append("native export identities not unique (Polys owner keying ambiguous)")
    only_a = sorted(set(ids_a) - set(ids_b))
    only_b = sorted(set(ids_b) - set(ids_a))
    if only_a or only_b:
        fails.append(f"export SET differs: only-native={only_a[:8]} only-ued={only_b[:8]}")
    if "Level MyLevel" not in ids_a or "Level MyLevel" not in ids_b:
        fails.append("Level 'MyLevel' export missing on one side")

    for ident in sorted(set(ids_a) & set(ids_b)):
        try:
            ca = canon_body(ia, ids_a[ident])
            cb = canon_body(ib, ids_b[ident])
        except Exception as ex:                          # decode failure is a hard fail, not a pass
            fails.append(f"BODY {ident}: canonicalise failed: {ex}")
            continue
        if ca != cb:
            fails.append(f"BODY {ident}: canonical bodies differ\n"
                         f"      native={_short(ca)}\n      ued=   {_short(cb)}")
    return not fails, fails


def _short(c, limit: int = 240) -> str:
    s = repr(c)
    return s if len(s) <= limit else s[:limit] + " ..."


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    ok, fails = gate(sys.argv[1], sys.argv[2])
    if ok:
        print("PARITY: YES (modulo GC export-order / counter-names / Actors None-holes + "
              "guid/latent/timeseconds/aiprofile/camera masks)")
        return 0
    print(f"PARITY: NO -- {len(fails)} residual difference(s):")
    for f in fails[:30]:
        print(f"  - {f}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
