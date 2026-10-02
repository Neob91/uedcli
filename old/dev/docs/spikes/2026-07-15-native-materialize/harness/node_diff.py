#!/usr/bin/env python3
"""Node-for-node ordered diff of the `Nodes` array: native bspcsg build vs editor golden.

The acceptance gate for a byte-identity phase is "the first N nodes match exactly".  This
tool localizes exactly where that breaks:

  * ORDERED pass — walk both `Nodes` arrays index by index and compare the per-node tuple
    (plane, iVertPool, NumVertices, iSurf, iFront, iBack, iPlane, iZone, node_flags).  It
    reports the matching-prefix length (longest run from index 0 where EVERY field is equal),
    the FIRST diverging index with the exact fields that differ, and a histogram of which field
    diverges most across the whole compared range.
  * MULTISET pass — order-independent: key each node by its (rounded) splitting plane and count
    multiplicities on each side.  This separates "same planes, wrong tree order" (multisets
    match, ordered prefix short) from "genuinely different set of splits" (multisets differ).
    Node `iSurf` is NOT part of the key: it indexes each model's own `Surfs` array, whose
    ordering also differs, so it is not comparable across the two models — the plane is the
    geometric identity of a split.

Floats (the plane) compare with a tolerance (default 1e-3); indices/flags compare exactly.

Usage:
  castle_build paths are baked in (castle trunk vs Test_Castle.dx):
    .venv/bin/python docs/.../harness/node_diff.py [--tol 1e-3] [--top 15]

Importable:  diff_nodes(native_model, editor_model, tol=1e-3) -> dict.
"""
from __future__ import annotations

import argparse
from collections import Counter

import castle_build

# per-node fields compared (name -> extractor); plane is float-compared, the rest exact.
_INT_FIELDS = ["i_vert_pool", "num_vertices", "i_surf", "i_front", "i_back",
               "i_plane", "i_zone", "node_flags"]


def _plane_key(plane, nd=3):
    return tuple(round(c, nd) for c in plane)


def _plane_eq(a, b, tol):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def _node_fields_differ(na, nb, tol):
    """Return the list of field names that differ between two nodes."""
    diff = []
    if not _plane_eq(na.plane, nb.plane, tol):
        diff.append("plane")
    for f in _INT_FIELDS:
        if getattr(na, f) != getattr(nb, f):
            diff.append(f)
    return diff


def diff_nodes(native, editor, tol: float = 1e-3) -> dict:
    """Compare the two `Nodes` arrays.  Returns a dict with:
        len_native, len_editor, compared (min of the two),
        prefix (longest all-fields-equal run from index 0),
        first_divergence (dict index+fields+values, or None),
        field_histogram (Counter field->#indices-differing over compared range),
        multiset (dict: shared, only_native, only_editor plane-key counts).
    """
    na, ne = native.nodes, editor.nodes
    compared = min(len(na), len(ne))

    hist = Counter()
    prefix = None
    first = None
    for i in range(compared):
        d = _node_fields_differ(na[i], ne[i], tol)
        if d:
            hist.update(d)
            if prefix is None:
                prefix = i
                first = dict(
                    index=i, fields=d,
                    native={f: (na[i].plane if f == "plane" else getattr(na[i], f)) for f in d},
                    editor={f: (ne[i].plane if f == "plane" else getattr(ne[i], f)) for f in d},
                )
    if prefix is None:
        prefix = compared  # every compared index matched

    # order-independent multiset over splitting planes
    kn = Counter(_plane_key(n.plane) for n in na)
    ke = Counter(_plane_key(n.plane) for n in ne)
    shared = sum((kn & ke).values())
    only_native = sum((kn - ke).values())
    only_editor = sum((ke - kn).values())

    return dict(
        len_native=len(na), len_editor=len(ne), compared=compared,
        prefix=prefix, first_divergence=first, field_histogram=hist,
        multiset=dict(shared=shared, only_native=only_native, only_editor=only_editor,
                      kn=kn, ke=ke),
    )


def print_report(res: dict, top: int = 15):
    print("=== NODE DIFF (native bspcsg vs editor golden) ===")
    print(f"lengths: native={res['len_native']}  editor={res['len_editor']}  "
          f"compared={res['compared']}")
    if res['len_native'] != res['len_editor']:
        print(f"  (LENGTH MISMATCH: {res['len_native'] - res['len_editor']:+d} nodes native-vs-editor)")
    print(f"matching prefix: {res['prefix']} / {res['compared']} nodes "
          f"({100.0 * res['prefix'] / res['compared']:.2f}% of compared)"
          if res['compared'] else "matching prefix: n/a (an array is empty)")

    fd = res['first_divergence']
    if fd is None:
        print("first divergence: NONE over the compared range")
    else:
        print(f"first divergence @ node[{fd['index']}], fields differing: {', '.join(fd['fields'])}")
        for f in fd['fields']:
            print(f"    {f:<14} native={fd['native'][f]!r:<28} editor={fd['editor'][f]!r}")

    print("field-divergence histogram (over compared range, #nodes differing per field):")
    if res['field_histogram']:
        for f, c in res['field_histogram'].most_common():
            print(f"    {f:<14} {c:>6}  ({100.0 * c / res['compared']:.1f}%)")
    else:
        print("    (none — all compared nodes match)")

    ms = res['multiset']
    print("order-independent plane multiset:")
    print(f"    shared planes (with multiplicity): {ms['shared']}")
    print(f"    only in native:                    {ms['only_native']}")
    print(f"    only in editor:                    {ms['only_editor']}")
    if ms['only_editor']:
        onlyed = (ms['ke'] - ms['kn'])
        print(f"    top {top} planes only in editor (plane -> count):")
        for plane, c in onlyed.most_common(top):
            print(f"        {plane}  x{c}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tol", type=float, default=1e-3,
                    help="float tolerance for comparing node splitting-plane components (default 1e-3)")
    ap.add_argument("--top", type=int, default=15,
                    help="how many 'only-in-editor' planes to list in the multiset section (default 15)")
    args = ap.parse_args()

    native, editor, _pkg = castle_build.load_both()
    res = diff_nodes(native, editor, tol=args.tol)
    print_report(res, top=args.top)


if __name__ == "__main__":
    main()
