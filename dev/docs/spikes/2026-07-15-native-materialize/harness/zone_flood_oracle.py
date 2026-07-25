#!/usr/bin/env python3
"""Zone-flood root-cause oracle: run native's Pass B (portal graph) + Pass C (union-find) flood
DIRECTLY on a shipped editor map's OWN finalized BSP tree + leaves, and compare the zone COUNT it
produces against the editor's shipped zone count.

Why this isolates the bug: native's over-fragmentation ("far MORE zones than UnrealEd, dozens of
tiny singleton zones") could originate either (1) in the CSG tree native builds (dropped portal
sheets, different leaf structure) or (2) in the zone-flood algorithm itself (`zones.rs` Pass B/C).
This harness feeds the EDITOR's tree + EDITOR's leaves (read straight off the shipped `.dx`) into a
faithful Python port of native's Pass B/C.  If it over-fragments the editor's own 2266 leaves into
45 zones, the bug is entirely in Pass B/C (portal detection / union-find) — independent of CSG.  If
it reproduces ~7 zones, the flood is fine and the bug is upstream in the CSG tree.

Port fidelity: clip_poly / plane_axes / poly_area / filter_subtree / collect_portals / union-find
are line-for-line the `uedctl-native/src/zones.rs` logic (WORLD=32768, MIN_AREA=1.0, 1e-4 clip
band, PF_PORTAL=0x04000000).  Pass A is SKIPPED — we reuse the editor's node.iLeaf + Leaves array.

Usage: python zone_flood_oracle.py /path/to/Map.dx
"""
import sys
from collections import Counter
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
ROOT = HARNESS.parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedctl/harness"))

import utexture_decode as UT  # noqa: E402
from uedctl.native import umodel as UM  # noqa: E402

import os
WORLD = 32768.0
MIN_AREA = float(os.environ.get("MINAREA", "1.0"))
PF_PORTAL = 0x04000000


def clip_poly(verts, n, w):
    out = []
    def d(v):
        return n[0] * v[0] + n[1] * v[1] + n[2] * v[2] - w
    m = len(verts)
    for i in range(m):
        a = verts[i]
        b = verts[(i + 1) % m]
        da, db = d(a), d(b)
        if da <= 1e-4:
            out.append(a)
        if (da < -1e-4 and db > 1e-4) or (da > 1e-4 and db < -1e-4):
            t = da / (da - db)
            out.append((a[0] + (b[0] - a[0]) * t,
                        a[1] + (b[1] - a[1]) * t,
                        a[2] + (b[2] - a[2]) * t))
    return out


def plane_axes(n):
    ax, ay, az = abs(n[0]), abs(n[1]), abs(n[2])
    if ax <= ay and ax <= az:
        helper = (1.0, 0.0, 0.0)
    elif ay <= az:
        helper = (0.0, 1.0, 0.0)
    else:
        helper = (0.0, 0.0, 1.0)
    def cross(a, b):
        return (a[1] * b[2] - a[2] * b[1],
                a[2] * b[0] - a[0] * b[2],
                a[0] * b[1] - a[1] * b[0])
    def norm(v):
        l = (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) ** 0.5
        if l < 1e-8:
            return (1.0, 0.0, 0.0)
        return (v[0] / l, v[1] / l, v[2] / l)
    u = norm(cross(helper, n))
    v = norm(cross(n, u))
    return u, v


def poly_area(verts):
    if len(verts) < 3:
        return 0.0
    nx = ny = nz = 0.0
    for i in range(1, len(verts) - 1):
        a = (verts[i][0] - verts[0][0], verts[i][1] - verts[0][1], verts[i][2] - verts[0][2])
        b = (verts[i + 1][0] - verts[0][0], verts[i + 1][1] - verts[0][1], verts[i + 1][2] - verts[0][2])
        nx += a[1] * b[2] - a[2] * b[1]
        ny += a[2] * b[0] - a[0] * b[2]
        nz += a[0] * b[1] - a[1] * b[0]
    return 0.5 * (nx * nx + ny * ny + nz * nz) ** 0.5


def filter_child(model, child, leaf, poly, out):
    if len(poly) < 3:
        return
    if child == -1:
        out.append((leaf, poly))
    else:
        filter_subtree(model, child, poly, out)


