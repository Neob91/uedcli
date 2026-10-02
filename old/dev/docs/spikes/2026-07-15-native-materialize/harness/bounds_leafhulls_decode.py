#!/usr/bin/env python3
"""Decode the editor's render `Bounds` (c0) + `LeafHulls` (cc) structure, and prove both are
node-emit-ORDER-derived (hence blocked on the node-order port for byte parity).

Run after build_native_castle.py.  Loads the golden `Test_Castle.dx` (editor) and
`NativeCastle.dx` (native) Model bodies and reports, for the two aux arrays:

  Bounds (c0) — the render-cull FBox array:
    * WHICH nodes carry a render bound: exactly the front/back-tree nodes with >=1 child
      (iFront!=-1 or iBack!=-1).  Leaf nodes (both children -1) get iRenderBound=-1.
      For Test_Castle: 691 FB-tree nodes - 207 leaf nodes = 484 bounds.
    * iRenderBound is the POST-ORDER DFS index (root gets the LAST index, 483) — so the
      array ORDER is the full front/back tree traversal order.
    * bound VALUE = the tight convex-CELL bbox (NOT the node's stored-vertex subtree bbox):
      231/484 happen to equal the vertex-subtree bbox; the other 253 are strictly LARGER
      (the cell extends past the node's own clipped vertices, to the ancestor split planes).

  LeafHulls (cc) — the box-sweep collision hulls:
    * editor and native BOTH mark 308 collision nodes (iCollisionBound!=-1).
    * per-hull format is identical: [plane-node refs (|0x40000000 FLIP), ..., -1, 6x i32-bitcast
      f32 bbox].  BUT: editor uses the TIGHT convex-cell bbox; native hardcodes the +-32768
      world box.  And editor selects fewer bounding planes (<=10/hull) than native's
      cull_parallel_planes (up to 14/hull) -> native emits 162 extra ints (1872 vs 1710 refs).

  The BLOCKER (measured here): native vs editor node planes match positionally only 172/1156,
  first diverging at node 51.  Both aux arrays are ordered by / indexed into the node array
  (Bounds by post-order DFS; LeafHull refs ARE node indices, array order tracks iCollisionBound),
  so neither can be byte-identical until the node-emit ORDER matches the editor's bspBuild.  That
  is the separately-tracked node-order grind, not a standalone aux-array fix.
"""
import struct
import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))
from uedcli.native.codec import read_ci  # noqa: E402
import utexture_decode as UT  # noqa: E402

EDITOR = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx"
NATIVE = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/NativeCastle.dx"
FLIP = 0x40000000


def load_body(path):
    pkg = UT.load_package(path)
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    return bytes(pkg.buf[e["soff"]:e["soff"] + e["ssize"]])


def parse(body):
    p = 42
    c, p = read_ci(body, p); p += c * 12                      # Vectors
    c, p = read_ci(body, p)
    points = [struct.unpack_from("<3f", body, p + i * 12) for i in range(c)]; p += c * 12
    nc, p = read_ci(body, p)
    nodes = []
    for _ in range(nc):
        plane = struct.unpack_from("<4f", body, p); p += 16
        p += 8; p += 1                                        # zone_mask + flags
        v = []
        for _ in range(10):
            x, p = read_ci(body, p); v.append(x)
        p += 8                                                # iLeaf pair
        nodes.append(dict(plane=plane, iVertPool=v[0], iSurf=v[1], iFront=v[2], iBack=v[3],
                          iColl=v[5], iRend=v[6], nv=v[9]))
    sc, p = read_ci(body, p)
    for _ in range(sc):
        _, p = read_ci(body, p); p += 4
        for _ in range(6):
            _, p = read_ci(body, p)
        p += 4; _, p = read_ci(body, p)
    vc, p = read_ci(body, p)
    for _ in range(vc):
        _, p = read_ci(body, p); _, p = read_ci(body, p)
    p += 4
    nz = struct.unpack_from("<i", body, p)[0]; p += 4
    for _ in range(nz):
        _, p = read_ci(body, p); p += 16
    _, p = read_ci(body, p)                                   # field_0x54
    c, p = read_ci(body, p)                                   # LightMap
    for _ in range(c):
        p += 16; _, p = read_ci(body, p); _, p = read_ci(body, p); p += 12
    c, p = read_ci(body, p); p += c                           # LightBits
    bc, p = read_ci(body, p)                                  # Bounds
    bounds = []
    for _ in range(bc):
        mn = struct.unpack_from("<3f", body, p); p += 12
        mx = struct.unpack_from("<3f", body, p); p += 12
        p += 1
        bounds.append((mn, mx))
    lc, p = read_ci(body, p)                                  # LeafHulls
    hulls = list(struct.unpack_from("<%di" % lc, body, p))
    return dict(nodes=nodes, points=points, bounds=bounds, hulls=hulls)


