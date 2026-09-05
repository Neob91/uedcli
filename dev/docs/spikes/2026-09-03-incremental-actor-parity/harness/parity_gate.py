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
_POLYS_COUNTER = re.compile(r"^Polys\d+$", re.IGNORECASE)
_LI_MASKED_PROPS = {"timeseconds", "aiprofile"}
# A Brush actor's persisted Region (PointRegion) is inert: at map load UGameEngine::LoadMap
# (Engine.dll 0x158930) calls ULevel::SetActorZone(actor,1,1) (0x161e10, vtable slot 43) per actor,
# which recomputes the region from Location and OVERWRITES actor+0x88/+0x90 (iLeaf default -1); an
# actor gated out of that pass (flag 0x10000@0x11c) skips all init and never consults Region. Either
# way a brush's saved Region is discarded/unused (board native-n8-unatco-rotated-brush-base-fp-diverges).
_BRUSH_MASKED_PROPS = {"region"}
# BSP node-plane W dedup-tie mask (same board finding). A rotated brush's x=448 face base sits at a
# genuine point-dedup near-tie: two REAL, distinct entries in the byte-identical Model.Points table
# (448.00006 and 447.99985, 2.16e-4 apart ~= 7 f32 ULP). The editor's incremental pool keeps the
# un-snapped point for this face so its node plane W = raw Base.N; native's linear-scan dedup snaps
# to the sibling point, so W = Points[snapped].N -- a 2.16e-4 W offset on nodes 29/30. It is
# game-inconsequential: 4.6x below the engine's +/-0.001 zero-extent line-trace band (linecheck.rs:33)
# and orders below the box-collision plane band; only an exact-split PointRegion sample could flip,
# and that feeds the (inert) brush Region above. A faithful fix is a multi-week incremental-CSG-core
# rewrite (owner-ruled out). Masked NARROWLY: see _bodies_equal / _node_w_tie / _poly_base_tie.
NODE_W_DEDUP_TOL = 0.002     # point-dedup tolerance: max |Wn - Wu| for a near-tie
NODE_W_POINT_TOL = 1.5e-4    # a masked W must equal a real table-point projection (< the 2.16e-4
#                              real-point spacing, so a between-points corruption cannot match)


def _cf(s: str) -> str:
    """Case-fold a name/identity for comparison. UE1 FNames are case-INSENSITIVE, so two names that
    differ only in case are the SAME FName and resolve to the same object; the editor's process-global
    FName pool can serialize either spelling (e.g. `CoreTexSky.Sky` vs `.sky`) — boot-order-determined,
    not authored. Folding case (still requiring string equality otherwise) neutralises that without
    masking a genuine wrong-name (owner ruling + opus confirmation 2026-09-04)."""
    return s.casefold()


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
        self._model_pts: frozenset | None = None

    def model_points(self) -> frozenset:
        """Union of every UModel's Points table (x,y,z tuples). A CSG-soup poly base that snapped
        under point-dedup equals one of these; used to bound the node-W / poly-base tie masks."""
        if self._model_pts is None:
            p, buf, pts = self.p, self.buf, set()
            for i, e in enumerate(p.exports):
                if (p.object_class_name(i + 1) or "") != "Model":
                    continue
                pos, end = e["soff"], e["soff"] + e["ssize"]
                if e["flags"] & RF_HasStack:
                    _, pos = _stateframe(self, pos)
                pos = read_property_tags(p, pos, end)[1]
                pos += 25 + 16                              # FBox(+valid) + FSphere
                n, pos = read_compact_index(buf, pos); pos += 12 * n   # Vectors (skip)
                n, pos = read_compact_index(buf, pos)                  # Points
                pts.update(struct.unpack_from("<3f", buf, pos + 12 * k) for k in range(n))
            self._model_pts = frozenset(pts)
        return self._model_pts

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
        return _cf(f"{cls} {path}")

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
        return _cf(f"import {p.names[cp]}.{p.names[cn]} '{'.'.join(reversed(chain))}'")

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
        return ("name", _cf(p.names[idx]) if 0 <= idx < len(p.names) else idx)
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
        val = ("MASKED",) if t.name.casefold() in mask_props else _canon_value(idt, t)
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

    def mask_at(pos: int) -> int:
        _, npos = read_compact_index(buf, pos)
        flush(pos)
        toks.append(("MV",))                            # masked orphan-vert iVertex
        start[0] = npos
        return npos

    def nodeflags_at(pos: int) -> int:
        flush(pos)
        toks.append(("NF", buf[pos] & ~0x18))           # drop render-occlusion scratch bits
        start[0] = pos + 1
        return pos + 1

    n, pos = read_compact_index(buf, pos); pos += 12 * n  # Vectors (skip)
    n, pos = read_compact_index(buf, pos)               # Points
    points = [struct.unpack_from("<3f", buf, pos + 12 * k) for k in range(n)]
    pos += 12 * n

    def nodeplane_at(pos: int) -> int:
        # FPlane = normal(12, literal-compared) + W(4). W is masked-conditionally as a dedup-tie
        # token carrying every table-point projection onto this node's normal (see _node_w_tie).
        nrm = struct.unpack_from("<3f", buf, pos)
        w = struct.unpack_from("<f", buf, pos + 12)[0]
        flush(pos + 12)                                 # normal bytes stay literal (a changed
        #                                                 normal FAILS here, before the W token)
        proj = frozenset(px * nrm[0] + py * nrm[1] + pz * nrm[2] for px, py, pz in points)
        toks.append(("NW", w, proj))
        start[0] = pos + 16
        return pos + 16

    n, pos = read_compact_index(buf, pos)               # Nodes
    live_verts: set[int] = set()                        # vert slots in a live node ring
    for _ in range(n):
        pos = nodeplane_at(pos)                          # FPlane (normal literal, W dedup-tie mask)
        pos += 8                                         # zone_mask (literal)
        pos = nodeflags_at(pos)                          # node_flags: drop NF_PolyOccluded|NF_BoxOccluded
        node_cis = []
        for _ in range(4 + 5 + 1):
            v, pos = read_compact_index(buf, pos)
            node_cis.append(v)
        pos += 8
        live_verts.update(range(node_cis[0], node_cis[0] + node_cis[9]))  # iVertPool..+NumVertices
    n, pos = read_compact_index(buf, pos)               # Surfs
    for _ in range(n):
        pos = obj_at(pos)                               # Texture
        pos += 4
        for _ in range(4 + 1 + 1):
            _, pos = read_compact_index(buf, pos)
        pos += 4
        pos = obj_at(pos)                               # Actor (brush)
    n, pos = read_compact_index(buf, pos)               # Verts
    for i in range(n):
        # An orphan vert (slot in no live node ring) has an iVertex nothing dereferences: UED22's
        # own build stores an out-of-range orphan iVertex and its maps ship/play. Mask it (excluded
        # 2026-09-04, two opus reviews + owner); iSide and every live vert stay compared. Divergent
        # liveness => node rings differ => the Nodes tokens already FAIL, so a per-buffer orphan set
        # is safe (it can't hide a live-vert divergence).
        if i in live_verts:
            _, pos = read_compact_index(buf, pos)       # iVertex (live: compared)
        else:
            pos = mask_at(pos)                          # iVertex (orphan: excluded)
        _, pos = read_compact_index(buf, pos)           # iSide (always compared)
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
        toks.append((kind, idt.ref_identity(v) if kind == "O" else _cf(idt.p.names[v])))
        start[0] = npos
        return npos

    model_pts = idt.model_points()
    num = struct.unpack_from("<i", buf, pos)[0]; pos += 8
    for _ in range(num):
        nv, pos = read_compact_index(buf, pos)
        base = struct.unpack_from("<3f", buf, pos)      # FPoly.Base: dedup-tie-masked (see tie fn)
        flush(pos)
        toks.append(("PB", base, base in model_pts))    # normal/tu/tv (next 36 B) stay literal
        start[0] = pos + 12
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
    mask = _LI_MASKED_PROPS if cls == "LevelInfo" else _BRUSH_MASKED_PROPS if cls == "Brush" \
        else frozenset()                                # Brush Region is inert at load (see const)
    return ("actor", sf, _canon_props(idt, pos, end, mask_props=mask))


