#!/usr/bin/env python3
"""Replay one surf's per-lumel shadow trace against a built package, under a chosen IsCsg mask.

Usage: replay_bake.py <pkg.dx> <surf> <light-x,y,z> [extra-mask-bits]
Prints the produced bit plane (hex rows), so it can be diffed against the editor's stored plane.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
import raytrace as R  # noqa: E402
from uedcli.upackage import load_package, read_compact_index, read_property_tags  # noqa: E402

SELF_SHADOW_BIAS = 4.0
PF_BRIGHT_CORNERS = 0x00080000


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def model(path):
    p = load_package(path)
    i0 = next(i for i in range(len(p.exports))
              if (p.object_class_name(i + 1) or "") == "Model"
              and p.names[p.exports[i]["nm"]].lower().startswith("model"))
    e = p.exports[i0]
    buf = p.buf
    pos, end = e["soff"], e["soff"] + e["ssize"]
    pos = read_property_tags(p, pos, end)[1]
    pos += 25 + 16
    nv, pos = read_compact_index(buf, pos)
    vectors = [struct.unpack_from("<3f", buf, pos + 12 * k) for k in range(nv)]
    pos += 12 * nv
    npt, pos = read_compact_index(buf, pos)
    points = [struct.unpack_from("<3f", buf, pos + 12 * k) for k in range(npt)]
    pos += 12 * npt
    n, pos = read_compact_index(buf, pos)
    nodes, node_rings = [], []
    for _ in range(n):
        plane = struct.unpack_from("<4f", buf, pos); pos += 16
        pos += 8
        fl = buf[pos]; pos += 1
        ci = []
        for _ in range(10):
            v, pos = read_compact_index(buf, pos)
            ci.append(v)
        pos += 8
        nodes.append(dict(plane=plane, flags=fl, ivp=ci[0], isurf=ci[1],
                          ifront=ci[2], iback=ci[3], nv=ci[9]))
    n, pos = read_compact_index(buf, pos)
    surfs = []
    for _ in range(n):
        _, pos = read_compact_index(buf, pos)
        flags = struct.unpack_from("<I", buf, pos)[0]; pos += 4
        f = []
        for _ in range(6):
            v, pos = read_compact_index(buf, pos)
            f.append(v)
        pos += 4
        _, pos = read_compact_index(buf, pos)
        surfs.append(dict(flags=flags, pbase=f[0], vnormal=f[1], vtu=f[2], vtv=f[3], ilm=f[4]))
    n, pos = read_compact_index(buf, pos)
    verts = []
    for _ in range(n):
        iv, pos = read_compact_index(buf, pos)
        _, pos = read_compact_index(buf, pos)
        verts.append(iv)
    return nodes, surfs, verts, points, vectors, buf, pos, p


def sub(a, b):
    return tuple(f32(a[k] - b[k]) for k in range(3))


def dot3(a, b):
    return f32(f32(f32(a[0] * b[0]) + f32(a[1] * b[1])) + f32(a[2] * b[2]))


def addv(a, b):
    return tuple(f32(a[k] + b[k]) for k in range(3))


def scale(v, s):
    return tuple(f32(v[k] * s) for k in range(3))


def trace_plane(nodes, surfs, points, vectors, si, rec, light, world_radius):
    """Re-trace one (surf, light) bit-plane exactly as `light.rs::bake_surf` does."""
    s = surfs[si]
    pan, u_size, v_size, u_scale, v_scale = rec["pan"], rec["u"], rec["v"], rec["su"], rec["sv"]
    normal = vectors[s["vnormal"]]
    axes = lumel_axes(vectors[s["vtu"]], vectors[s["vtv"]], normal)
    base = points[s["pbase"]]
    bright = s["flags"] & PF_BRIGHT_CORNERS != 0
    xf = 0x14 if bright else 0x04
    if axes is None:
        return b""
    u_dir, v_dir = axes
    step_u = f32(u_scale - 0.5 / (u_size - 1)) if bright else u_scale
    step_v = f32(v_scale - 0.5 / (v_size - 1)) if bright else v_scale
    origin = addv(addv(addv(base, scale(normal, SELF_SHADOW_BIAS)), scale(u_dir, pan[0])),
                  scale(v_dir, pan[1]))
    if bright:
        origin = addv(addv(origin, scale(v_dir, 0.25)), scale(u_dir, 0.25))
    row_bytes = (u_size + 7) // 8
    wr2 = f32(world_radius * world_radius)
    out = bytearray()
    for _v in range(v_size):
        pnt = origin
        for byteix in range(row_bytes):
            last_clear = False
            acc = 0
            first = byteix * 8
            for bit in range(8):
                if first + bit >= u_size:
                    if last_clear:
                        acc |= (0xFF << bit) & 0xFF
                    break
                d = sub(pnt, light)
                if dot3(d, d) < wr2:
                    last_clear = R.line_clear(nodes, pnt, light, xf, [])
                    if last_clear:
                        acc |= 1 << bit
                pnt = addv(pnt, scale(u_dir, step_u))
            out.append(acc)
        origin = addv(origin, scale(v_dir, step_v))
    return bytes(out)


def main():
    path, si = sys.argv[1], int(sys.argv[2])
    light = tuple(float(x) for x in sys.argv[3].split(","))
    world_radius = float(sys.argv[4])
    extra_mask = int(sys.argv[5], 0) if len(sys.argv) > 5 else 0
    nodes, surfs, verts, points, vectors, buf, pos, p = model(path)
    s = surfs[si]
    # the stored lightmap descriptor gives the exact grid the editor used
    lm_pos = pos
    lm_pos += 4                       # NumSharedSides
    nz = struct.unpack_from("<i", buf, lm_pos)[0]; lm_pos += 4
    for _ in range(nz):
        _, lm_pos = read_compact_index(buf, lm_pos); lm_pos += 16
    _, lm_pos = read_compact_index(buf, lm_pos)
    n, lm_pos = read_compact_index(buf, lm_pos)
    lms = []
    for _ in range(n):
        doff = struct.unpack_from("<i", buf, lm_pos)[0]; lm_pos += 4
        pan = struct.unpack_from("<3f", buf, lm_pos); lm_pos += 12
        cu, lm_pos = read_compact_index(buf, lm_pos)
        cv, lm_pos = read_compact_index(buf, lm_pos)
        su, sv, ila = struct.unpack_from("<ffi", buf, lm_pos); lm_pos += 12
        lms.append((doff, pan, cu, cv, su, sv, ila))
    rec = lms[s["ilm"]]
    _doff, pan, u_size, v_size, u_scale, v_scale, _ila = rec

    normal = vectors[s["vnormal"]]
    tu, tv = vectors[s["vtu"]], vectors[s["vtv"]]
    base = points[s["pbase"]]
    # lumel_axes: u_dir/v_dir orthogonalised from tu/tv against the normal (see light.rs)
    u_dir, v_dir = lumel_axes(tu, tv, normal)
    bright = s["flags"] & PF_BRIGHT_CORNERS != 0
    xf = 0x14 if bright else 0x04
    step_u = f32(u_scale - 0.5 / (u_size - 1)) if bright else u_scale
    step_v = f32(v_scale - 0.5 / (v_size - 1)) if bright else v_scale
    origin = addv(addv(addv(base, scale(normal, SELF_SHADOW_BIAS)), scale(u_dir, pan[0])),
                  scale(v_dir, pan[1]))
    if bright:
        origin = addv(addv(origin, scale(v_dir, 0.25)), scale(u_dir, 0.25))
    row_bytes = (u_size + 7) // 8
    wr2 = f32(world_radius * world_radius)
    out = []
    R.EXTRA_CSG_MASK = extra_mask
    for _v in range(v_size):
        row = bytearray(row_bytes)
        pnt = origin
        for byteix in range(row_bytes):
            last_clear = False
            acc = 0
            first = byteix * 8
            for bit in range(8):
                if first + bit >= u_size:
                    if last_clear:
                        acc |= (0xFF << bit) & 0xFF
                    break
                d = sub(pnt, light)
                if dot3(d, d) < wr2:
                    log = []
                    last_clear = R.line_clear(nodes, pnt, light, xf, log)
                    if last_clear:
                        acc |= 1 << bit
                pnt = addv(pnt, scale(u_dir, step_u))
            row[byteix] = acc
        out.append(bytes(row))
        origin = addv(origin, scale(v_dir, step_v))
    print(f"surf {si} grid {u_size}x{v_size} bright={bright} xf={xf:#x} extra_mask={extra_mask:#x}")
    for r in out:
        print("  " + r.hex())


def lumel_axes(tu, tv, normal):
    """Mirror of light.rs::lumel_axes (adjugate inverse of the texture frame)."""
    def cross(a, b):
        return (f32(f32(a[1] * b[2]) - f32(a[2] * b[1])),
                f32(f32(a[2] * b[0]) - f32(a[0] * b[2])),
                f32(f32(a[0] * b[1]) - f32(a[1] * b[0])))

    c0 = cross(tv, normal)
    det = dot3(tu, c0)
    if abs(det) < 1e-8:
        return None
    rdet = f32(1.0 / det)
    c1 = cross(normal, tu)
    return tuple(f32(x * rdet) for x in c0), tuple(f32(x * rdet) for x in c1)


if __name__ == "__main__":
    main()
