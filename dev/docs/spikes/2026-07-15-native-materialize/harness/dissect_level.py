"""Dissect the ULevel ('Level') export body in a real .dx, empirically.

Locates the single Level export, skips its UObject tagged-property list, then
decodes the ULevel body structure by hand: the Actors array (raw INT32 Num + INT32
Max + Num*ci object-refs — a TTransArray, NOT a ci-count TArray), the FURL, the
Model ref, the ReachSpecs TArray (ci count), and the trailing block. Confirms element
0 is LevelInfo, element 1 is the Default Brush.

Usage: python dissect_level.py <map.dx>
"""
from __future__ import annotations
import struct, sys
sys.path.insert(0, "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli/dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness")
from utexture_decode import load_package, ci, read_props

RF_HasStack = 0x02000000


def resolve_ref(p, ref):
    """object ref -> (kind, class, name) for display."""
    if ref == 0:
        return ("null", None, "None")
    if ref > 0:
        e = p.exports[ref - 1]
        return ("exp", p.class_of_export(ref - 1), p.names[e["nm"]])
    j = -ref - 1
    imp = p.imports[j]
    return ("imp", p.names[imp[1]], p.names[imp[3]])


def main(argv):
    path = argv[1]
    p = load_package(path)
    print(f"{path.split('/')[-1]} v{p.version}: names={len(p.names)} imports={len(p.imports)} exports={len(p.exports)}")

    # find the Level export
    lvl = [i for i, e in enumerate(p.exports) if p.class_of_export(i) == "Level"]
    print(f"Level exports: {[ (i, p.names[p.exports[i]['nm']]) for i in lvl ]}")
    if not lvl:
        # LevelInfo/Level naming: also check exports named 'MyLevel' or class 'Level'
        return 1
    i0 = lvl[0]
    e = p.exports[i0]
    so, sz = e["soff"], e["ssize"]
    end = so + sz
    buf = p.buf
    print(f"Level export[{i0}] name={p.names[e['nm']]} flags={e['flags']:#010x} "
          f"HasStack={bool(e['flags']&RF_HasStack)} soff={so:#x} ssize={sz} end={end:#x}")

    pos = so
    # StateFrame? Level is a UObject not an AActor; RF_HasStack likely clear.
    if e["flags"] & RF_HasStack:
        node, pos = ci(buf, pos); _st, pos = ci(buf, pos); pos += 12
        if node != 0:
            _o, pos = ci(buf, pos)
        print(f"  skipped StateFrame -> pos={pos-so} into body")

    # UObject tagged-property list
    props, pos = read_props(buf, pos, end, p.names)
    print(f"  property list: {len(props)} props, ends at body offset {pos-so} (abs {pos:#x})")
    for k, v in list(props.items())[:20]:
        print(f"     {k} = {v}")

    # ---- ULevel body starts here ----
    print(f"\n  === ULevel body @ body offset {pos-so} ===")
    hexdump(buf, pos, 32, so)

    # ULevelBase::Serialize -> Actors TTransArray: raw INT Num + raw INT Max + Num*ci(ref)
    num = struct.unpack_from("<i", buf, pos)[0]; pos += 4
    mx  = struct.unpack_from("<i", buf, pos)[0]; pos += 4
    print(f"  [Actors] Num={num} Max={mx}  (n exports={len(p.exports)}, "
          f"n RF_HasStack={sum(1 for x in p.exports if x['flags']&RF_HasStack)})")
    refs = []
    for k in range(num):
        r, pos = ci(buf, pos)
        refs.append(r)
    print(f"  read {len(refs)} refs, pos now at body offset {pos-so} (end {end-so})")
    for k in list(range(min(5, len(refs)))) + list(range(max(0,len(refs)-2), len(refs))):
        print(f"     Actors[{k}] ref={refs[k]:>5d} -> {resolve_ref(p, refs[k])}")
    nulls = sum(1 for r in refs if r == 0)
    from collections import Counter
    cls_hist = Counter(resolve_ref(p, r)[1] for r in refs if r != 0)
    print(f"     null refs (deleted slots): {nulls}; class histogram: {dict(cls_hist.most_common(8))}")

    # After Actors: FURL
    print(f"\n  === FURL @ body offset {pos-so} ===")
    hexdump(buf, pos, 48, so)
    urlpos = pos
    fields = {}
    for fld in ("Protocol", "Host", "Map", "Portal"):
        s, urlpos = read_fstring(buf, urlpos)
        fields[fld] = s
    opcount, urlpos = ci(buf, urlpos)
    ops = []
    for _ in range(opcount):
        s, urlpos = read_fstring(buf, urlpos)
        ops.append(s)
    port = struct.unpack_from("<i", buf, urlpos)[0]; urlpos += 4
    valid = struct.unpack_from("<i", buf, urlpos)[0]; urlpos += 4
    print(f"  FURL: Protocol={fields['Protocol']!r} Host={fields['Host']!r} "
          f"Map={fields['Map']!r} Portal={fields['Portal']!r} Op={ops} Port={port} Valid={valid}")
    print(f"  after FURL @ body offset {urlpos-so}")
    hexdump(buf, urlpos, 32, so)
    pos = urlpos

    # ULevel::Serialize adds: Model ref (ci), ReachSpecs TArray, then trailing.
    model_ref, pos = ci(buf, pos)
    print(f"  Model ref = {model_ref} -> {resolve_ref(p, model_ref)}  @ body offset {pos-so}")
    hexdump(buf, pos, 32, so)
    rs_count, pos = ci(buf, pos)
    print(f"  [ReachSpecs] ci count = {rs_count} @ body offset {(pos)-so}; "
          f"if 21B each -> reachspecs end at body offset {(pos + rs_count*21)-so} (body end {end-so})")
    # decode first few reachspecs (21B: INT dist, ci start, ci end, INT R, INT H, INT flags, BYTE pruned)
    rpos = pos
    for k in range(min(rs_count, 4)):
        dist = struct.unpack_from("<i", buf, rpos)[0]; rpos += 4
        start, rpos = ci(buf, rpos)
        endr, rpos = ci(buf, rpos)
        R = struct.unpack_from("<i", buf, rpos)[0]; rpos += 4
        H = struct.unpack_from("<i", buf, rpos)[0]; rpos += 4
        flg = struct.unpack_from("<i", buf, rpos)[0]; rpos += 4
        pr = buf[rpos]; rpos += 1
        print(f"     ReachSpec[{k}] dist={dist} start={start}->{resolve_ref(p,start)[2]} "
              f"end={endr}->{resolve_ref(p,endr)[2]} R={R} H={H} flags={flg:#x} pruned={pr}")
    # skip all reachspecs assuming 21B and dump what's after
    after = pos
    # do a proper skip using ci for start/end
    for k in range(rs_count):
        after += 4
        _s, after = ci(buf, after)
        _e, after = ci(buf, after)
        after += 13  # INT R + INT H + INT flags + BYTE pruned
    print(f"\n  === after ReachSpecs @ body offset {after-so} (body end {end-so}, remaining {end-after}) ===")
    hexdump(buf, after, min(64, end-after), so)


def read_fstring(buf, pos):
    length, pos = ci(buf, pos)
    if length < 0:
        n = (-length) * 2
        s = buf[pos:pos+n-2].decode("utf-16-le", "replace")
        return s, pos + n
    else:
        s = buf[pos:pos+length-1].decode("latin-1") if length else ""
        return s, pos + length


def hexdump(buf, pos, n, base):
    row = buf[pos:pos+n]
    for off in range(0, len(row), 16):
        chunk = row[off:off+16]
        hexs = " ".join(f"{b:02x}" for b in chunk)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"    +{pos-base+off:5d}  {hexs:<48s}  {asc}")


if __name__ == "__main__":
    main(sys.argv)
