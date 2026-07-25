#!/usr/bin/env python3
"""Static BSP structural health check on a native (or editor) .dx Model (spike section 88).

A CPU-bound load hang after import resolution is classically a MALFORMED BSP: a node child index
that cycles (infinite point-region / filter descent), or an out-of-range child/leaf/zone/surf index.
This decodes the largest Model body and asserts:
  - i_front / i_back in [-1, len(nodes))          (a self/cyclic child => infinite descent)
  - the front/back subtree walk terminates (no revisited node => no cycle)
  - i_leaf[k] in [-1, len(leaves)); leaf.i_zone in [0, len(zones)); node.i_zone[k] in [0, len(zones))
  - i_surf in [0, len(surfs)); i_collision_bound/i_render_bound in [-1, len(...))
  - i_vert_pool + num_vertices <= len(verts); vert.i_vertex in range
  - **refs/leaf == 1.0** — every empty terminal cell owns EXACTLY ONE FBspLeaf and no leaf is
    shared: distinct(iLeaf>=0 slots) == count(iLeaf>=0 slots) == len(Leaves), and NO iLeaf>=0 is
    set on a NON-terminal node (child != -1). This is the defining property of a COMPLETED UE1
    Pass-A `AssignLeaves` (Editor.dll 0xa7760 — one leaf appended per empty terminal, §70 §2), and
    it holds on the real shipped `.dx` and on native. A headless golden built with a LEAN rebuild
    (a bare `MAP REBUILD`, no `ZONES` keyword => AssignLeaves never re-runs on the
    final tree) leaves a STALE leaf array from the incremental paste with heavy reuse
    (refs/leaf 9.45, 2750 iLeaf slots on non-terminal nodes) — spike section 91. This check FAILS
    such a golden's LEAF array so it can never be trusted as a LEAF/VERT parity basis.

    BUT NOTE THE TWO-BASIS SPLIT (spike §92 stage 0, 2026-07-19): a bare `MAP REBUILD` golden is
    STILL the correct NODE/SURF/VECTOR parity basis (native models csgRebuild = bare `MAP REBUILD`;
    ANY `BSP REBUILD` re-partitions and inflates nodes — GOOD-ZONES 7273, OPTIMAL-ZONES 6859, vs
    native's 6425 / bare 6314). So a refs/leaf!=1.0 FAILURE here means ONLY "do not use this map's
    LEAVES/VERTS as parity" — its Nodes/Surfs/Vectors remain the trustworthy target. For a clean
    refs/leaf==1.0 leaf/vert basis build with `MAP REBUILD;BSP REBUILD GOOD OPTGEOM ZONES`
    (build_ued_golden.py opt-in), accepting that golden's node count is re-partitioned, not native's.
Prints the first few violations of each kind and a cycle check via DFS with a visited set.
Exit code is non-zero if any file fails a structural check (including refs/leaf != 1.0).

Usage: bsp_health_check.py <map.dx> [<map2.dx> ...]
"""
import sys
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl")
sys.path.insert(0, str(ROOT))
from uedctl.native.pkg_write import parse_package  # noqa: E402
from uedctl.native import umodel as UM  # noqa: E402


def biggest_model(pkg):
    idx = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
              key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[idx]
    return UM.parse_model_body(pkg.buf, e["soff"], e["ssize"])


