#!/usr/bin/env python3
"""Ordered diff of the vertex/vector pools: native bspcsg build vs editor golden.

Three parallel pools are compared, each the same way (ordered-prefix + permutation test):

  * Points   — `TArray<FVector>` (the BSP vertex positions).  Float compare, tol.
  * Vectors  — `TArray<FVector>` (shared normals + texture axes).  Float compare, tol.
  * FVerts   — the `Verts` pool, one `(iVertex, iSide)` per entry (iVertex indexes Points,
               iSide the shared-side pool).  Integer compare, exact.

For each pool the tool reports:
  * matching prefix — longest run from index 0 that is equal (floats within tol),
  * first divergence — index + the two differing values,
  * lengths on both sides (handles unequal lengths without crashing),
  * PERMUTATION verdict — is it the SAME multiset of values in a different order
    ("permutation": ordering bug) versus genuinely different values ("value-diff":
    the sets differ)?  Floats are bucketed at the tolerance for the multiset test.

Note on FVerts: `iVertex` indexes each model's OWN Points array; when the Points orderings
differ, the FVert multiset test is only meaningful as a raw-(iVertex,iSide) comparison — a
"value-diff" there can simply reflect a different Points order, so read it together with the
Points verdict.

Usage:
    .venv/bin/python docs/.../harness/pool_diff.py [--tol 1e-3]

Importable:  diff_points(), diff_vectors(), diff_verts(), diff_pools() (all -> dict).
"""
from __future__ import annotations

import argparse
from collections import Counter


def _fkey(v, tol):
    """Bucket a float-vector to a hashable multiset key at the tolerance grid."""
    q = 1.0 / tol if tol else 1.0
    return tuple(round(c * q) for c in v)


def _vec_eq(a, b, tol):
    return len(a) == len(b) and all(abs(x - y) <= tol for x, y in zip(a, b))


def _diff_float_pool(a, b, tol, label):
    compared = min(len(a), len(b))
    prefix = compared
    first = None
    for i in range(compared):
        if not _vec_eq(a[i], b[i], tol):
            prefix = i
            first = dict(index=i, native=tuple(a[i]), editor=tuple(b[i]))
            break
    ka = Counter(_fkey(v, tol) for v in a)
    kb = Counter(_fkey(v, tol) for v in b)
    same_multiset = ka == kb
    return dict(label=label, len_native=len(a), len_editor=len(b), compared=compared,
                prefix=prefix, first_divergence=first,
                permutation=(same_multiset and len(a) == len(b) and prefix < compared),
                same_multiset=same_multiset,
                only_native=sum((ka - kb).values()), only_editor=sum((kb - ka).values()))


def _diff_int_pool(a, b, label):
    """a, b are lists of hashable tuples (exact compare)."""
    compared = min(len(a), len(b))
    prefix = compared
    first = None
    for i in range(compared):
        if a[i] != b[i]:
            prefix = i
            first = dict(index=i, native=a[i], editor=b[i])
            break
    ka, kb = Counter(a), Counter(b)
    same_multiset = ka == kb
    return dict(label=label, len_native=len(a), len_editor=len(b), compared=compared,
                prefix=prefix, first_divergence=first,
                permutation=(same_multiset and len(a) == len(b) and prefix < compared),
                same_multiset=same_multiset,
                only_native=sum((ka - kb).values()), only_editor=sum((kb - ka).values()))


def diff_points(native, editor, tol: float = 1e-3) -> dict:
    return _diff_float_pool(native.points, editor.points, tol, "Points")


def diff_vectors(native, editor, tol: float = 1e-3) -> dict:
    return _diff_float_pool(native.vectors, editor.vectors, tol, "Vectors")


def diff_verts(native, editor) -> dict:
    a = [(v.i_vertex, v.i_side) for v in native.verts]
    b = [(v.i_vertex, v.i_side) for v in editor.verts]
    return _diff_int_pool(a, b, "FVerts (iVertex,iSide)")


def diff_pools(native, editor, tol: float = 1e-3) -> dict:
    return dict(points=diff_points(native, editor, tol),
                vectors=diff_vectors(native, editor, tol),
                verts=diff_verts(native, editor))


def _print_pool(res: dict):
    print(f"--- {res['label']} ---")
    print(f"  lengths: native={res['len_native']}  editor={res['len_editor']}  "
          f"compared={res['compared']}"
          + ("" if res['len_native'] == res['len_editor']
             else f"  (MISMATCH {res['len_native'] - res['len_editor']:+d})"))
    pct = (100.0 * res['prefix'] / res['compared']) if res['compared'] else 0.0
    print(f"  matching prefix: {res['prefix']} / {res['compared']} ({pct:.2f}% of compared)")
    fd = res['first_divergence']
    if fd is None:
        print("  first divergence: NONE over compared range")
    else:
        print(f"  first divergence @ [{fd['index']}]: native={fd['native']!r}  editor={fd['editor']!r}")
    if res['permutation']:
        verdict = "PERMUTATION (same value multiset, different order)"
    elif res['same_multiset']:
        verdict = "identical (same multiset, same order over compared range)"
    else:
        verdict = (f"VALUE-DIFF (multisets differ: {res['only_native']} only-native, "
                   f"{res['only_editor']} only-editor)")
    print(f"  verdict: {verdict}")


def print_report(res: dict):
    print("=== POOL DIFF (native bspcsg vs editor golden) ===")
    _print_pool(res['points'])
    _print_pool(res['vectors'])
    _print_pool(res['verts'])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tol", type=float, default=1e-3,
                    help="float tolerance for comparing Point/Vector components (default 1e-3)")
    args = ap.parse_args()

    import castle_build
    native, editor, _pkg = castle_build.load_both()
    print_report(diff_pools(native, editor, tol=args.tol))


if __name__ == "__main__":
    main()
