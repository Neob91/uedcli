#!/usr/bin/env python3
"""Validate the candidate normal model against EVERY plane-bits-differing Pass-1 node:

  editor node normal  ==  SafeNormalSlow( X . CalcNormal(local ring) )      [MODEL]
  native node normal  ==  the currently-shipped path (authored / calc(world) / vec_xform)

with X = R (unscaled; identity when no Rotation), or `editor_vector_xform` (scaled, mirror
included; local ring UNREVERSED).  All arithmetic replicates the Rust ops bit-for-bit
(f32 per-op; NormalizeSlow inv = f32(1/f32(sqrt_f64(mag2)))).

Prints: per-class explained/unexplained counts for the differing nodes' normals, matching on
(x,y,z) bits up to global sign (subtract store-time Reverse).
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vdb_lib as V  # noqa: E402
HARNESS29 = Path(__file__).resolve().parents[2] / "2026-08-29-unatco-repart-live-diff/harness"
sys.path.insert(0, str(HARNESS29))
from pass1_compare import parse_native, read_bin  # noqa: E402
from uedcli import rotation as ROT                # noqa: E402


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def bits(x):
    return struct.unpack("<I", struct.pack("<f", x))[0]


def calc_normal(verts):
    # Verts are f32 in the engine BEFORE any arithmetic -- pre-cast, then subtract in f32.
    verts = [[f32(c) for c in v] for v in verts]
    n = [0.0, 0.0, 0.0]
    for i in range(2, len(verts)):
        a = [f32(verts[i - 1][j] - verts[0][j]) for j in range(3)]
        b = [f32(verts[i][j] - verts[0][j]) for j in range(3)]
        c = [f32(f32(a[1] * b[2]) - f32(a[2] * b[1])),
             f32(f32(a[2] * b[0]) - f32(a[0] * b[2])),
             f32(f32(a[0] * b[1]) - f32(a[1] * b[0]))]
        n = [f32(n[j] + c[j]) for j in range(3)]
    mag2 = f32(f32(f32(n[0] * n[0]) + f32(n[1] * n[1])) + f32(n[2] * n[2]))
    if mag2 < 1e-8:
        return None
    inv = f32(1.0 / f32(__import__("math").sqrt(mag2)))
    return [f32(n[j] * inv) for j in range(3)]


def sns(v):
    mag2 = f32(f32(f32(v[0] * v[0]) + f32(v[1] * v[1])) + f32(v[2] * v[2]))
    if mag2 < 1e-8:
        return None
    inv = f32(1.0 / f32(__import__("math").sqrt(mag2)))
    return [f32(v[j] * inv) for j in range(3)]


def matvec_f32(m, v):
    return [f32(f32(f32(m[r][0] * v[0]) + f32(m[r][1] * v[1])) + f32(m[r][2] * v[2]))
            for r in range(3)]


def key(n):
    return tuple(bits(c) for c in n)


def main() -> int:
    level, names = V.world_csg_names()
    ed = read_bin(Path(sys.argv[1]))          # editor nfinal.bin
    _, na_nodes = parse_native(Path(sys.argv[2]))  # native FULL:727-727 log
    na = na_nodes[727]
    states, _ = parse_native(Path(sys.argv[3]))    # native COUNTS log
    ranges = []
    prev = 0
    for s in states:
        ranges.append((s["bi"], prev, s["nodes"]))
        prev = s["nodes"]

    # Predicted editor-normal set (bits), global across brushes, with provenance class.
    predicted: dict[tuple, str] = {}
    for nm in names:
        a = level.actors[nm]
        ms, ps = ROT.actor_main_scale(a), ROT.actor_post_scale(a)
        scaled = not (ms.is_identity() and ps.is_identity())
        Rm = ROT.actor_matrix(a)
        if scaled:
            X = ROT.editor_vector_xform(a)
            from uedcli.transform import flip_winding
            cls = "mirror" if flip_winding(ROT.actor_linear(a)) else "scaled"
        elif Rm is not None:
            # Rotated-unscaled: the editor's VectorXform is the f32 FCoords chain here too.
            X = ROT.editor_vector_xform(a)
            cls = "rotated"
        else:
            X = None
            cls = "unscaled"
        for poly in a.brush.polys:
            cn = calc_normal([tuple(float(c) for c in v) for v in poly.vertices])
            if cn is None:
                continue
            xn = cn if X is None else matvec_f32([[float(c) for c in row] for row in X], cn)
            n = sns(xn)
            if n is None:
                continue
            for cand in (n, [-c for c in n]):
                predicted.setdefault(key(cand), cls)

    explained = {}
    unexplained = {}
    samples = []
    for i, (e, nnode) in enumerate(zip(ed, na)):
        if e == nnode:
            continue
        ekey = (e[0], e[1], e[2])
        bi = next(bi for bi, lo, hi in ranges if lo <= i < hi)
        if ekey in predicted:
            explained[predicted[ekey]] = explained.get(predicted[ekey], 0) + 1
        else:
            # w-only diffs: normal bits equal on both sides
            if ekey == (nnode[0], nnode[1], nnode[2]):
                explained["w-only"] = explained.get("w-only", 0) + 1
            else:
                unexplained[bi] = unexplained.get(bi, 0) + 1
                if len(samples) < 10:
                    samples.append((i, bi, ekey, (nnode[0], nnode[1], nnode[2])))
    print("explained by class:", explained)
    print(f"unexplained nodes: {sum(unexplained.values())} across {len(unexplained)} brushes")
    for bi, c in sorted(unexplained.items(), key=lambda kv: -kv[1])[:10]:
        print(f"  bi={bi} {names[bi]} unexplained={c}")
    for s in samples:
        print("  sample:", s[0], f"bi={s[1]}", "editor=" + ",".join(f"{b:08x}" for b in s[2]),
              "native=" + ",".join(f"{b:08x}" for b in s[3]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
