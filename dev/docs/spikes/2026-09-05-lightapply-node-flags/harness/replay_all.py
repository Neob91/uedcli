#!/usr/bin/env python3
"""Replay the WHOLE lightmap bake of a built package against its own stored LightBits.

For every surf that carries a lightmap record, re-trace every light's bit-plane with the ported
walker and compare to the bytes the editor stored. Variants of the `IsCsg` mask can be switched on
to test which node-flag rule the editor's shadow ray actually used.

Usage: replay_all.py <ued.dx> <trunk-dir> [--csg-exempt 0x08] [--csg-exempt-crossing 0x08]
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
import raytrace as R  # noqa: E402
import replay_bake as B  # noqa: E402
from uedcli import trunk  # noqa: E402
from uedcli.upackage import read_compact_index  # noqa: E402

PF_BRIGHT_CORNERS = 0x00080000


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def read_tail(buf, pos):
    """From the end of Verts: NumSharedSides, Zones, field_0x54, LightMap, LightBits, ... Lights."""
    pos += 4
    nz = struct.unpack_from("<i", buf, pos)[0]; pos += 4
    for _ in range(nz):
        _, pos = read_compact_index(buf, pos); pos += 16
    _, pos = read_compact_index(buf, pos)
    n, pos = read_compact_index(buf, pos)
    lms = []
    for _ in range(n):
        doff = struct.unpack_from("<i", buf, pos)[0]; pos += 4
        pan = struct.unpack_from("<3f", buf, pos); pos += 12
        cu, pos = read_compact_index(buf, pos)
        cv, pos = read_compact_index(buf, pos)
        su, sv, ila = struct.unpack_from("<ffi", buf, pos); pos += 12
        lms.append(dict(doff=doff, pan=pan, u=cu, v=cv, su=su, sv=sv, ila=ila))
    nb, pos = read_compact_index(buf, pos)
    bits = buf[pos:pos + nb]; pos += nb
    n, pos = read_compact_index(buf, pos); pos += 25 * n
    n, pos = read_compact_index(buf, pos); pos += 4 * n
    n, pos = read_compact_index(buf, pos)
    for _ in range(n):
        for _ in range(3):
            _, pos = read_compact_index(buf, pos)
        pos += 8
    n, pos = read_compact_index(buf, pos)
    lights = []
    for _ in range(n):
        r, pos = read_compact_index(buf, pos)
        lights.append(r)
    return lms, bits, lights


def main():
    pkg, trunk_dir = sys.argv[1], sys.argv[2]
    exempt = 0
    exempt_cross = 0
    for i, a in enumerate(sys.argv):
        if a == "--csg-exempt":
            exempt = int(sys.argv[i + 1], 0)
        if a == "--csg-exempt-crossing":
            exempt_cross = int(sys.argv[i + 1], 0)
    R.EXTRA_CSG_MASK = exempt
    R.EXTRA_CSG_MASK_CROSSING = exempt_cross

    nodes, surfs, verts, points, vectors, buf, pos, p = B.model(pkg)
    lms, bits, lightrefs = read_tail(buf, pos)
    if "--brightcorners-nodeflag" in sys.argv:
        # Hypothesis: at LIGHT APPLY time a node whose surf carries PF_BrightCorners also carries
        # NF_BrightCorners (0x10) -- the same bit NF_BoxOccluded uses, transient, not serialized.
        for n in nodes:
            if n["isurf"] >= 0 and surfs[n["isurf"]]["flags"] & PF_BRIGHT_CORNERS:
                n["flags"] |= 0x10
    if "--clear-saved-08" in sys.argv:
        for n in nodes:
            n["flags"] &= ~0x08
    if "--flags" in sys.argv:
        # Replace the SAVED node flags with the LIVE ones a probe captured at LIGHT APPLY time
        # (`NODE <i> flags=0x.. nv=..` lines). This is the whole question: do the live flags explain
        # the golden's stored bit-planes?
        path = sys.argv[sys.argv.index("--flags") + 1]
        live = {}
        for line in Path(path).read_text(errors="replace").splitlines():
            if line.strip().startswith("NODE "):
                parts = line.split()
                live[int(parts[1])] = int(parts[2].split("=")[1], 16)
        for i, n in enumerate(nodes):
            if i in live:
                n["flags"] = live[i]
        print(f"applied {len(live)} live node flags from {path}")

    lvl, _ = trunk.read_level(Path(trunk_dir))
    lights = []
    for name in lvl.order:
        a = lvl.actors[name]
        if not a.cls.endswith("Light"):
            continue
        props = dict(a.props)
        loc = tuple(f32(x) for x in (a.location or (0.0, 0.0, 0.0)))
        radius = float(props.get("LightRadius", 64))
        lights.append((name, loc, f32(25.0 * (radius + 1))))
    by_name = {n.lower(): i for i, (n, _, _) in enumerate(lights)}
    idname = {i + 1: p.names[p.exports[i]["nm"]].lower() for i in range(len(p.exports))}

    ok = bad = 0
    for si, s in enumerate(surfs):
        if s["ilm"] < 0:
            continue
        rec = lms[s["ilm"]]
        # the editor's own run for this surf
        run = []
        k = rec["ila"]
        while k >= 0 and k < len(lightrefs) and lightrefs[k] != 0 and lightrefs[k] != -1:
            run.append(idname.get(lightrefs[k], "?"))
            k += 1
        rb = (rec["u"] + 7) // 8
        plane_len = rb * rec["v"]
        off = rec["doff"]
        for j, lname in enumerate(run):
            li = by_name.get(lname)
            if li is None:
                print(f"surf {si}: unknown light {lname}")
                continue
            got = B.trace_plane(nodes, surfs, points, vectors, si, rec,
                                lights[li][1], lights[li][2])
            want = bits[off + j * plane_len: off + (j + 1) * plane_len]
            if got == want:
                ok += 1
            else:
                bad += 1
                print(f"surf {si:3d} light {lname:10s} MISMATCH\n   got  {got.hex()}\n   want {want.hex()}")
    print(f"\nplanes byte-identical: {ok}, mismatched: {bad}")


if __name__ == "__main__":
    main()
