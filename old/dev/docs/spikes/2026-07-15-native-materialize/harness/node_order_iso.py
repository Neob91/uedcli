#!/usr/bin/env python3
"""Node-order oracle: prove the native BSP tree is ISOMORPHIC to the editor golden, and localize
the remaining ARRAY-ORDER (linearization) gap.

Two views (both on the final on-disk trees, native `NativeCastle.dx` vs editor `Test_Castle.dx`):

  * ISOMORPHISM WALK — follow (iFront, iBack, iPlane) from the root on BOTH trees in lock-step,
    comparing planes with an absolute tolerance.  A 0-divergence result means the two trees have
    the SAME SHAPE (same split at every tree position) — the residual is purely how nodes are
    laid out in the `Nodes[]` array, NOT the partition.

  * PERMUTATION RUNS — the map native_array_idx -> editor_array_idx (from the isomorphism), printed
    as constant-delta runs.  Before the §82 §10.17 tail-reorder this showed the ~56 Pass-D
    boundary-wall zone-split fragments scattered EARLY in native while the editor appends them all
    at the tail (indices ~1100-1155); after the reorder the map is (near-)identity.

This is the durable evidence for §82 §10.17 (the node-emit-ORDER lever).  Run under `.venv/bin/python`.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import castle_build

TOL = 2e-3


def plane_eq(a, b, tol=TOL):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def iso_map(native, editor):
    """Link-following lock-step walk; returns (n2e map, list of divergences)."""
    na, ne = native.nodes, editor.nodes
    n2e, divs = {}, []
    stack = [(0, 0, "root")]
    while stack:
        ni, ei, path = stack.pop()
        if ni == -1 and ei == -1:
            continue
        if ni == -1 or ei == -1:
            divs.append((path, f"shape mismatch ni={ni} ei={ei}"))
            continue
        if ni in n2e:
            continue
        n2e[ni] = ei
        A, B = na[ni], ne[ei]
        if not plane_eq(A.plane, B.plane):
            divs.append((path, f"PLANE ni={ni} ei={ei}"))
            continue
        stack.append((A.i_front, B.i_front, path + "/F"))
        stack.append((A.i_back, B.i_back, path + "/B"))
        stack.append((A.i_plane, B.i_plane, path + "/P"))
    return n2e, divs


def main():
    native, editor, _ = castle_build.load_both()
    N = len(native.nodes)
    print(f"native nodes={N} editor nodes={len(editor.nodes)}")

    n2e, divs = iso_map(native, editor)
    print(f"\n=== ISOMORPHISM (plane-eq, link-following from root) ===")
    print(f"  matched {len(n2e)}/{len(editor.nodes)} nodes; divergences {len(divs)}")
    for p, d in divs[:20]:
        print(f"    {p:40s} {d}")

    ident = sum(1 for k, v in n2e.items() if k == v)
    print(f"  identity-position (native idx == editor idx): {ident}/{len(n2e)}")

    # positional plane match (the raw gate metric, abs tol 1e-3)
    peq = lambda a, b: all(abs(x - y) <= 1e-3 for x, y in zip(a, b))
    pm = sum(1 for i in range(min(N, len(editor.nodes))) if peq(native.nodes[i].plane, editor.nodes[i].plane))
    fd = next((i for i in range(min(N, len(editor.nodes))) if not peq(native.nodes[i].plane, editor.nodes[i].plane)), None)
    print(f"  RAW positional plane match {pm}/{len(editor.nodes)} (abs tol 1e-3); first divergence {fd}")

    print(f"\n=== PERMUTATION RUNS (native_idx -> editor_idx, delta = e - n) ===")
    runs, i = [], 0
    while i < N:
        if i not in n2e:
            i += 1
            continue
        d = n2e[i] - i
        j = i
        while j < N and j in n2e and (n2e[j] - j) == d:
            j += 1
        runs.append((i, j - 1, d))
        i = j
    for a, b, d in runs[:40]:
        print(f"  native[{a:4d}..{b:4d}]  editor delta {d:+5d}   (len {b - a + 1})")
    print(f"  total runs: {len(runs)}  (1 run + identity = fully positional)")


if __name__ == "__main__":
    main()
