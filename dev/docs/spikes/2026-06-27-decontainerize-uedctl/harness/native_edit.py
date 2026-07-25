"""End-to-end test of the native package WRITER's hard path: synthesize a changed
object body and recompute offsets (not the verbatim round-trip of `write_full`).

We edit a real `.dx` natively — bump one `Light`'s `LightBrightness` — by appending a
modified copy of its body at end-of-data and repointing that export's SerialOffset/Size,
leaving every other body at its original offset (so bodies that contain internal absolute
file offsets — texture `FMipmap` WidthOffset, mesh lazy arrays, the Model — are NOT
relocated and stay valid). Then re-parse the output and assert:
  - it parses to EOF (container still valid after offset recompute),
  - the edited Light now decodes with the new brightness,
  - a sample of other exports' bodies are byte-identical to the original.

This proves: locate-a-property-in-a-real-body + synthesize a (possibly resized) body +
recompute table/export offsets -> a structurally valid package. (Relocating bodies that
carry internal absolute offsets needs offset patching — documented, not done here.)

Usage: python native_edit.py <map.dx> [out.dx]
"""
from __future__ import annotations

import struct
import sys

sys.path.insert(0, ".")
from utexture_decode import ci
from package_rw import Pkg

RF_HasStack = 0x02000000
# Pkg.exports tuples: (cls, sup, outer, nm, flags, ssize, soff)
CLS, SUP, OUTER, NM, FL, SSIZE, SOFF = range(7)


def _names(p):
    return [n[0].split(b"\x00", 1)[0].decode("latin-1") for n in p.names]


def _class_of(p, i, names):
    cref = p.exports[i][CLS]
    if cref == 0:
        return "Class"
    if cref < 0:
        return names[p.imports[-cref - 1][3]]
    return names[p.exports[cref - 1][NM]]


def _skip_stateframe(buf, pos, flags):
    if flags & RF_HasStack:
        node, pos = ci(buf, pos)
        _stnode, pos = ci(buf, pos)
        pos += 12                       # ProbeMask u64 + LatentAction u32
        if node != 0:
            _off, pos = ci(buf, pos)
    return pos


def find_byte_prop_value_offset(buf, body_start, body_end, names, propname):
    """Walk the property list; return the absolute offset of `propname`'s value byte
    (Byte props only). Returns None if not found."""
    pos = body_start
    while pos < body_end:
        nidx, pos = ci(buf, pos)
        nm = names[nidx]
        if nm == "None":
            return None
        info = buf[pos]; pos += 1
        ptype = info & 0x0F
        size_code = (info >> 4) & 0x07
        array = info & 0x80
        if ptype == 10:                 # struct name
            _s, pos = ci(buf, pos)
        if size_code <= 4:
            size = {0: 1, 1: 2, 2: 4, 3: 12, 4: 16}[size_code]
        elif size_code == 5:
            size = buf[pos]; pos += 1
        elif size_code == 6:
            size = struct.unpack_from("<H", buf, pos)[0]; pos += 2
        else:
            size = struct.unpack_from("<I", buf, pos)[0]; pos += 4
        if ptype == 3:                  # bool: value in info, no bytes
            continue
        if array:
            b = buf[pos]; pos += 1
            if b >= 0x80:
                pos += 1 if (b & 0xC0) == 0x80 else 3
        if nm == propname and ptype == 1 and size == 1:
            return pos                  # the single value byte
        pos += size
    return None


def main(argv):
    path = argv[1]
    out = argv[2] if len(argv) > 2 else "/tmp/native_edit_out.dx"
    p = Pkg(path)
    names = _names(p)

    # pick the first Light with a LightBrightness byte prop
    target = None
    for i, e in enumerate(p.exports):
        if _class_of(p, i, names) != "Light" or e[SSIZE] <= 0:
            continue
        bstart = _skip_stateframe(p.buf, e[SOFF], e[FL])
        off = find_byte_prop_value_offset(p.buf, bstart, e[SOFF] + e[SSIZE],
                                          names, "LightBrightness")
        if off is not None:
            target = (i, off)
            break
    if target is None:
        print("no Light with an explicit LightBrightness found"); return 1
    idx, valoff = target
    e = p.exports[idx]
    old = p.buf[valoff]
    new = (old + 50) % 256
    body = bytearray(p.buf[e[SOFF]:e[SOFF] + e[SSIZE]])
    body[valoff - e[SOFF]] = new
    print(f"editing export {idx} ({names[e[NM]]}): LightBrightness {old} -> {new}")

    # re-layout: header | names | origdata | newbody | imports | exports
    names_b = p.enc_names()
    origdata = p.buf[p.nameend:p.impoff]
    nameoff = p.headerlen
    dataoff = nameoff + len(names_b)
    newbody_off = dataoff + len(origdata)
    impoff = newbody_off + len(body)
    # rebuild exports with the edited one repointed; others keep original soff
    new_exports = []
    for j, (cls, sup, outer, nm, fl, ssize, soff) in enumerate(p.exports):
        if j == idx:
            # body unchanged size here, but soff MOVES -> exercises export-offset recompute
            new_exports.append((cls, sup, outer, nm, fl, len(body), newbody_off))
        else:
            shift = dataoff - p.nameend       # 0 (names same size) — robustness only
            new_exports.append((cls, sup, outer, nm, fl, ssize, soff + shift))
    p.exports = new_exports
    exports_b = p.enc_exports()
    expoff = impoff + len(p.enc_imports())
    p.nameoff, p.impoff, p.expoff = nameoff, impoff, expoff
    blob = p.enc_header() + names_b + origdata + bytes(body) + p.enc_imports() + exports_b
    open(out, "wb").write(blob)
    print(f"wrote {out} ({len(blob)} bytes; original {len(p.buf)})")

    # re-parse and validate (Pkg.__init__ raises if the export table doesn't reach EOF)
    q = Pkg(out)
    qe = q.exports[idx]
    bstart = _skip_stateframe(q.buf, qe[SOFF], qe[FL])
    voff = find_byte_prop_value_offset(q.buf, bstart, qe[SOFF] + qe[SSIZE],
                                       _names(q), "LightBrightness")
    roundtrip_val = q.buf[voff]
    orig = Pkg(path)
    sample_ok = all(
        q.buf[q.exports[k][SOFF]:q.exports[k][SOFF] + q.exports[k][SSIZE]]
        == orig.buf[orig.exports[k][SOFF]:orig.exports[k][SOFF] + orig.exports[k][SSIZE]]
        for k in (0, 100, 1000, 2000, len(q.exports) - 1) if k != idx
    )
    print("re-parsed cleanly to EOF: True (Pkg validates export table reaches EOF)")
    print(f"edited Light brightness on re-read: {roundtrip_val} (expected {new}) -> "
          f"{'OK' if roundtrip_val == new else 'FAIL'}")
    print(f"sampled other exports byte-identical: {'OK' if sample_ok else 'FAIL'}")
    return 0 if roundtrip_val == new and sample_ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
