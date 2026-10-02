#!/usr/bin/env python3
"""Decode the UModel lightmap arrays (FLightMapIndex @0xa8, lumel BYTEs @0xb4)
out of a built .dx and run the reconciliation equation that pins the per-lumel
byte count and the USize/VSize semantics.

FLightMapIndex serial (from Engine.dll FLightMapIndex::Serialize @0x1016f9f0):
  +0x00  INT   DataOffset          (raw 4)
  +0x08  FVector Pan               (raw 12: 3 floats)   [via 0x1010c160]
  +0x1c  ci    field_1c            (ci)
  +0x20  ci    field_20            (ci)
  +0x14  FLOAT field_14            (raw 4)
  +0x18  FLOAT field_18            (raw 4)
  +0x04  INT   field_04            (raw 4)
in-memory struct is 40 bytes (0x28); +0x24 is a runtime ptr, not serialized.
"""
import sys, struct, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "bspspike"))
import umodel_parser as UP

def _f32(b, p): return struct.unpack_from("<f", b, p)[0], p + 4
def _i32(b, p): return struct.unpack_from("<i", b, p)[0], p + 4

def parse_lightmap_index(data, pos):
    """Return (record dict, new_pos). record fields keyed by mem offset."""
    data_offset, pos = _i32(data, pos)          # +0x00
    pan_x, pos = _f32(data, pos)                 # +0x08
    pan_y, pos = _f32(data, pos)
    pan_z, pos = _f32(data, pos)
    f1c, pos = UP._ci(data, pos)                 # +0x1c
    f20, pos = UP._ci(data, pos)                 # +0x20
    f14, pos = _f32(data, pos)                   # +0x14 (float?)
    f18, pos = _f32(data, pos)                   # +0x18 (float?)
    f04, pos = _i32(data, pos)                   # +0x04
    return {
        "DataOffset": data_offset, "Pan": (pan_x, pan_y, pan_z),
        "f1c": f1c, "f20": f20, "f14": f14, "f18": f18, "f04": f04,
    }, pos

def walk_to_lightmap(buf, offset, size):
    """Walk the UModel body exactly like parse_model_serial up to the 0xa8 array,
    then parse 0xa8 (FLightMapIndex) and 0xb4 (BYTE) arrays fully."""
    data = buf[offset:offset+size]
    # detect prefix (42 or 57) by trying to reach a sane point — reuse parser's fixed 42,
    # but validate via full parse first.
    m = UP.parse_model_serial(buf, offset, size)  # validates arrays reach EOF
    # Re-walk to find pos at start of 0xa8. Replicate parse_model_serial front matter.
    pos = UP._PREFIX
    _, pos = UP._parse_fvector_array(data, pos)     # Vectors
    _, pos = UP._parse_fvector_array(data, pos)     # Points
    _, pos = UP._parse_array(data, pos, UP._parse_node, "Nodes")
    surfs, pos = UP._parse_array(data, pos, UP._parse_surf, "Surfs")
    _, pos = UP._parse_array(data, pos, UP._parse_vert, "Verts")
    _nss, pos = UP._i32(data, pos)
    _nz, pos = UP._i32(data, pos)
    pos = UP._skip_zone_data(data, pos, _nz)
    _f54, pos = UP._ci(data, pos)
    # now at 0xa8 array
    count, pos = UP._ci(data, pos)
    recs = []
    for _ in range(count):
        r, pos = parse_lightmap_index(data, pos)
        recs.append(r)
    # 0xb4 BYTE array
    bcount, pos = UP._ci(data, pos)
    lumels = data[pos:pos+bcount]
    pos += bcount
    return surfs, recs, lumels, m

def main(path):
    buf = open(path, "rb").read()
    exps = UP.find_model_exports(path)
    exp_idx, name, size, offset = exps[0]   # largest = level model
    print(f"{os.path.basename(path)}: {name} size={size} off={offset:#x}")
    surfs, recs, lumels, m = walk_to_lightmap(buf, offset, size)
    print(f"  surfs={len(surfs)} lightmap_recs={len(recs)} lumel_bytes={len(lumels)}")

    # iLightMap linkage: FBspSurf field the parser calls 'i_actor' (+0x18 mem) is iLightMap.
    ilm = [s.i_actor for s in surfs]
    valid = [i for i in ilm if i != -1 and 0 <= i < len(recs)]
    print(f"  surf.iLightMap: {len(valid)}/{len(surfs)} in-range, "
          f"distinct={len(set(valid))}, range=[{min(valid) if valid else '-'},{max(valid) if valid else '-'}]")

    # Reconciliation: does Sum(f1c * f20) match lumel byte count (x1 or x3)?
    S = sum(r["f1c"] * r["f20"] for r in recs)
    print(f"  Sum(f1c*f20)           = {S}")
    print(f"  lumel byte count       = {len(lumels)}")
    for k in (1, 2, 3, 4):
        print(f"    /{k} = {len(lumels)/k:.2f}   match_x{k}={abs(S*k-len(lumels))<=len(recs)}")

    # DataOffset sanity: last rec's DataOffset + its size should ~ total
    doff = [r["DataOffset"] for r in recs]
    print(f"  DataOffset range=[{min(doff)},{max(doff)}]  (max should be < {len(lumels)})")
    # Check DataOffset ordering & gap = f1c*f20*k
    for k in (1, 3):
        ok = True
        for i in range(1, min(len(recs), 500)):
            gap = recs[i]["DataOffset"] - recs[i-1]["DataOffset"]
            if gap != recs[i-1]["f1c"] * recs[i-1]["f20"] * k:
                ok = False; break
        print(f"  DataOffset consecutive-gap == f1c*f20*{k}: {ok} (first 500)")

    # dump some records
    print("  --- first 6 FLightMapIndex records ---")
    for r in recs[:6]:
        print(f"    DataOffset={r['DataOffset']:>8} Pan=({r['Pan'][0]:.1f},{r['Pan'][1]:.1f},{r['Pan'][2]:.1f}) "
              f"f1c={r['f1c']} f20={r['f20']} f14={r['f14']:.4f} f18={r['f18']:.4f} f04={r['f04']}")
    # field value distributions
    import collections
    print("  f14 sample distinct:", sorted(set(round(r['f14'],4) for r in recs))[:10])
    print("  f18 sample distinct:", sorted(set(round(r['f18'],4) for r in recs))[:10])
    print("  f04 sample distinct:", sorted(set(r['f04'] for r in recs))[:10])
    print("  f1c range:", min(r['f1c'] for r in recs), max(r['f1c'] for r in recs))
    print("  f20 range:", min(r['f20'] for r in recs), max(r['f20'] for r in recs))
    return recs, lumels, surfs

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/00_Intro.dx")