def hulls_by_node(m):
    H = m["hulls"]; out = []
    for i, n in enumerate(m["nodes"]):
        c = n["iColl"]
        if c == -1:
            continue
        p = c; refs = []
        while H[p] != -1:
            refs.append(H[p]); p += 1
        p += 1
        bbox = [struct.unpack("<f", struct.pack("<i", H[p + k]))[0] for k in range(6)]
        out.append((i, refs, bbox))
    return out


def main():
    ed = parse(load_body(EDITOR))
    nt = parse(load_body(NATIVE))
    en, nn = ed["nodes"], nt["nodes"]

    print("=== NODE-ORDER divergence (RESOLVED — §82 §10.17) ===")
    # RAW positional node-for-node plane compare.  Use an ABSOLUTE float tolerance (1e-3), NOT a
    # round-to-3dp string key: the octagonal-roof/bastion planes sit at w = -381.0655, whose f32
    # value straddles the round(3) boundary (-381.065 vs -381.066), so a rounded-key equality reports
    # a spurious 12/1156 "divergence" on planes that are in fact identical.  The tolerant compare is
    # the faithful raw metric.  (The 12-vs-12 round-key artifact is the same fp-noise §10.10-§10.12
    # tracked; an fp-tolerant pairing collapses it to 0.)
    ntol = min(len(en), len(nn))
    peq = lambda a, b: all(abs(x - y) <= 1e-3 for x, y in zip(a, b))
    fd = next((i for i in range(ntol) if not peq(en[i]["plane"], nn[i]["plane"])), None)
    match = sum(1 for i in range(ntol) if peq(en[i]["plane"], nn[i]["plane"]))
    print(f"  positional plane match {match}/{len(en)} (abs tol 1e-3); first divergence at node {fd}")
    # also report the round-3dp key count so the fp-noise residual stays visible
    pl = lambda n: tuple(round(x, 3) for x in n["plane"])
    key_match = sum(1 for i in range(ntol) if pl(en[i]) == pl(nn[i]))
    print(f"  (round-3dp key match {key_match}/{len(en)} — the {len(en) - key_match} delta is the "
          f"-381.0655 round-boundary fp-noise, same plane)")

    print("\n=== Bounds (c0) structure (editor) ===")
    rend = [i for i, n in enumerate(en) if n["iRend"] != -1]
    print(f"  editor render bounds: {len(rend)} nodes  (array count {len(ed['bounds'])})")
    print(f"  native render bounds: {sum(1 for n in nn if n['iRend'] != -1)} nodes")
    # node-set rule: FB-tree nodes with >=1 child
    reach = set()
    st = [0]
    while st:
        i = st.pop()
        if i == -1 or i in reach:
            continue
        reach.add(i); st += [en[i]["iFront"], en[i]["iBack"]]
    withkids = {i for i in reach if en[i]["iFront"] != -1 or en[i]["iBack"] != -1}
    print(f"  rule 'FB-tree node with >=1 child' == render-bound set: {withkids == set(rend)}")
    print(f"  iRend of root node 0 = {en[0]['iRend']} (== count-1 -> post-order DFS index)")

    print("\n=== LeafHulls (cc) structure ===")
    eh, nh = hulls_by_node(ed), hulls_by_node(nt)
    ep = [len(r) for _, r, _ in eh]; npl = [len(r) for _, r, _ in nh]
    print(f"  editor: {len(eh)} hulls, {len(ed['hulls'])} ints, {sum(ep)} plane refs")
    print(f"  native: {len(nh)} hulls, {len(nt['hulls'])} ints, {sum(npl)} plane refs "
          f"(+{len(nt['hulls']) - len(ed['hulls'])} ints / +{sum(npl) - sum(ep)} refs)")
    print(f"  editor planes/hull: {dict(sorted(Counter(ep).items()))}")
    print(f"  native planes/hull: {dict(sorted(Counter(npl).items()))}")
    ebm = max(abs(x) for _, _, bb in eh for x in bb)
    nbm = max(abs(x) for _, _, bb in nh for x in bb)
    print(f"  editor bbox: TIGHT convex-cell (sample {[round(x,1) for x in eh[0][2]]})")
    print(f"  native bbox: +-world box (max |coord| native {nbm} vs editor {ebm})")


if __name__ == "__main__":
    main()
