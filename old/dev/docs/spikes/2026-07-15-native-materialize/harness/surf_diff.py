#!/usr/bin/env python3
"""Ordered diff of the `Surfs` array: native bspcsg build vs editor golden.

Per-surf fields compared (index by index):

  * texture    — resolved to a NAME, not a raw ref.  Editor: `pkg.name_of_ref(iTexture)`.
                 Native (unassembled bspcsg output): the texture object-ref is not yet wired
                 (typically 0), so it resolves to None — texture WILL diverge everywhere until
                 the assembly step assigns refs; that is expected, and reported plainly.
  * poly_flags — exact.
  * i_brush_poly — exact (the source poly index on the owning brush).
  * i_light_map — compared as a PRESENCE flag (has-lightmap vs -1): the raw index points into
                 each model's own LightMap array, so only presence is comparable.  Native
                 (unlit bspcsg) is -1 everywhere; the editor golden carries baked indices.
  * base       — `pBase` resolved to the actual `Points[pBase]` position (float compare, tol).
  * normal     — `vNormal` resolved to `Vectors[vNormal]` (float compare, tol).
  * tex_u/tex_v — `vTextureU`/`vTextureV` resolved to their `Vectors[...]` axes (float, tol).

Indices (`pBase`, `vNormal`, `vTextureU/V`) are NOT compared directly — they index each
model's own Points/Vectors pools, whose orderings differ — so they are resolved to the
geometric value they name and those values are compared.

Reports matching-prefix length, first divergence (with the differing fields + values), and a
per-field divergence histogram, so it works as a phase gate.

Usage:
    .venv/bin/python docs/.../harness/surf_diff.py [--tol 1e-3] [--top 12]

Importable:  diff_surfs(native, editor, editor_pkg, tol=1e-3) -> dict.
"""
from __future__ import annotations

import argparse
from collections import Counter

# fields compared per surf; geometric ones (base/normal/tex_u/tex_v) are float-compared.
_GEOM_FIELDS = ["base", "normal", "tex_u", "tex_v"]
_EXACT_FIELDS = ["texture", "poly_flags", "i_brush_poly", "has_lightmap"]


def _resolve(model, idx, arr):
    return tuple(arr[idx]) if 0 <= idx < len(arr) else None


def _surf_view(model, s, pkg=None):
    """Extract the comparable field bundle for one surf."""
    tex = pkg.name_of_ref(s.texture_ref) if pkg is not None else None
    if tex is None:
        tex = f"<ref {s.texture_ref}>"          # unresolved (native) — keep the raw ref visible
    return dict(
        texture=tex,
        poly_flags=s.poly_flags,
        i_brush_poly=s.i_brush_poly,
        has_lightmap=(s.i_light_map >= 0),
        base=_resolve(model, s.p_base, model.points),
        normal=_resolve(model, s.v_normal, model.vectors),
        tex_u=_resolve(model, s.v_texture_u, model.vectors),
        tex_v=_resolve(model, s.v_texture_v, model.vectors),
    )


def _geom_eq(a, b, tol):
    if a is None or b is None:
        return a is b
    return len(a) == len(b) and all(abs(x - y) <= tol for x, y in zip(a, b))


def _surf_fields_differ(va, vb, tol):
    diff = []
    for f in _EXACT_FIELDS:
        if va[f] != vb[f]:
            diff.append(f)
    for f in _GEOM_FIELDS:
        if not _geom_eq(va[f], vb[f], tol):
            diff.append(f)
    return diff


def diff_surfs(native, editor, editor_pkg=None, native_pkg=None, tol: float = 1e-3) -> dict:
    """Compare the two `Surfs` arrays.  Returns lengths, matching prefix, first divergence,
    and a per-field divergence histogram over the compared range."""
    na, ne = native.surfs, editor.surfs
    compared = min(len(na), len(ne))
    hist = Counter()
    prefix = None
    first = None
    for i in range(compared):
        va = _surf_view(native, na[i], native_pkg)
        vb = _surf_view(editor, ne[i], editor_pkg)
        d = _surf_fields_differ(va, vb, tol)
        if d:
            hist.update(d)
            if prefix is None:
                prefix = i
                first = dict(index=i, fields=d,
                             native={f: va[f] for f in d}, editor={f: vb[f] for f in d})
    if prefix is None:
        prefix = compared
    return dict(len_native=len(na), len_editor=len(ne), compared=compared,
                prefix=prefix, first_divergence=first, field_histogram=hist)


def print_report(res: dict):
    print("=== SURF DIFF (native bspcsg vs editor golden) ===")
    print(f"lengths: native={res['len_native']}  editor={res['len_editor']}  "
          f"compared={res['compared']}"
          + ("" if res['len_native'] == res['len_editor']
             else f"  (MISMATCH {res['len_native'] - res['len_editor']:+d})"))
    pct = (100.0 * res['prefix'] / res['compared']) if res['compared'] else 0.0
    print(f"matching prefix: {res['prefix']} / {res['compared']} ({pct:.2f}% of compared)")
    fd = res['first_divergence']
    if fd is None:
        print("first divergence: NONE over compared range")
    else:
        print(f"first divergence @ surf[{fd['index']}], fields: {', '.join(fd['fields'])}")
        for f in fd['fields']:
            print(f"    {f:<14} native={fd['native'][f]!r:<30} editor={fd['editor'][f]!r}")
    print("field-divergence histogram (over compared range, #surfs differing per field):")
    if res['field_histogram']:
        for f, c in res['field_histogram'].most_common():
            print(f"    {f:<14} {c:>6}  ({100.0 * c / res['compared']:.1f}%)")
    else:
        print("    (none — all compared surfs match)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tol", type=float, default=1e-3,
                    help="float tolerance for comparing resolved base/normal/tex-axis vectors (default 1e-3)")
    args = ap.parse_args()

    import castle_build
    native, editor, pkg = castle_build.load_both()
    print_report(diff_surfs(native, editor, editor_pkg=pkg, tol=args.tol))


if __name__ == "__main__":
    main()
