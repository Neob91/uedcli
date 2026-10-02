#!/usr/bin/env python3
"""Cause-2 SHATTERED-TREE probe — localize, geometrically and against the golden, WHERE native's
finalized BSP loses empty-space connectivity relative to the editor's own tree.

Method (RAW geometry, nothing normalized):
  * Parse BOTH the native build and the shipped editor golden Model bodies.
  * Sample empty space DENSELY near real faces: for every editor node with a stored polygon, take
    the polygon centroid nudged +-EPS along the plane normal -> two probe points that sit just off a
    real world face, i.e. exactly the open doorway / wall-adjacency regions where connectivity lives.
  * For each probe point, do an FPointRegion descent (iFront/iBack, the engine convention the
    zone_flood_oracle verified) in BOTH trees -> (leaf index | -1 SOLID).
  * GROUND TRUTH connectivity = the editor golden's own shipped leaf.iZone (the editor's finalized
    zones).  NATIVE connectivity = union-find over native's Pass-B portals (union ALL portals ==
    the oracle's [D1] pure-adjacency: the geometric connectivity of native's own leaves).

Then classify every probe point that the EDITOR says is empty (iZone assigned):
  A. SOLIDIFIED  — native descent lands in SOLID (-1): native walled off space the editor keeps open.
  B. connected in editor, but native leaf is in a native component that is DISCONNECTED from the bulk.

and the reverse (native empty where editor solid) for completeness.  Cluster the SOLIDIFIED points
spatially (coarse voxel grid) to show it is whole regions, not scattered noise, and print bounding
boxes so the defect can be located in the map.

Usage:
  shatter_probe.py NATIVE.dx EDITOR.dx [EPS]
"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
ROOT = HARNESS.parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

import utexture_decode as UT  # noqa: E402
from uedcli.native import umodel as UM  # noqa: E402

# reuse the verified portal collector / clip from the zone oracle
sys.path.insert(0, str(HARNESS))
import zone_flood_oracle as ZO  # noqa: E402

PF_PORTAL = 0x04000000


def load_model(path):
    pkg = UT.load_package(path)
    mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
             key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    return UM.parse_model_body(pkg.buf, e["soff"], e["ssize"])


def point_region_leaf(model, pt):
    """FPointRegion descent: return the empty-leaf index the point lands in, or -1 for SOLID.
    Convention matches zone_flood_oracle.filter_subtree / [D6]: side>=0 => FRONT => (i_back, iLeaf[1]);
    side<0 => BACK => (i_front, iLeaf[0])."""
    ni = 0
    if not model.nodes:
        return -1
    guard = 0
    while ni >= 0:
        guard += 1
        if guard > len(model.nodes) + 5:
            return -1
        n = model.nodes[ni]
        side = n.plane[0] * pt[0] + n.plane[1] * pt[1] + n.plane[2] * pt[2] - n.plane[3]
        if side >= 0:
            nxt = n.i_back
            if nxt < 0:
                return n.i_leaf[1]
            ni = nxt
        else:
            nxt = n.i_front
            if nxt < 0:
                return n.i_leaf[0]
            ni = nxt
    return -1


def native_components(model):
    """Union-find over ALL native Pass-B portals (== oracle [D1]); return comp-id per leaf and the
    size of each component."""
    portals = []
    ZO.collect_portals(model, portals, Counter())
    n_leaves = len(model.leaves)
    uf = ZO.UF(n_leaves)
    for (a, b, zp) in portals:
        uf.union(a, b)
    comp = [uf.find(i) for i in range(n_leaves)]
    sizes = Counter(comp)
    return comp, sizes, len(portals)


def node_polys(model):
    """Yield (centroid, unit_normal) for every node that stores a real polygon."""
    for n in model.nodes:
        if n.num_vertices < 3 or n.i_vert_pool < 0:
            continue
        cx = cy = cz = 0.0
        ok = True
        pts = []
        for k in range(n.num_vertices):
            vp = n.i_vert_pool + k
            if vp >= len(model.verts):
                ok = False
                break
            vi = model.verts[vp].i_vertex
            if vi >= len(model.points):
                ok = False
                break
            p = model.points[vi]
            pts.append(p)
            cx += p[0]; cy += p[1]; cz += p[2]
        if not ok or not pts:
            continue
        c = (cx / len(pts), cy / len(pts), cz / len(pts))
        nl = (n.plane[0] ** 2 + n.plane[1] ** 2 + n.plane[2] ** 2) ** 0.5
        if nl < 1e-6:
            continue
        nrm = (n.plane[0] / nl, n.plane[1] / nl, n.plane[2] / nl)
        yield c, nrm


def main(native_path, editor_path, eps):
    nat = load_model(native_path)
    ed = load_model(editor_path)
    print(f"== native {Path(native_path).name}: nodes={len(nat.nodes)} leaves={len(nat.leaves)} "
          f"surfs={len(nat.surfs)} zones={len(nat.zones)}")
    print(f"== editor {Path(editor_path).name}: nodes={len(ed.nodes)} leaves={len(ed.leaves)} "
          f"surfs={len(ed.surfs)} zones={len(ed.zones)}")

    comp, sizes, nat_portals = native_components(nat)
    # the "bulk" native components = the few biggest (cover most leaves)
    ordered = sizes.most_common()
    total_leaves = len(nat.leaves)
    print(f"   native components (leaf-blobs)={len(sizes)}, native portals={nat_portals}")
    print(f"   biggest native comps (size): {[s for _, s in ordered[:8]]}  "
          f"singletons={sum(1 for _, s in ordered if s == 1)}")

    ed_zone = [lf.i_zone for lf in ed.leaves]

    # probe points near every editor face, both sides
    A_solidified = []   # editor-empty, native-SOLID
    B_disc = 0          # editor-empty, native-empty but native-disconnected-singleton/tiny
    R_carved = 0        # editor-SOLID, native-empty (reverse)
    both_empty = 0
    n_probe = 0
    ed_empty = 0
    # "bulk" threshold: a native comp is bulk if it is one of the few big ones
    big_comps = set(r for r, s in ordered if s >= 8)

    for c, nrm in node_polys(ed):
        for sgn in (+1.0, -1.0):
            p = (c[0] + nrm[0] * eps * sgn,
                 c[1] + nrm[1] * eps * sgn,
                 c[2] + nrm[2] * eps * sgn)
            n_probe += 1
            el = point_region_leaf(ed, p)
            nl = point_region_leaf(nat, p)
            ed_is_empty = el >= 0
            nat_is_empty = nl >= 0
            if ed_is_empty:
                ed_empty += 1
                if not nat_is_empty:
                    A_solidified.append(p)
                else:
                    both_empty += 1
                    if comp[nl] not in big_comps:
                        B_disc += 1
            else:
                if nat_is_empty:
                    R_carved += 1

    print(f"\n   probes={n_probe}  (editor-empty={ed_empty})")
    print(f"   [A] editor-EMPTY but native-SOLID (native walled off open space): "
          f"{len(A_solidified)}  ({100.0*len(A_solidified)/max(ed_empty,1):.1f}% of editor-empty)")
    print(f"   [B] editor-EMPTY, native-empty but in a NON-bulk native blob: {B_disc}")
    print(f"   [R] editor-SOLID but native-EMPTY (native over-carved): {R_carved}")
    print(f"   both-empty & native-bulk: {both_empty - B_disc}")

    # cluster [A] solidified points into coarse voxels to show whole regions
    if A_solidified:
        VOX = 256.0
        vox = defaultdict(int)
        for p in A_solidified:
            key = (int(p[0] // VOX), int(p[1] // VOX), int(p[2] // VOX))
            vox[key] += 1
        print(f"\n   [A] solidified points fall in {len(vox)} voxels of {int(VOX)}uu; "
              f"top voxels (count @ center):")
        for key, cnt in Counter(vox).most_common(12):
            cen = ((key[0] + 0.5) * VOX, (key[1] + 0.5) * VOX, (key[2] + 0.5) * VOX)
            print(f"      {cnt:5d}  @ ({cen[0]:.0f},{cen[1]:.0f},{cen[2]:.0f})")
        xs = [p[0] for p in A_solidified]; ys = [p[1] for p in A_solidified]; zs = [p[2] for p in A_solidified]
        print(f"   [A] bbox: x[{min(xs):.0f},{max(xs):.0f}] y[{min(ys):.0f},{max(ys):.0f}] "
              f"z[{min(zs):.0f},{max(zs):.0f}]")


if __name__ == "__main__":
    eps = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
    main(sys.argv[1], sys.argv[2], eps)
