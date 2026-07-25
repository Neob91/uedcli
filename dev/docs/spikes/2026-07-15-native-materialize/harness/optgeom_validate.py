#!/usr/bin/env python3
"""Validate the standalone Rust `bspOptGeom` port (`uedctl-native/src/bspoptgeom.rs`) against the
editor golden `Test_Castle.dx`.

The golden Model is POST-bspOptGeom (T-junctions already eliminated, iSide/NumSharedSides set).
We feed its geometry to the Rust `opt_geom_from_arrays` and assert the pass reproduces the golden:

  * pass 1 (T-junction elimination) inserts ZERO vertices  -> vert count unchanged (16163), and
    every node's iVertPool/NumVertices unchanged  (the golden is a fixpoint of the faithful,
    descent-scoped detector — the retess invariant HOLDS);
  * pass 2 (side linking) reproduces all 16163 FVert.iSide values BYTE-EXACT and NumSharedSides=2739.

Run:  .venv/bin/python docs/.../harness/optgeom_validate.py
"""
import sys
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedctl/harness"))
from uedctl.native import umodel as UM
import utexture_decode as UT
import uedctl_native

EDITOR = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx"


def load_editor():
    pkg = UT.load_package(EDITOR)
    mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
             key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    return UM.parse_model_body(pkg.buf, e["soff"], e["ssize"])


def main():
    m = load_editor()
    nodes, verts, pts = m.nodes, m.verts, m.points

    points = [c for p in pts for c in p]
    node_plane = [c for n in nodes for c in n.plane]
    node_ivertpool = [n.i_vert_pool for n in nodes]
    node_numverts = [n.num_vertices for n in nodes]
    node_ifront = [n.i_front for n in nodes]
    node_iback = [n.i_back for n in nodes]
    node_iplane = [n.i_plane for n in nodes]
    vert_ivertex = [v.i_vertex for v in verts]
    gold_iside = [v.i_side for v in verts]

    (out_iv, out_iside, out_pool, out_nv, nss) = uedctl_native.opt_geom_from_arrays(
        points, node_plane, node_ivertpool, node_numverts,
        node_ifront, node_iback, node_iplane, vert_ivertex,
    )

    ok = True

    # pass 1 idempotency: no vertex inserted, node pools/counts unchanged
    if len(out_iv) != len(vert_ivertex):
        print(f"[FAIL] pass1 inserted {len(out_iv)-len(vert_ivertex)} verts "
              f"({len(vert_ivertex)} -> {len(out_iv)})")
        ok = False
    else:
        print(f"[ok] pass1 idempotent: vert count unchanged ({len(out_iv)})")
    if out_iv != vert_ivertex:
        print("[FAIL] pass1 mutated the vertex iVertex array")
        ok = False
    if out_pool != node_ivertpool or out_nv != node_numverts:
        print("[FAIL] pass1 changed node iVertPool/NumVertices")
        ok = False
    else:
        print("[ok] pass1 idempotent: node iVertPool/NumVertices unchanged")

    # pass 2: byte-exact iSide + NumSharedSides
    if len(out_iside) == len(gold_iside):
        matches = sum(1 for a, b in zip(out_iside, gold_iside) if a == b)
        if matches == len(gold_iside):
            print(f"[ok] pass2 iSide BYTE-EXACT: {matches}/{len(gold_iside)}")
        else:
            print(f"[FAIL] pass2 iSide mismatch: {matches}/{len(gold_iside)}")
            diffs = [(i, out_iside[i], gold_iside[i])
                     for i in range(len(gold_iside)) if out_iside[i] != gold_iside[i]]
            print(f"       first diffs (gv, mine, gold): {diffs[:10]}")
            ok = False
    else:
        print("[FAIL] pass2 iSide length mismatch")
        ok = False

    if nss == m.num_shared_sides:
        print(f"[ok] NumSharedSides EXACT: {nss}")
    else:
        print(f"[FAIL] NumSharedSides {nss} != golden {m.num_shared_sides}")
        ok = False

    print("\nALL CHECKS PASS" if ok else "\nVALIDATION FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