def filter_subtree(model, ni, poly, out):
    n = model.nodes[ni]
    pl = (n.plane[0], n.plane[1], n.plane[2])
    w = n.plane[3]
    front = clip_poly(poly, (-pl[0], -pl[1], -pl[2]), -w)
    filter_child(model, n.i_back, n.i_leaf[1], front, out)
    back = clip_poly(poly, pl, w)
    filter_child(model, n.i_front, n.i_leaf[0], back, out)


def collect_portals(model, portals, stats):
    # iterative DFS with an ancestor-plane stack, mirroring collect_portals recursion
    def rec(ni, planes):
        if ni < 0:
            return
        n = model.nodes[ni]
        i_front, i_back = n.i_front, n.i_back
        pl = (n.plane[0], n.plane[1], n.plane[2])
        u, v = plane_axes(pl)
        base = (n.plane[0] * n.plane[3], n.plane[1] * n.plane[3], n.plane[2] * n.plane[3])
        face = [
            (base[0] - (u[0] + v[0]) * WORLD, base[1] - (u[1] + v[1]) * WORLD, base[2] - (u[2] + v[2]) * WORLD),
            (base[0] + (u[0] - v[0]) * WORLD, base[1] + (u[1] - v[1]) * WORLD, base[2] + (u[2] - v[2]) * WORLD),
            (base[0] + (u[0] + v[0]) * WORLD, base[1] + (u[1] + v[1]) * WORLD, base[2] + (u[2] + v[2]) * WORLD),
            (base[0] - (u[0] - v[0]) * WORLD, base[1] - (u[1] - v[1]) * WORLD, base[2] - (u[2] - v[2]) * WORLD),
        ]
        for (cn, cw) in planes:
            if len(face) < 3:
                break
            face = clip_poly(face, cn, cw)
        if len(face) >= 3 and poly_area(face) >= MIN_AREA:
            zone_portal = (n.i_surf >= 0 and n.i_surf < len(model.surfs)
                           and (model.surfs[n.i_surf].poly_flags & PF_PORTAL) != 0)
            back_frags = []
            filter_child(model, i_front, n.i_leaf[0], list(face), back_frags)
            for (back_leaf, frag) in back_frags:
                if back_leaf < 0:
                    continue
                front_frags = []
                filter_child(model, i_back, n.i_leaf[1], frag, front_frags)
                for (front_leaf, sub) in front_frags:
                    if front_leaf >= 0 and front_leaf != back_leaf and poly_area(sub) >= MIN_AREA:
                        portals.append((front_leaf, back_leaf, zone_portal))
        else:
            stats['node_face_rejected'] += 1
        if i_back != -1:
            planes.append(((-pl[0], -pl[1], -pl[2]), -n.plane[3]))
            rec(i_back, planes)
            planes.pop()
        if i_front != -1:
            planes.append((pl, n.plane[3]))
            rec(i_front, planes)
            planes.pop()

    sys.setrecursionlimit(1 << 20)
    rec(0, [])


