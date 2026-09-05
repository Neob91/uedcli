#!/usr/bin/env python3
"""Replay native's `linecheck::seg_clear` over a built package's BSP, printing the walk."""
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from uedcli.upackage import load_package, read_compact_index, read_property_tags  # noqa: E402

EPS = 0.001
NF_NOT_CSG, NF_NOT_VIS, NF_BRIGHT, NF_IS_NEW = 0x01, 0x04, 0x10, 0x20


def nodes(path):
    p = load_package(path)
    i0 = next(i for i in range(len(p.exports))
              if (p.object_class_name(i + 1) or "") == "Model"
              and p.names[p.exports[i]["nm"]].lower().startswith("model"))
    e = p.exports[i0]
    buf = p.buf
    pos, end = e["soff"], e["soff"] + e["ssize"]
    pos = read_property_tags(p, pos, end)[1]
    pos += 25 + 16
    n, pos = read_compact_index(buf, pos); pos += 12 * n
    npt, pos = read_compact_index(buf, pos)
    points = [struct.unpack_from("<3f", buf, pos + 12 * k) for k in range(npt)]
    pos += 12 * npt
    n, pos = read_compact_index(buf, pos)
    out = []
    for _ in range(n):
        plane = struct.unpack_from("<4f", buf, pos); pos += 16
        pos += 8
        fl = buf[pos]; pos += 1
        ci = []
        for _ in range(10):
            v, pos = read_compact_index(buf, pos)
            ci.append(v)
        pos += 8
        out.append(dict(plane=plane, flags=fl, ivp=ci[0], isurf=ci[1],
                        ifront=ci[2], iback=ci[3], nv=ci[9]))
    return out, points


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def dot(pl, v):
    return f32(f32(f32(pl[0] * v[0]) + f32(pl[1] * v[1])) + f32(pl[2] * v[2])) - pl[3]


EXTRA_CSG_MASK = 0           # experiment: extra NodeFlags bits exempting a node at EVERY site
EXTRA_CSG_MASK_CROSSING = 0  # experiment: extra bits exempting a node at CROSSING sites only


def is_csg(nd, xf, strip):
    mask = ((xf & ~NF_BRIGHT) if strip else xf) | NF_NOT_CSG | NF_IS_NEW | EXTRA_CSG_MASK
    if not strip:
        mask |= EXTRA_CSG_MASK_CROSSING
    return nd["nv"] > 0 and (nd["flags"] & mask) == 0


def child(nd, side):
    return nd["iback"] if side == 1 else nd["ifront"]


def combine(side, state, csg):
    return (state or csg) if side == 1 else (state and not csg)


def seg(nds, inode, p1, p2, state, xf, seen, depth, log, indent=0):
    while True:
        if depth[0] > 4096:
            return True
        if inode == -1:
            if state:
                seen[0] = True
                log.append(f"{'  '*indent}TERM clear (state=True)")
                return True
            if seen[0]:
                log.append(f"{'  '*indent}TERM BLOCKED (state=False, seen_empty=True)")
                return False
            log.append(f"{'  '*indent}TERM clear (bright-corners suppression)"
                       if xf & NF_BRIGHT else f"{'  '*indent}TERM BLOCKED (state=False)")
            return bool(xf & NF_BRIGHT)
        nd = nds[inode]
        d1, d2 = dot(nd["plane"], p1), dot(nd["plane"], p2)
        if d1 > -EPS and d2 > -EPS:
            csg = is_csg(nd, xf, True)
            state = combine(1, state, csg)
            log.append(f"{'  '*indent}n{inode} whole FRONT d1={d1:.4f} d2={d2:.4f} "
                       f"csg={csg} fl=0x{nd['flags']:02x} nv={nd['nv']} surf={nd['isurf']} -> state={state}")
            inode = child(nd, 1); depth[0] += 1; continue
        if d1 < EPS and d2 < EPS:
            csg = is_csg(nd, xf, True)
            state = combine(0, state, csg)
            log.append(f"{'  '*indent}n{inode} whole BACK  d1={d1:.4f} d2={d2:.4f} "
                       f"csg={csg} fl=0x{nd['flags']:02x} nv={nd['nv']} surf={nd['isurf']} -> state={state}")
            inode = child(nd, 0); depth[0] += 1; continue
        t = f32(d2 / f32(d1 - d2))
        mid = tuple(f32(p2[k] + f32(f32(p2[k] - p1[k]) * t)) for k in range(3))
        near = 1 if d2 > 0.0 else 0
        far = 1 - near
        csg = is_csg(nd, xf, False)
        log.append(f"{'  '*indent}n{inode} CROSS d1={d1:.4f} d2={d2:.4f} near={'F' if near else 'B'} "
                   f"csg={csg} fl=0x{nd['flags']:02x} nv={nd['nv']} surf={nd['isurf']} mid={mid}")
        if not seg(nds, child(nd, near), mid, p2, combine(near, state, csg), xf, seen,
                   depth, log, indent + 1):
            return False
        state = combine(far, state, csg)
        inode = child(nd, far)
        p2 = mid
        depth[0] += 1


def line_clear(nds, start, end, xf, log):
    seen = [False]
    return seg(nds, 0, end, start, False, xf, seen, [0], log)


if __name__ == "__main__":
    nds, pts = nodes(sys.argv[1])
    a = tuple(float(x) for x in sys.argv[2].split(","))
    b = tuple(float(x) for x in sys.argv[3].split(","))
    xf = int(sys.argv[4], 0)
    log = []
    r = line_clear(nds, a, b, xf, log)
    print("\n".join(log))
    print("RESULT clear =", r)


def descend(nds, p):
    """Point descent: report the node chain and the side of the last CSG node crossed."""
    i, last = 0, None
    chain = []
    while i != -1:
        nd = nds[i]
        d = dot(nd["plane"], p)
        side = 1 if d >= 0 else 0
        csg = is_csg(nd, 0, False)
        chain.append(f"n{i}(d={d:.3f},{'F' if side else 'B'},csg={csg},surf={nd['isurf']},nv={nd['nv']})")
        if csg:
            last = side
        i = child(nd, side)
    return chain, last
