#!/usr/bin/env python3
r"""Evidence harness for decode §6a/§6b: the `bspOptGeom` T-junction detector fix.

Cross-checks a native build's welds + point pool against the editor golden, three ways:

  1. WELDS — match native's inserter log (NINS lines, emitted by `bspoptgeom.rs` under
     `UEDCLI_OPTGEOM_DEBUG=1`) against the editor inserter oracle (`logs/bspopt-insert.log`,
     produced by `bspopt_insert_oracle.py`).  Keyed permutation-invariantly on (node-plane, welded-P)
     because the two trees are isomorphic under a node RELABELING, so raw node indices do not align.
     Expected after the perpendicular (E×N) detector fix: 959/975 editor welds reproduced.

  2. LIVE RING COORDS — the multiset of live ring-vertex COORDINATES (node.iVertPool..+NumVertices),
     native vs editor.  This is the load-bearing check that `SplitPolyList` places the editor's split
     vertices: expected 1549/1555 distinct coords identical, the rest sub-0.05uu FP aliases.

  3. POINT POOL — final Points array by coordinate, native vs editor.  Shows the residual is
     orphan-point bookkeeping (native clears+rebuilds → 1797; editor keeps CSG-transients → 2035).

Usage:
  UEDCLI_OPTGEOM_DEBUG=1 python ../build_native_castle.py /tmp/NativeCastle.dx 2>/tmp/nins.log
  python weld_pool_diff.py /tmp/nins.log /tmp/NativeCastle.dx [Test_Castle.dx]
"""
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from uedcli.native import umodel as UM  # noqa: E402
from uedcli.native.pkg_write import parse_package  # noqa: E402

NINS_LOG = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/nins.log")
NATIVE = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/NativeCastle.dx")
EDITOR = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx")
EDITOR_INS = HERE / "logs" / "bspopt-insert.log"


def load_model(p):
    pkg = parse_package(Path(p).read_bytes())
    mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
             key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    return UM.parse_model_body(pkg.buf, e["soff"], e["ssize"])


def parse_ins(path, tag):
    out = []
    for line in open(path):
        if not line.startswith(tag + " "):
            continue
        m = re.search(r'node=(\d+) edge=(\d+) point=(-?\d+) plane=(\S+) P=(\S+?)(?: nv=\d+)?\s*$', line.strip())
        plane = tuple(round(float(x), 3) for x in m.group(4).split(','))
        P = tuple(round(float(x), 2) for x in m.group(5).split(','))
        out.append((plane, P))
    return out


def live_coords(m):
    c = Counter()
    for n in m.nodes:
        for j in range(n.num_vertices):
            p = m.points[m.verts[n.i_vert_pool + j].i_vertex]
            c[(round(p[0], 2), round(p[1], 2), round(p[2], 2))] += 1
    return c


def main():
    nm = load_model(NATIVE)
    em = load_model(EDITOR)
    print(f"native: nodes={len(nm.nodes)} verts={len(nm.verts)} live={sum(n.num_vertices for n in nm.nodes)} "
          f"points={len(nm.points)} nss={nm.num_shared_sides}")
    print(f"editor: nodes={len(em.nodes)} verts={len(em.verts)} live={sum(n.num_vertices for n in em.nodes)} "
          f"points={len(em.points)} nss={em.num_shared_sides}")

    print("\n[1] WELDS (permutation-invariant on plane+P)")
    nk = Counter(parse_ins(NINS_LOG, "NINS"))
    ek = Counter(parse_ins(EDITOR_INS, "INS"))
    print(f"  native welds={sum(nk.values())} editor welds={sum(ek.values())} "
          f"matched={sum((nk & ek).values())} only-native={sum((nk - ek).values())} only-editor={sum((ek - nk).values())}")

    print("\n[2] LIVE RING COORDS")
    nl, el = live_coords(nm), live_coords(em)
    ns, es = set(nl), set(el)
    print(f"  distinct: native={len(ns)} editor={len(es)} common={len(ns & es)} "
          f"only-editor={len(es - ns)} only-native={len(ns - es)} (differences are FP aliases)")

    print("\n[3] POINT POOL")
    def pk(m):
        return Counter((round(p[0], 2), round(p[1], 2), round(p[2], 2)) for p in m.points)
    np_, ep_ = pk(nm), pk(em)
    print(f"  coords native-missing={sum((ep_ - np_).values())} spurious={sum((np_ - ep_).values())} "
          f"shared={sum((np_ & ep_).values())}")


if __name__ == "__main__":
    main()