class UF:
    def __init__(self, n):
        self.p = list(range(n))
    def find(self, x):
        r = x
        while self.p[r] != r:
            r = self.p[r]
        while self.p[x] != r:
            self.p[x], x = r, self.p[x]
        return r
    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def blockportal_interior_zones(model):
    """The faithful native zone flood (Pass B portals + BlockPortal barriers + Pass C union-find),
    reimplementing `uedctl-native/src/zones.rs` on a parsed Model.  Returns the number of INTERIOR
    zones (== NumZones - 1 == the union-find component count).  A zone BARRIER is a leaf-pair a
    PF_Portal node's REAL polygon separates (re-filtered through its coplanar-chain HEAD's subtrees);
    every non-barrier portal merges.  This is the committed reference the pytest golden-checks the
    Rust flood against.  Matches editor NumZones-1 leaf-pair-exact on Castle/UNATCO/HKMarket/
    Catacombs editor trees (3/6/4/16)."""
    n_leaves = len(model.leaves)
    portals = []
    collect_portals(model, portals, Counter())

    # chain-head map (tree nodes + i_plane predecessors)
    is_tree = [False] * len(model.nodes)
    if model.nodes:
        is_tree[0] = True
    for n in model.nodes:
        for c in (n.i_front, n.i_back):
            if c >= 0:
                is_tree[c] = True
    iplane_pred = {}
    for i, n in enumerate(model.nodes):
        if n.i_plane >= 0:
            iplane_pred[n.i_plane] = i

    def head_of(ni):
        seen = 0
        while not is_tree[ni] and ni in iplane_pred and seen < len(model.nodes):
            ni = iplane_pred[ni]
            seen += 1
        return ni

    def node_landings(head, poly):
        hn = model.nodes[head]
        back = []
        filter_child(model, hn.i_front, hn.i_leaf[0], poly, back)
        outp = []
        for (bl, frag) in back:
            front = []
            filter_child(model, hn.i_back, hn.i_leaf[1], frag, front)
            for (fl, sub) in front:
                outp.append((bl, fl))
        return outp

    barriers = set()
    for ni, n in enumerate(model.nodes):
        if not (0 <= n.i_surf < len(model.surfs)
                and (model.surfs[n.i_surf].poly_flags & PF_PORTAL)):
            continue
        if n.num_vertices < 3 or n.i_vert_pool < 0:
            continue
        poly = []
        for k in range(n.num_vertices):
            vi = model.verts[n.i_vert_pool + k].i_vertex
            p = model.points[vi]
            poly.append((p[0], p[1], p[2]))
        for (bl, fl) in node_landings(head_of(ni), poly):
            if bl >= 0 and fl >= 0 and bl != fl:
                barriers.add((min(bl, fl), max(bl, fl)))

    uf = UF(n_leaves)
    for (a, b, zp) in portals:
        if (min(a, b), max(a, b)) not in barriers:
            uf.union(a, b)
    return len(set(uf.find(i) for i in range(n_leaves)))


