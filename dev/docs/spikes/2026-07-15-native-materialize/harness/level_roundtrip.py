"""Byte-exact round-trip of the ULevel ('Level'/'MyLevel') export body.

Parses the ULevel body into fields (Actors Num/Max/refs, FURL, Model ref,
ReachSpecs, trailing raw) then re-serializes and asserts byte-identical to the
original serial extent. Proves the ULevel body layout is fully understood.

Layout under test (v68/69):
  <UObject prop list: None terminator>
  INT32 Num, INT32 Max, Num*ci(actor ref)          # Actors (TTransArray<AActor*>)
  FURL: 4*FString(Protocol,Host,Map,Portal), ci OpCount + OpCount*FString,
        INT32 Port, INT32 Valid
  ci Model ref
  ci ReachSpecCount + ReachSpecCount*FReachSpec(21B: i32 dist, ci start, ci end,
        i32 R, i32 H, i32 flags, u8 pruned)
  <trailing raw bytes to serial end>

Usage: python level_roundtrip.py <map.dx> [<map.dx> ...]
"""
from __future__ import annotations
import struct, sys, glob
sys.path.insert(0, "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli/dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness")
sys.path.insert(0, "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli/dev/docs/spikes/2026-07-15-native-materialize/harness")
from utexture_decode import load_package, ci, read_props
from package_rw import write_ci

RF_HasStack = 0x02000000


def read_fstring(buf, pos):
    length, pos = ci(buf, pos)
    if length < 0:
        n = (-length) * 2
        raw = buf[pos:pos+n]; return ("U", raw), pos + n
    raw = buf[pos:pos+length]; return ("A", raw), pos + length


def enc_fstring(fs):
    kind, raw = fs
    if kind == "U":
        return write_ci(-(len(raw)//2)) + raw
    return write_ci(len(raw)) + raw


def parse_level(p, i0):
    e = p.exports[i0]; so, sz = e["soff"], e["ssize"]; end = so + sz
    buf = p.buf; pos = so
    assert not (e["flags"] & RF_HasStack), "Level unexpectedly has stack"
    # UObject property list (raw span; usually just the None terminator)
    prop_start = pos
    _props, pos = read_props(buf, pos, end, p.names)
    prop_raw = buf[prop_start:pos]
    # Actors
    num = struct.unpack_from("<i", buf, pos)[0]; pos += 4
    mx  = struct.unpack_from("<i", buf, pos)[0]; pos += 4
    refs = []
    for _ in range(num):
        r, pos = ci(buf, pos); refs.append(r)
    # FURL
    url = {}
    for fld in ("Protocol", "Host", "Map", "Portal"):
        url[fld], pos = read_fstring(buf, pos)
    opcount, pos = ci(buf, pos)
    ops = []
    for _ in range(opcount):
        s, pos = read_fstring(buf, pos); ops.append(s)
    port = struct.unpack_from("<i", buf, pos)[0]; pos += 4
    valid = struct.unpack_from("<i", buf, pos)[0]; pos += 4
    # Model ref
    model_ref, pos = ci(buf, pos)
    # ReachSpecs
    rs_count, pos = ci(buf, pos)
    specs = []
    for _ in range(rs_count):
        dist = struct.unpack_from("<i", buf, pos)[0]; pos += 4
        start, pos = ci(buf, pos)
        endr, pos = ci(buf, pos)
        R = struct.unpack_from("<i", buf, pos)[0]; pos += 4
        H = struct.unpack_from("<i", buf, pos)[0]; pos += 4
        flg = struct.unpack_from("<i", buf, pos)[0]; pos += 4
        pr = buf[pos]; pos += 1
        specs.append((dist, start, endr, R, H, flg, pr))
    trailing = buf[pos:end]
    return dict(prop_raw=prop_raw, num=num, mx=mx, refs=refs, url=url, ops=ops,
                port=port, valid=valid, model_ref=model_ref, specs=specs,
                trailing=trailing), (so, end)


def serialize_level(L):
    out = bytearray()
    out += L["prop_raw"]
    out += struct.pack("<ii", L["num"], L["mx"])
    for r in L["refs"]:
        out += write_ci(r)
    for fld in ("Protocol", "Host", "Map", "Portal"):
        out += enc_fstring(L["url"][fld])
    out += write_ci(len(L["ops"]))
    for s in L["ops"]:
        out += enc_fstring(s)
    out += struct.pack("<ii", L["port"], L["valid"])
    out += write_ci(L["model_ref"])
    out += write_ci(len(L["specs"]))
    for (dist, start, endr, R, H, flg, pr) in L["specs"]:
        out += struct.pack("<i", dist) + write_ci(start) + write_ci(endr)
        out += struct.pack("<iii", R, H, flg) + bytes([pr])
    out += L["trailing"]
    return bytes(out)


def main(argv):
    paths = argv[1:]
    npass = nfail = 0
    for path in paths:
        try:
            p = load_package(path)
        except Exception as ex:
            print(f"{path.split('/')[-1]:32s} LOAD-ERR {ex}"); nfail += 1; continue
        lvl = [i for i, e in enumerate(p.exports) if p.class_of_export(i) == "Level"]
        if not lvl:
            print(f"{path.split('/')[-1]:32s} no Level export"); continue
        i0 = lvl[0]
        try:
            L, (so, end) = parse_level(p, i0)
            got = serialize_level(L)
            orig = p.buf[so:end]
            ok = got == orig
            tail = L["trailing"].hex()
            print(f"{path.split('/')[-1]:32s} v{p.version} actors={L['num']} "
                  f"specs={len(L['specs'])} url={L['url']['Map'][1].split(b(0))[0].decode('latin1','replace') if L['url']['Map'][1] else ''!r:12} "
                  f"tail[{len(L['trailing'])}]={tail}  {'BYTE-EXACT' if ok else 'MISMATCH len %d/%d'%(len(got),len(orig))}")
            if ok: npass += 1
            else:
                nfail += 1
                # first diff
                for k in range(min(len(got), len(orig))):
                    if got[k] != orig[k]:
                        print(f"    first diff at body off {k}: got {got[k]:02x} want {orig[k]:02x}")
                        break
        except Exception as ex:
            import traceback; traceback.print_exc()
            print(f"{path.split('/')[-1]:32s} PARSE-ERR {ex}"); nfail += 1
    print(f"\n{npass}/{npass+nfail} Level bodies BYTE-EXACT round-trip")


def b(x):  # helper for bytes literal in fstring
    return bytes([x])


if __name__ == "__main__":
    args = sys.argv
    if len(args) == 2 and args[1] == "--all":
        args = [args[0]] + sorted(glob.glob("/home/neob91/Games/LutrisDX/drive_c/DX/Maps/*.dx"))
    main(args)