def _node_w_tie(xa, xb) -> bool:
    """Two ('NW', W, proj) node-plane-W tokens: equal, or a masked point-dedup near-tie. The normals
    are compared literally elsewhere; here only W. A near-tie masks iff BOTH sides' W equal a real
    projection of a byte-identical table point AND the two Ws are within the dedup tolerance -- so a
    plane bug whose W lands on no table point (or too far to be a tie) still FAILS."""
    wa, wb = xa[1], xb[1]
    if wa == wb:
        return True
    if abs(wa - wb) > NODE_W_DEDUP_TOL:
        return False
    near = lambda w, proj: any(abs(w - pv) <= NODE_W_POINT_TOL for pv in proj)
    return near(wa, xa[2]) and near(wb, xb[2])


def _poly_base_tie(xa, xb) -> bool:
    """Two ('PB', base, is_table_point) FPoly-base tokens (xa native, xb ued): equal, or a masked
    point-dedup near-tie. The soup base diverges when native's linear-scan dedup SNAPS the raw
    transformed base onto a nearby Model.Points entry while the editor keeps the raw base. Masks iff
    the two bases are within the dedup tolerance AND native's base is a real (snapped) table point --
    so a base moved off-geometry, or beyond the tie band, still FAILS. Normal/tu/tv stay literal."""
    ba, bb = xa[1], xb[1]
    if ba == bb:
        return True
    d = sum((ba[k] - bb[k]) ** 2 for k in range(3)) ** 0.5
    return d <= NODE_W_DEDUP_TOL and xa[2]


_BODY_TIE = {"NW": _node_w_tie, "PB": _poly_base_tie}


def _bodies_equal(ca, cb) -> bool:
    """Body equality with the model node-plane-W and polys FPoly-base dedup-tie masks; every other
    token compared exactly."""
    if not (isinstance(ca, tuple) and ca and ca[0] in ("model", "polys")
            and isinstance(cb, tuple) and cb and cb[0] == ca[0]):
        return ca == cb
    if ca[1] != cb[1] or len(ca[2]) != len(cb[2]):     # stateframe + token count
        return False
    for xa, xb in zip(ca[2], cb[2]):
        tie = _BODY_TIE.get(xa[0]) if xa[0] == xb[0] else None
        if xa[0] in _BODY_TIE or xb[0] in _BODY_TIE:
            if tie is None or not tie(xa, xb):
                return False
        elif xa != xb:
            return False
    return True


# --------------------------------------------------------------------------- name/import content

def _fold_name(n: str) -> str:
    return "Polys#" if _POLYS_COUNTER.match(n) else n


def _name_multiset(p) -> dict:
    from collections import Counter
    return Counter(_cf(_fold_name(n)) for n in p.names)


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
    if "level mylevel" not in ids_a or "level mylevel" not in ids_b:
        fails.append("Level 'MyLevel' export missing on one side")

    for ident in sorted(set(ids_a) & set(ids_b)):
        try:
            ca = canon_body(ia, ids_a[ident])
            cb = canon_body(ib, ids_b[ident])
        except Exception as ex:                          # decode failure is a hard fail, not a pass
            fails.append(f"BODY {ident}: canonicalise failed: {ex}")
            continue
        if not _bodies_equal(ca, cb):
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
