"""Slice 1b/2 — CSG world-surface build + the merge/optimize tail, on top of bsp_port.

Mirrors the editor pipeline decoded in the 2026-06-24 spikes + this session's
exec-parser disassembly:

  csgRebuild (Editor 0x4a650): EmptyModel; for each brush IN ACTOR ORDER apply
    bspBrushCSG (0x355e0); then bspBuild (0x35ef0) -> bspRefresh/MergeCoplanars/OptGeom.

  MAP REBUILD defaults (disassembled this session @Editor 0x65220 exec handler):
    Optimization=2 (OPTIMAL, candidate/classify Inc=1, exact)
    Balance=0x32=50, PortalBias=0x46=70   (packed BalancePortal = 50 | (70<<8))
  -- corrects the slice-1 port which used Balance=15.

bspBrushCSG (0x355e0) per-poly flag: CsgOper==1 (Add) -> 0; else (Subtract) -> 0x28.
The leaf-filter (0x31f50) classifies world polys against the brush half-spaces using
FPlane|·vs 0.0 (the *exact* 0.0 test, not the 0.25 band that only gates bspBuild's
partition splitting), Fixes fragments, and Reverses winding for subtraction.

This module is the CSG soup producer; bsp_port supplies FPoly/classify/split/bspBuild.
"""
from __future__ import annotations

from dataclasses import dataclass

import bsp_port
from bsp_port import FPoly, _sub, _dot, _cross, _norm

PF_SEMISOLID = 0x20
PF_NOTSOLID = 0x08
PF_STRUCTURAL = 0x28


# --- exact-plane clipping (the leaf-filter math: FPlane| vs 0.0) ---------------------------
# bspBrushCSG's leaf-filter uses the EXACT 0.0 dot test (no 0.25 band) to clip world polys
# against a brush's faces. THRESH_POINTS_ARE_SAME (0.002) collapses near-coincident split
# verts; we use a small epsilon for the on-plane class.
_EPS = 1e-4


def _plane_of(face: FPoly):
    return face.plane()


def _clip_exact(poly_verts, plane, keep_front: bool):
    """Sutherland-Hodgman clip of a vertex ring against a plane half-space.
    keep_front=True keeps the d>=0 side, False keeps d<=0. Returns vertex list (maybe < 3)."""
    out = []
    n = len(poly_verts)
    for i in range(n):
        a = poly_verts[i]
        b = poly_verts[(i + 1) % n]
        da = _dot(plane[:3], a) - plane[3]
        db = _dot(plane[:3], b) - plane[3]
        a_in = (da >= -_EPS) if keep_front else (da <= _EPS)
        b_in = (db >= -_EPS) if keep_front else (db <= _EPS)
        if a_in:
            out.append(a)
        if a_in != b_in and abs(da - db) > 1e-12:
            t = da / (da - db)
            out.append(tuple(a[k] + t * (b[k] - a[k]) for k in range(3)))
    return out


def _convex_planes(brush: list[FPoly]):
    """Inward half-space planes of a convex brush: each face's plane with the brush interior
    on the d<=plane.w side. Returns list of (nx,ny,nz,w) where interior satisfies n·v <= w."""
    # centroid as interior witness
    pts = [v for f in brush for v in f.verts]
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    cz = sum(p[2] for p in pts) / len(pts)
    c = (cx, cy, cz)
    planes = []
    for f in brush:
        n = f.normal()
        w = _dot(f.verts[0], n)
        # ensure outward normal: centroid should be behind (n·c - w < 0)
        if _dot(n, c) - w > 0:
            n = (-n[0], -n[1], -n[2]); w = -w
        planes.append((n[0], n[1], n[2], w))
    return planes


def _inside_convex(v, planes, eps=1e-3):
    return all(_dot(p[:3], v) - p[3] <= eps for p in planes)


def _poly_centroid(verts):
    n = len(verts)
    return (sum(v[0] for v in verts) / n, sum(v[1] for v in verts) / n, sum(v[2] for v in verts) / n)


@dataclass
class Brush:
    faces: list           # list[FPoly] in world coords, CCW-from-outside
    csg: str              # "add" | "subtract"
    poly_flags: int = 0   # solidity bits (PF_Semisolid/PF_NotSolid)


def csg_world_surfaces(brushes: list[Brush]) -> list[FPoly]:
    """Reproduce csgRebuild's world poly soup (render/collision surfaces), applying brushes in
    order. A surface bounds SOLID on one side and EMPTY on the other; a face interior to the
    final solid/empty regions (same medium both sides) carries no surface.

    Faithful-to-counts model for convex axis-aligned brushes (the common authoring case):
      - Maintain the EMPTY region as the union of subtract-volume convex cells, and SOLID
        regions as additive cells.
      - A SUBTRACT brush contributes each face (REVERSED, pointing into the room) UNLESS that
        face is interior to the empty union (another subtract already carved the solid behind
        it) — e.g. two abutting subtracts drop their shared wall (10 faces, not 12).
      - An ADD brush contributes each face UNLESS it is interior to solid (covered by another
        additive) OR sits outside any carved empty space (an add in untouched solid shows
        nothing). A pillar inside a room shows all its lateral faces.
    Each face is clipped to the empty region (the part of a subtract face inside *another*
    subtract's empty space is dropped fragment-wise), which is the T-junction mechanism.
    """
    subtract_vols = [(_convex_planes(b.faces), b) for b in brushes if b.csg == "subtract"]
    add_vols = [(_convex_planes(b.faces), b) for b in brushes if b.csg == "add"]
    surfaces: list[FPoly] = []
    for idx, br in enumerate(brushes):
        planes = _convex_planes(br.faces)
        others_sub = [pl for pl, b in subtract_vols if b is not br]
        for f in br.faces:
            verts = list(reversed(f.verts)) if br.csg == "subtract" else list(f.verts)
            centroid = _poly_centroid(verts)
            if br.csg == "subtract":
                # drop the face fragment that lies inside ANOTHER subtract volume (interior wall)
                frags = _clip_out_of_volumes(verts, others_sub)
            else:  # add
                # an additive face shows only where it borders carved-empty space and is not
                # buried inside another additive
                inside_other_add = any(_inside_convex(centroid, pl, eps=-1.0)
                                       for pl, b in add_vols if b is not br)
                if inside_other_add:
                    continue
                # keep fragments that touch some subtracted (empty) region
                frags = [verts] if any(_touches_volume(verts, pl) for pl, _ in subtract_vols) else []
            for fr in frags:
                if len(fr) >= 3:
                    surfaces.append(FPoly(fr, br.poly_flags, f.tag))
    return _cancel_coincident_opposite(surfaces)


