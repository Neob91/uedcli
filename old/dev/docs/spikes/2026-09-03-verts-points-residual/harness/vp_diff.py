#!/usr/bin/env python3
"""Verts/Points pool differ: native `build_geometry_bspcsg` vs the cached self-built golden.

For a level whose tree is already node/surf/leaf-EXACT, localizes the remaining verts/points
count residual:
  - per-node ring diff (same node index both sides): num_vertices deltas and ring-coordinate
    mismatches, resolving iVertex -> Points;
  - orphan verts (verts no node's [i_vert_pool, +num_vertices) range covers) per side;
  - Points multiset diff by exact float triple, with back-references (which surfs' p_base /
    which verts name each extra point).

Usage: .venv/bin/python vp_diff.py <path/to/OG.dx> [--json]
Reads the golden from /tmp/uedcli-parity-cache/<hash>/golden.dx and the trunk from the shared
trunk cache (sweep_lib.shared_trunk_cache_root) -- offline, no editor.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
PR_HARNESS = HERE.parents[1] / "2026-08-31-native-parity-report/harness"
sys.path.insert(0, str(PR_HARNESS))

import parity_lib as pl          # noqa: E402
import parity_compare as pc      # noqa: E402
import sweep_lib as sl           # noqa: E402


def load_pair(dx_path: Path):
    h = pl.content_hash(dx_path)
    layout = pl.cache_layout(pl.CACHE_ROOT_DEFAULT, h)
    if not layout.golden.exists():
        sys.exit(f"no cached golden for {dx_path} (hash {h})")
    trunk_root = sl.shared_trunk_cache_root(HERE) / h / "trunk" / "maps"
    trunks = list(trunk_root.iterdir()) if trunk_root.is_dir() else []
    if len(trunks) != 1:
        sys.exit(f"expected exactly one trunk under {trunk_root}, found {trunks}")
    native_model, _level = pc.build_native_model(trunks[0])
    golden_model = pc.parse_dx_model(layout.golden)
    return native_model, golden_model


def ring(model, node) -> list[tuple]:
    return [tuple(model.points[model.verts[node.i_vert_pool + k].i_vertex])
            for k in range(node.num_vertices)]


def referenced_vert_indices(model) -> set[int]:
    out: set[int] = set()
    for n in model.nodes:
        out.update(range(n.i_vert_pool, n.i_vert_pool + n.num_vertices))
    return out


def diff(native, golden) -> dict:
    res: dict = {"counts": {
        "nodes": (len(native.nodes), len(golden.nodes)),
        "surfs": (len(native.surfs), len(golden.surfs)),
        "leaves": (len(native.leaves), len(golden.leaves)),
        "verts": (len(native.verts), len(golden.verts)),
        "points": (len(native.points), len(golden.points)),
        "vectors": (len(native.vectors), len(golden.vectors)),
    }}

    nv_diff, ring_diff = [], []
    for i in range(min(len(native.nodes), len(golden.nodes))):
        nn, gn = native.nodes[i], golden.nodes[i]
        if nn.num_vertices != gn.num_vertices:
            nv_diff.append({"node": i, "native_nv": nn.num_vertices, "golden_nv": gn.num_vertices,
                            "i_surf": (nn.i_surf, gn.i_surf)})
        elif ring(native, nn) != ring(golden, gn):
            ring_diff.append(i)
    res["nodes_nv_differ"] = nv_diff
    res["nodes_ring_coords_differ"] = {"count": len(ring_diff), "first": ring_diff[:10]}

    n_ref = referenced_vert_indices(native)
    g_ref = referenced_vert_indices(golden)
    res["orphan_verts"] = {"native": len(native.verts) - len(n_ref),
                           "golden": len(golden.verts) - len(g_ref)}

    n_pts = Counter(tuple(p) for p in native.points)
    g_pts = Counter(tuple(p) for p in golden.points)
    extra = n_pts - g_pts     # in native, not golden
    missing = g_pts - n_pts   # in golden, not native
    res["points_multiset"] = {"native_extra": sum(extra.values()),
                              "golden_extra": sum(missing.values())}

    def backrefs(model, coords: Counter) -> list[dict]:
        want = set(coords)
        by_coord: dict[tuple, dict] = {c: {"coord": c, "point_idx": [], "surf_pbase": [],
                                           "vert_idx_ref": [], "vert_orphan_ref": []}
                                       for c in want}
        idx_of = {}
        for pi, p in enumerate(model.points):
            t = tuple(p)
            if t in want:
                by_coord[t]["point_idx"].append(pi)
                idx_of.setdefault(pi, t)
        for si, s in enumerate(model.surfs):
            t = idx_of.get(s.p_base)
            if t is not None:
                by_coord[t]["surf_pbase"].append(si)
        ref = referenced_vert_indices(model)
        for vi, v in enumerate(model.verts):
            t = idx_of.get(v.i_vertex)
            if t is not None:
                key = "vert_idx_ref" if vi in ref else "vert_orphan_ref"
                by_coord[t][key].append(vi)
        return list(by_coord.values())

    res["extra_points_backrefs_native"] = backrefs(native, extra)
    res["missing_points_backrefs_golden"] = backrefs(golden, missing)
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dx_path")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    native, golden = load_pair(Path(args.dx_path))
    res = diff(native, golden)
    if args.json:
        print(json.dumps(res, indent=1, default=str))
        return
    for k, v in res["counts"].items():
        print(f"{k:8s} native={v[0]:7d} golden={v[1]:7d} d={v[0]-v[1]:+d}")
    print("nodes with differing num_vertices:", len(res["nodes_nv_differ"]))
    for d in res["nodes_nv_differ"][:20]:
        print("  ", d)
    print("nodes with same nv but different ring coords:", res["nodes_ring_coords_differ"]["count"],
          res["nodes_ring_coords_differ"]["first"])
    print("orphan verts:", res["orphan_verts"])
    print("points multiset:", res["points_multiset"])
    for side in ("extra_points_backrefs_native", "missing_points_backrefs_golden"):
        rows = res[side]
        print(f"{side}: {len(rows)} coords")
        for r in rows[:20]:
            print("  ", r)


if __name__ == "__main__":
    main()
