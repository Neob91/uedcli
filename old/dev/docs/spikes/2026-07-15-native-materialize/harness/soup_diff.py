#!/usr/bin/env python3
"""Reconstruct the FPoly 'soup' from a parsed Model and compare native-vs-editor at the
surface (pre-tree) level, to separate "wrong soup" from "wrong tree order".

A Model's nodes each reconstruct to one FPoly via bspNodeToFPoly:
    base   = points[surf.p_base]
    normal = vectors[surf.v_normal]
    verts  = [ points[verts[iVertPool+k].i_vertex] for k in range(num_vertices) ]

We key each reconstructed face by (rounded plane, rounded sorted vertex-set) so the comparison is
order-independent.  This lets us ask: does the native tree carry the SAME set of face fragments as
the editor (=> tree-ORDER divergence, a FindBestSplit/SplitPolyList issue), or a DIFFERENT set
(=> CSG SOUP divergence, a bspBrushCSG filter/merge issue)?

Usage (full castle):  soup_diff.py            # native bspcsg vs editor golden
       (a subset):     imported by subset analysis.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

import castle_build  # noqa: E402


def node_faces(model, nd_plane=2, nd_vert=1):
    """Reconstruct one face per node -> (plane_key, vertset_key, num_verts)."""
    out = []
    for n in model.nodes:
        base = model.points[model.surfs[n.i_surf].p_base] if model.surfs else None
        verts = []
        for k in range(n.num_vertices):
            fv = model.verts[n.i_vert_pool + k]
            verts.append(model.points[fv.i_vertex])
        pkey = tuple(round(c, nd_plane) for c in n.plane)
        vkey = tuple(sorted(tuple(round(c, nd_vert) for c in v) for v in verts))
        out.append((pkey, vkey, n.num_vertices))
    return out


def plane_multiset(model, nd=2):
    return Counter(tuple(round(c, nd) for c in n.plane) for n in model.nodes)


def face_multiset(model, nd_plane=2, nd_vert=1):
    return Counter((p, v) for (p, v, _) in node_faces(model, nd_plane, nd_vert))


def report(native, editor):
    pn, pe = plane_multiset(native), plane_multiset(editor)
    print("=== PLANE multiset (order-independent) ===")
    print(f"  native nodes={len(native.nodes)}  editor nodes={len(editor.nodes)}")
    print(f"  shared plane-instances : {sum((pn & pe).values())}")
    print(f"  only-native            : {sum((pn - pe).values())}")
    print(f"  only-editor            : {sum((pe - pn).values())}")

    fn, fe = face_multiset(native), face_multiset(editor)
    print("=== FACE multiset (plane + vertex-set) ===")
    print(f"  shared face-instances  : {sum((fn & fe).values())}")
    print(f"  only-native            : {sum((fn - fe).values())}")
    print(f"  only-editor            : {sum((fe - fn).values())}")
    print("  top only-editor planes (plane -> count of faces we lack):")
    onlyE = Counter()
    for (p, v), c in (fe - fn).items():
        onlyE[p] += c
    for p, c in onlyE.most_common(12):
        print(f"    {p}  x{c}")
    print("  top only-native planes:")
    onlyN = Counter()
    for (p, v), c in (fn - fe).items():
        onlyN[p] += c
    for p, c in onlyN.most_common(12):
        print(f"    {p}  x{c}")


def main():
    native, editor, _pkg = castle_build.load_both()
    report(native, editor)


if __name__ == "__main__":
    main()