def main(path):
    pkg = UT.load_package(path)
    mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
             key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    model = UM.parse_model_body(pkg.buf, e["soff"], e["ssize"])
    n_leaves = len(model.leaves)
    print(f"== {Path(path).name}: editor nodes={len(model.nodes)} leaves={n_leaves} "
          f"zones={len(model.zones)}")
    # how many nodes reference each leaf (sanity)
    referenced = set()
    for n in model.nodes:
        for s in (0, 1):
            if n.i_leaf[s] >= 0:
                referenced.add(n.i_leaf[s])
    print(f"   leaves referenced by some node.iLeaf: {len(referenced)} / {n_leaves}")

    stats = Counter()
    portals = []
    collect_portals(model, portals, stats)
    zone_portals = sum(1 for p in portals if p[2])
    print(f"   Pass B portals found: {len(portals)}  (zone-portals={zone_portals})  "
          f"node_face_rejected={stats['node_face_rejected']}")

    # leaves touched by at least one portal
    touched = set()
    for (a, b, zp) in portals:
        touched.add(a)
        touched.add(b)
    print(f"   leaves touched by >=1 portal: {len(touched)} / {n_leaves}  "
          f"(untouched => forced singleton zone: {n_leaves - len(touched)})")

    # Pass C union-find over NON-zone portals
    uf = UF(n_leaves)
    for (a, b, zp) in portals:
        if not zp:
            uf.union(a, b)
    roots = Counter(uf.find(i) for i in range(n_leaves))
    n_zones_found = len(roots)
    print(f"   Pass C zones (native flood on EDITOR tree): {n_zones_found}  "
          f"(+zone0 => NumZones={min(n_zones_found + 1, 64)})")
    print(f"   editor shipped NumZones: {len(model.zones)}")
    comp_sizes = Counter(roots.values())
    print(f"   component-size histogram (size:count): {dict(sorted(comp_sizes.items())[:15])}")
    singletons = sum(1 for r, c in roots.items() if c == 1)
    print(f"   singleton zones (1 leaf): {singletons}")

    # DIAGNOSTIC 1: pure geometric adjacency (union ALL portals, ignoring zone flag).
    # If this ~= editor zones, the excess comes from OVER-marking zone-portals; if it is still
    # far above editor, the excess is MISSING geometric portals.
    uf_all = UF(n_leaves)
    for (a, b, zp) in portals:
        uf_all.union(a, b)
    n_adj = len(set(uf_all.find(i) for i in range(n_leaves)))
    print(f"   [D1] pure-adjacency components (union ALL portals): {n_adj}")

    # DIAGNOSTIC 2: cross-check native's zone-portal marking against editor's TRUE leaf.iZone.
    ez = [lf.i_zone for lf in model.leaves]
    false_zp = same = diff = 0
    for (a, b, zp) in portals:
        if ez[a] == ez[b]:
            same += 1
            if zp:
                false_zp += 1  # native marks a WITHIN-editor-zone face as a zone boundary
        else:
            diff += 1
    print(f"   [D2] portals within same editor-zone: {same} (of which native falsely zone-marked: "
          f"{false_zp});  cross editor-zone: {diff}")

    # DIAGNOSTIC 3: flood treating native zone-portals correctly BUT re-run ignoring native's
    # zone flag and instead using editor ground truth (portal is a barrier iff ez[a]!=ez[b]).
    uf_gt = UF(n_leaves)
    for (a, b, zp) in portals:
        if ez[a] == ez[b]:
            uf_gt.union(a, b)
    n_gt = len(set(uf_gt.find(i) for i in range(n_leaves)))
    print(f"   [D3] components if barriers were editor-true (ez[a]!=ez[b]): {n_gt} "
          f"(vs editor {len(model.zones) - 1} interior)")

    # DIAGNOSTIC 5: the FAITHFUL BlockPortal — stamp zone barriers by the PF_Portal node's REAL
    # polygon (node_poly re-filtered), not by the infinite-quad-generating node's surf flag.  A
    # leaf-pair is a zone barrier iff a PF_Portal node's real polygon lands between them.  Then flood
    # skipping only those leaf-pairs.  This is what zones.rs SHOULD do (editor §3 BlockPortal).
    import os
    barrier_pairs = set()
    for ni, n in enumerate(model.nodes):
        if not (n.i_surf >= 0 and n.i_surf < len(model.surfs)
                and (model.surfs[n.i_surf].poly_flags & PF_PORTAL)):
            continue
        if n.num_vertices < 3 or n.i_vert_pool < 0:
            continue
        poly = []
        for k in range(n.num_vertices):
            vi = model.verts[n.i_vert_pool + k].i_vertex
            p = model.points[vi]
            poly.append((p[0], p[1], p[2]))
        # re-filter this real polygon through the whole tree (from root) to find leaf pairs
        lands = []
        filter_subtree(model, 0, poly, lands)
        # each landing is (leaf, frag); we need pairs across the node -> use node_landings-style:
        # filter down back subtree then front. Simpler: this poly is coplanar with node ni; use its
        # own front/back children like collect_portals does for a single node.
        back_frags = []
        filter_child(model, n.i_front, n.i_leaf[0], list(poly), back_frags)
        for (bl, frag) in back_frags:
            if bl < 0:
                continue
            ff = []
            filter_child(model, n.i_back, n.i_leaf[1], frag, ff)
            for (fl, sub) in ff:
                if fl >= 0 and fl != bl and poly_area(sub) >= MIN_AREA:
                    barrier_pairs.add((min(fl, bl), max(fl, bl)))
    uf_bp = UF(n_leaves)
    for (a, b, zp) in portals:
        if (min(a, b), max(a, b)) not in barrier_pairs:
            uf_bp.union(a, b)
    n_bp = len(set(uf_bp.find(i) for i in range(n_leaves)))
    print(f"   [D5] FAITHFUL BlockPortal flood: {n_bp} components (barrier leaf-pairs="
          f"{len(barrier_pairs)})  vs editor interior {len(model.zones) - 1}")

    # DIAGNOSTIC 6: centroid PointRegion barrier detection.  For each PF_Portal node, descend from
    # root with its real-poly centroid nudged +-eps along the plane normal -> (frontLeaf, backLeaf);
    # that unordered pair is a zone barrier.  Robust to coplanar-chain membership.
    def point_region_leaf(pt):
        ni = 0
        while ni >= 0:
            n = model.nodes[ni]
            side = n.plane[0]*pt[0] + n.plane[1]*pt[1] + n.plane[2]*pt[2] - n.plane[3]
            if side >= 0:  # FRONT
                nxt = n.i_back
                if nxt < 0:
                    return n.i_leaf[1]
                ni = nxt
            else:          # BACK
                nxt = n.i_front
                if nxt < 0:
                    return n.i_leaf[0]
                ni = nxt
        return -1
    barrier6 = set()
    EPS = 0.5
    for ni, n in enumerate(model.nodes):
        if not (n.i_surf >= 0 and n.i_surf < len(model.surfs)
                and (model.surfs[n.i_surf].poly_flags & PF_PORTAL)):
            continue
        if n.num_vertices < 3 or n.i_vert_pool < 0:
            continue
        cx = cy = cz = 0.0
        for k in range(n.num_vertices):
            vi = model.verts[n.i_vert_pool + k].i_vertex
            p = model.points[vi]
            cx += p[0]; cy += p[1]; cz += p[2]
        cx /= n.num_vertices; cy /= n.num_vertices; cz /= n.num_vertices
        nl = (n.plane[0]**2 + n.plane[1]**2 + n.plane[2]**2) ** 0.5
        nx, ny, nz = n.plane[0]/nl, n.plane[1]/nl, n.plane[2]/nl
        front_leaf = point_region_leaf((cx + nx*EPS, cy + ny*EPS, cz + nz*EPS))
        back_leaf = point_region_leaf((cx - nx*EPS, cy - ny*EPS, cz - nz*EPS))
        if front_leaf >= 0 and back_leaf >= 0 and front_leaf != back_leaf:
            barrier6.add((min(front_leaf, back_leaf), max(front_leaf, back_leaf)))
    uf6 = UF(n_leaves)
    for (a, b, zp) in portals:
        if (min(a, b), max(a, b)) not in barrier6:
            uf6.union(a, b)
    n6 = len(set(uf6.find(i) for i in range(n_leaves)))
    print(f"   [D6] centroid-PointRegion BlockPortal flood: {n6} components (barrier pairs="
          f"{len(barrier6)})  vs editor interior {len(model.zones) - 1}")

    # DIAGNOSTIC 7: BlockPortal via chain-HEAD subtrees (the faithful Pass-D machinery).  A
    # PF_Portal node on a coplanar i_plane chain has i_front/i_back = -1; its real poly must be
    # re-filtered through the chain HEAD's subtrees, not its own.  node_landings(head, poly).
    # Build head map: tree nodes = root + every i_front/i_back target; a chain member's head is
    # found by walking i_plane predecessors up to a tree node.
    is_tree = [False] * len(model.nodes)
    is_tree[0] = True
    for n in model.nodes:
        for c in (n.i_front, n.i_back):
            if c >= 0:
                is_tree[c] = True
    iplane_pred = {}
    for i, n in enumerate(model.nodes):
        if n.i_plane >= 0:
            iplane_pred[n.i_plane] = i
    def head_of(ni):
        seen = 0
        while not is_tree[ni] and ni in iplane_pred and seen < len(model.nodes):
            ni = iplane_pred[ni]
            seen += 1
        return ni
    def node_landings(head, poly):
        hn = model.nodes[head]
        back = []
        filter_child(model, hn.i_front, hn.i_leaf[0], poly, back)
        outp = []
        for (bl, frag) in back:
            front = []
            filter_child(model, hn.i_back, hn.i_leaf[1], frag, front)
            for (fl, sub) in front:
                outp.append((bl, fl))
        return outp
    barrier7 = set()
    for ni, n in enumerate(model.nodes):
        if not (n.i_surf >= 0 and n.i_surf < len(model.surfs)
                and (model.surfs[n.i_surf].poly_flags & PF_PORTAL)):
            continue
        if n.num_vertices < 3 or n.i_vert_pool < 0:
            continue
        poly = []
        for k in range(n.num_vertices):
            vi = model.verts[n.i_vert_pool + k].i_vertex
            p = model.points[vi]
            poly.append((p[0], p[1], p[2]))
        h = head_of(ni)
        for (bl, fl) in node_landings(h, poly):
            if bl >= 0 and fl >= 0 and bl != fl:
                barrier7.add((min(bl, fl), max(bl, fl)))
    uf7 = UF(n_leaves)
    for (a, b, zp) in portals:
        if (min(a, b), max(a, b)) not in barrier7:
            uf7.union(a, b)
    n7 = len(set(uf7.find(i) for i in range(n_leaves)))
    print(f"   [D7] chain-HEAD BlockPortal flood: {n7} components (barrier pairs="
          f"{len(barrier7)})  vs editor interior {len(model.zones) - 1}")


if __name__ == "__main__":
    main(sys.argv[1])