def check(path):
    pkg = parse_package(Path(path).read_bytes())
    m = biggest_model(pkg)
    N, L, Z, S, V = len(m.nodes), len(m.leaves), len(m.zones), len(m.surfs), len(m.verts)
    print(f"\n=== {Path(path).name} : nodes={N} leaves={L} zones={Z} surfs={S} verts={V} ===")
    bad = {"child_range": [], "leaf_range": [], "nodezone_range": [], "leafzone_range": [],
           "surf_range": [], "vertpool": []}
    for i, n in enumerate(m.nodes):
        for c in (n.i_front, n.i_back):
            if c < -1 or c >= N:
                bad["child_range"].append((i, c))
        for l in n.i_leaf:
            if l < -1 or l >= L:
                bad["leaf_range"].append((i, l))
        for z in n.i_zone:
            if z < 0 or z >= Z:
                bad["nodezone_range"].append((i, z))
        if not (0 <= n.i_surf < S):
            bad["surf_range"].append((i, n.i_surf))
        if n.i_vert_pool + n.num_vertices > V:
            bad["vertpool"].append((i, n.i_vert_pool, n.num_vertices))
    for i, lf in enumerate(m.leaves):
        if lf.i_zone < 0 or lf.i_zone >= Z:
            bad["leafzone_range"].append((i, lf.i_zone))
    for k, v in bad.items():
        flag = "OK" if not v else f"** {len(v)} BAD ** first: {v[:5]}"
        print(f"  {k:16s}: {flag}")

    # refs/leaf == 1.0: every empty terminal cell owns exactly one leaf; no reuse; no iLeaf on a
    # non-terminal node. The signature of a COMPLETED Pass-A AssignLeaves (§70 §2 / §91).
    from collections import Counter
    ref = Counter()
    ileaf_on_internal = 0
    for n in m.nodes:
        # engine order: iLeaf[1]<->i_back (FRONT side), iLeaf[0]<->i_front (BACK side)
        for side, il in enumerate(n.i_leaf):
            if il >= 0:
                ref[il] += 1
                child = n.i_back if side == 1 else n.i_front
                if child != -1:
                    ileaf_on_internal += 1
    total_refs = sum(ref.values())
    distinct = len(ref)
    unref = L - distinct
    reused = sum(1 for c in ref.values() if c > 1)
    refs_per_leaf = (total_refs / L) if L else 0.0
    leaf_ok = (total_refs == L and distinct == L and ileaf_on_internal == 0)
    top = ref.most_common(1)[0] if ref else (None, 0)
    print(f"  leaf_1to1        : {'OK' if leaf_ok else '** CORRUPT **'} "
          f"(leaves={L} iLeaf-slots={total_refs} distinct={distinct} refs/leaf={refs_per_leaf:.2f}; "
          f"reused-leaves={reused} unreferenced={unref} iLeaf-on-internal-node={ileaf_on_internal}"
          + (f"; max-reuse leaf {top[0]}x{top[1]}" if not leaf_ok else "") + ")")
    if not leaf_ok:
        print("    ^ refs/leaf != 1.0 => Leaves array is NOT a completed Pass-A enumeration "
              "(stale from a lean rebuild). DO NOT use this map as a Leaves/Verts parity basis. "
              "Rebuild with `BSP REBUILD OPTIMAL OPTGEOM ZONES` (see spike section 91).")

    ok = leaf_ok and not any(bad.values())

    # cycle detection: DFS the node tree from root 0 (iterative, visited set).
    if N:
        seen = set(); stack = [0]; cyclic = False; visited_count = 0
        while stack:
            x = stack.pop()
            if x < 0 or x >= N:
                continue
            if x in seen:
                cyclic = True
                print(f"  CYCLE/re-visit at node {x} (a node reachable twice => infinite descent risk)")
                break
            seen.add(x); visited_count += 1
            for c in (m.nodes[x].i_front, m.nodes[x].i_back):
                if 0 <= c < N:
                    stack.append(c)
        if not cyclic:
            print(f"  cycle_check      : OK (DFS reached {visited_count}/{N} nodes, no revisit)")
            if visited_count < N:
                print(f"    note: {N - visited_count} nodes NOT reachable from root 0 "
                      f"(coplanar-chain / plane-link nodes are reached via iPlane, not i_front/i_back)")
        ok = ok and not cyclic
    return ok


def main():
    all_ok = True
    for p in sys.argv[1:]:
        all_ok = check(p) and all_ok
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
