"""Diff the per-lightmap light RUNS of two built packages (Model.Lights region 2)."""
import struct
import sys

sys.path.insert(0, '.')
sys.path.insert(0, 'dev/docs/spikes/2026-09-03-incremental-actor-parity/harness')
from uedcli.upackage import load_package, read_compact_index, read_property_tags
import parity_gate as g


def walk(path):
    p = load_package(path)
    idt = g.Ident(p)
    for i, e in enumerate(p.exports):
        if (p.object_class_name(i + 1) or "") == "Model" and p.names[e["nm"]].lower() == "model2":
            break
    buf = p.buf
    pos, end = e["soff"], e["soff"] + e["ssize"]
    pos = read_property_tags(p, pos, end)[1]
    pos += 25 + 16
    n, pos = read_compact_index(buf, pos); pos += 12 * n          # Vectors
    n, pos = read_compact_index(buf, pos); pos += 12 * n          # Points
    nn, pos = read_compact_index(buf, pos)                        # Nodes
    for _ in range(nn):
        pos += 16 + 8 + 1
        for _ in range(10):
            _, pos = read_compact_index(buf, pos)
        pos += 8
    ns, pos = read_compact_index(buf, pos)                        # Surfs
    surfs = []
    for _ in range(ns):
        _, pos = read_compact_index(buf, pos); pos += 4
        f = []
        for _ in range(6):
            v, pos = read_compact_index(buf, pos); f.append(v)
        pos += 4
        a, pos = read_compact_index(buf, pos)
        surfs.append((f[5], idt.ref_identity(a), f))              # (iLightMap, actor, fields)
    nv, pos = read_compact_index(buf, pos)                        # Verts
    for _ in range(nv):
        _, pos = read_compact_index(buf, pos); _, pos = read_compact_index(buf, pos)
    pos += 4
    nz = struct.unpack_from("<i", buf, pos)[0]; pos += 4
    for _ in range(nz):
        _, pos = read_compact_index(buf, pos); pos += 16
    _, pos = read_compact_index(buf, pos)                         # Polys
    nlm, pos = read_compact_index(buf, pos)                       # LightMap
    lms = []
    for _ in range(nlm):
        off = struct.unpack_from("<i", buf, pos)[0]; pos += 16
        _tex, pos = read_compact_index(buf, pos)
        la, pos = read_compact_index(buf, pos)
        pos += 12
        lms.append((off, la))
    nlb, pos = read_compact_index(buf, pos); pos += nlb           # LightBits
    n, pos = read_compact_index(buf, pos); pos += 25 * n          # Bounds
    n, pos = read_compact_index(buf, pos); pos += 4 * n           # LeafHulls
    n, pos = read_compact_index(buf, pos)                         # Leaves
    for _ in range(n):
        for _ in range(3):
            _, pos = read_compact_index(buf, pos)
        pos += 8
    n, pos = read_compact_index(buf, pos)                         # Lights
    lights = []
    for _ in range(n):
        v, pos = read_compact_index(buf, pos)
        lights.append(idt.ref_identity(v))
    return surfs, lms, lights


def runs(lms, lights):
    out = {}
    for i, (off, la) in enumerate(lms):
        if la < 0 or la >= len(lights):
            out[i] = None
            continue
        r = []
        j = la
        while j < len(lights) and lights[j] != "None":
            r.append(lights[j]); j += 1
        out[i] = tuple(r)
    return out


sn, ln, gn = walk(sys.argv[1])
su, lu, gu = walk(sys.argv[2])
print("lights len", len(gn), len(gu), " lightmaps", len(ln), len(lu))
rn, ru = runs(ln, gn), runs(lu, gu)
bad = 0
for i in sorted(set(rn) & set(ru)):
    if rn[i] != ru[i]:
        bad += 1
        owner = sn[[k for k, s in enumerate(sn) if s[0] == i][0]][1] if any(s[0] == i for s in sn) else "?"
        isurf = [k for k, s in enumerate(sn) if s[0] == i]
        print(f"LM[{i}] surf={isurf} owner={owner}\n    nat={rn[i]}\n    ued={ru[i]}")
        if bad > 12:
            print("  ..."); break
print("differing runs:", bad)