def _cancel_coincident_opposite(surfaces: list[FPoly]) -> list[FPoly]:
    """Two coincident, opposite-facing coplanar surfaces bound empty on both sides -> both are
    interior and annihilate (the CSG rule that makes two abutting subtract rooms share no wall).
    Detected by equal plane up to sign with overlapping projected area (centroid coincidence)."""
    drop = set()
    for i in range(len(surfaces)):
        if i in drop:
            continue
        pi = surfaces[i].plane(); ci = _poly_centroid(surfaces[i].verts)
        for j in range(i + 1, len(surfaces)):
            if j in drop:
                continue
            pj = surfaces[j].plane(); cj = _poly_centroid(surfaces[j].verts)
            opposite = (abs(pi[0] + pj[0]) < 1e-3 and abs(pi[1] + pj[1]) < 1e-3 and
                        abs(pi[2] + pj[2]) < 1e-3 and abs(pi[3] + pj[3]) < 1e-2)
            near = all(abs(ci[k] - cj[k]) < 1e-2 for k in range(3))
            if opposite and near:
                drop.add(i); drop.add(j); break
    return [s for k, s in enumerate(surfaces) if k not in drop]


def _touches_volume(verts, planes) -> bool:
    c = _poly_centroid(verts)
    return _inside_convex(c, planes, eps=1.0)


def _clip_out_of_volumes(verts, volumes) -> list[list]:
    """Return fragments of `verts` NOT strictly inside any of the convex `volumes`. For an
    axis-aligned face this is the part not covered by an abutting/overlapping subtract."""
    frags = [verts]
    for planes in volumes:
        nxt = []
        for fr in frags:
            # if wholly inside this volume -> dropped; if wholly outside -> kept; else split off
            if all(_inside_convex(v, planes, eps=-1e-3) for v in fr):
                continue
            if not any(_inside_convex(v, planes, eps=1e-3) for v in fr):
                nxt.append(fr); continue
            # partial: keep the outside-of-each-plane fragments
            remaining = list(fr)
            for pl in planes:
                out = _clip_exact(remaining, pl, keep_front=True)
                if len(out) >= 3:
                    nxt.append(out)
                remaining = _clip_exact(remaining, pl, keep_front=False)
                if len(remaining) < 3:
                    break
        frags = nxt
    return frags


def _subtract_volume_from_poly(poly: FPoly, brush_planes) -> list[FPoly]:
    """Remove the part of `poly` inside the convex volume (all planes' inside side). Returns
    the outside fragments. If the poly is wholly outside, returns [poly]; wholly inside -> []."""
    # Quick check: any vertex strictly outside any plane -> at least partly outside.
    if all(_inside_convex(v, brush_planes, eps=-1e-3) for v in poly.verts):
        return []   # wholly inside the volume -> removed
    if not any(_inside_convex(v, brush_planes, eps=1e-3) for v in poly.verts):
        # no vertex inside; could still clip an edge, but for convex grid brushes treat as outside
        return [poly]
    # Partially inside: subtract = union of (poly clipped to OUTSIDE of each plane).
    frags = []
    remaining = list(poly.verts)
    for pl in brush_planes:
        outside = _clip_exact(remaining, pl, keep_front=True)   # n·v - w >= 0 = outside
        if len(outside) >= 3:
            frags.append(FPoly(outside, poly.flags, poly.tag))
        remaining = _clip_exact(remaining, pl, keep_front=False)
        if len(remaining) < 3:
            break
    return frags


# --- merge/optimize tail -------------------------------------------------------------------

THRESH_NORMALS_ARE_SAME = 2e-5


def _planes_equal(p, q, ntol=THRESH_NORMALS_ARE_SAME, dtol=0.01):
    return (abs(p[0] - q[0]) < ntol and abs(p[1] - q[1]) < ntol and
            abs(p[2] - q[2]) < ntol and abs(p[3] - q[3]) < dtol)


def merge_coplanars(node: bsp_port.Node | None):
    """bspMergeCoplanars (0x36200): merge adjacent coplanar surfaces. Modelled at the node
    level as: a node whose surface set is empty AND has only one child collapses into the
    child (the over-split linear chain a convex solid produces -> one node per face)."""
    if node is None:
        return None
    node.front = merge_coplanars(node.front)
    node.back = merge_coplanars(node.back)
    # collapse a split-only node (no surface) with a single child into that child
    if not node.surf:
        if node.front and not node.back:
            return node.front
        if node.back and not node.front:
            return node.back
    return node


def count_surface_nodes(node: bsp_port.Node | None) -> int:
    """Count nodes that carry at least one surface (the editor's final node count is ~the
    surviving surface-bearing nodes after refresh/merge drops empty split nodes)."""
    if node is None:
        return 0
    here = 1 if node.surf else 0
    return here + count_surface_nodes(node.front) + count_surface_nodes(node.back)
