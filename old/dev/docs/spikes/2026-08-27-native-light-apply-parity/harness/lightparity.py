#!/usr/bin/env python3
"""Lighting parity between two built `.dx`/`.unr` maps — native vs the editor's `LIGHT APPLY`.

Compares the four bake outputs (spike `2026-07-15-native-materialize/sections/20-lighting-bake.md`
§2): `Model.LightMap` (the `FLightMapIndex` array), `Model.LightBits` (the packed shadow planes),
`Model.Lights` (the flattened per-surf light runs) and each `FBspSurf.iLightMap` link.

Two views, because raw positional bytes alone cannot say WHY they differ:

* SECTION — raw serialized byte lengths and the first differing byte per section.
* PER-RECORD — record *k* of one file against record *k* of the other (both sides emit `LightMap`
  in BSP tree-walk order, §21 (E), so record *k* is the same lit surface when the trees match):
  grid dims, `Pan`, texel scales, run length, and the shadow bits themselves.

`Model.Lights` entries are compact-index object refs into each file's own export table, so this
resolves each ref to its export NAME before comparing — renumbering then stops being a difference.

Usage: lightparity.py NATIVE.dx EDITOR.dx [--repo <uedcli root>]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _load(repo: str):
    sys.path.insert(0, repo)
    from uedcli import upackage
    from uedcli.native import umodel
    return upackage, umodel


def level_model(upackage, umodel, path: str):
    """The level BSP `Model` of a built map, plus the package (for ref->name resolution).

    The level Model is the LARGEST `Engine.Model` export: every brush actor also owns a small shape
    Model, and the world BSP dwarfs them."""
    pkg = upackage.load_package(path)
    best = None
    for i, e in enumerate(pkg.exports):
        if pkg.object_class_name(i + 1) != "Model":
            continue
        if best is None or e["ssize"] > pkg.exports[best]["ssize"]:
            best = i
    if best is None:
        raise SystemExit(f"no Engine.Model export in {path}")
    e = pkg.exports[best]
    return pkg, umodel.parse_model_body(pkg.buf, e["soff"], e["ssize"])


def light_names(pkg, model) -> list[str | None]:
    """`Model.Lights` resolved from compact-index object refs to export names (`None` = the NULL
    terminator that ends a run)."""
    return [None if r == 0 else pkg.name_of_ref(r) for r in model.lights]


def runs(model, names) -> dict[int, list[str | None]]:
    """`record index -> its light run` (the names from `iLightActors` up to the NULL), `[]` for a
    dark record."""
    out = {}
    for k, rec in enumerate(model.light_map):
        if rec.i_light_actors < 0:
            out[k] = []
            continue
        run, i = [], rec.i_light_actors
        while i < len(names) and names[i] is not None:
            run.append(names[i])
            i += 1
        out[k] = run
    return out


def planes(model, rec, run_len: int) -> bytes:
    """The `run_len * ceil(USize/8) * VSize` bytes of this record's shadow planes."""
    if run_len == 0:
        return b""
    n = run_len * ((rec.u_size + 7) // 8) * rec.v_size
    return bytes(model.light_bits[rec.data_offset:rec.data_offset + n])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("native", help="the natively built map")
    ap.add_argument("editor", help="the editor's LIGHT APPLY build of the SAME trunk (the oracle)")
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parents[5]),
                    help="uedcli repo root to import from (default: this file's repo)")
    ap.add_argument("--records", type=int, default=12,
                    help="how many diverging records to list in detail (default 12)")
    args = ap.parse_args()

    upackage, umodel = _load(args.repo)
    npkg, nm = level_model(upackage, umodel, args.native)
    epkg, em = level_model(upackage, umodel, args.editor)

    print(f"{'':22} {'native':>12} {'editor':>12}")
    for label, a, b in (
            ("surfs", len(nm.surfs), len(em.surfs)),
            ("nodes", len(nm.nodes), len(em.nodes)),
            ("points", len(nm.points), len(em.points)),
            ("vectors", len(nm.vectors), len(em.vectors)),
            ("leaves", len(nm.leaves), len(em.leaves)),
            ("LightMap records", len(nm.light_map), len(em.light_map)),
            ("LightBits bytes", len(nm.light_bits), len(em.light_bits)),
            ("Lights entries", len(nm.lights), len(em.lights)),
            ("surfs iLightMap=-1", sum(s.i_light_map < 0 for s in nm.surfs),
             sum(s.i_light_map < 0 for s in em.surfs)),
    ):
        flag = "" if a == b else "   <-- differs"
        print(f"{label:22} {a:>12} {b:>12}{flag}")

    nnames, enames = light_names(npkg, nm), light_names(epkg, em)
    nruns, eruns = runs(nm, nnames), runs(em, enames)

    # Which actors each side lists on a SURFACE, and how often. Counted over the per-surface runs
    # only, never over the whole `Lights` array: the editor's array also holds the per-LEAF
    # permeating region, whose light set is chosen by a different rule (no `bSpecialLit` partition),
    # so counting it would report a light that legitimately lights no surface as a native omission.
    def census(runs_by_rec):
        c = {}
        for run in runs_by_rec.values():
            for n in run:
                c[n] = c.get(n, 0) + 1
        return c
    nc, ec = census(nruns), census(eruns)
    print(f"\nlight actors listed on at least one surface: native {len(nc)}, editor {len(ec)}; "
          f"only-native {len(set(nc) - set(ec))}, only-editor {len(set(ec) - set(nc))}")
    for label, extra in (("only native", sorted(set(nc) - set(ec))),
                         ("only editor", sorted(set(ec) - set(nc)))):
        if extra:
            print(f"  {label} ({len(extra)}): {', '.join(extra[:15])}"
                  + (" ..." if len(extra) > 15 else ""))

    # Per-record compare (record k == record k; both sides emit in BSP tree-walk order).
    common = min(len(nm.light_map), len(em.light_map))
    fields = {"u_size": 0, "v_size": 0, "pan": 0, "u_scale": 0, "v_scale": 0,
              "run": 0, "bits": 0, "all": 0}
    detail = []
    for k in range(common):
        a, b = nm.light_map[k], em.light_map[k]
        bad = []
        if a.u_size != b.u_size:
            bad.append("u_size")
        if a.v_size != b.v_size:
            bad.append("v_size")
        if a.pan != b.pan:
            bad.append("pan")
        if a.u_scale != b.u_scale:
            bad.append("u_scale")
        if a.v_scale != b.v_scale:
            bad.append("v_scale")
        if nruns[k] != eruns[k]:
            bad.append("run")
        if planes(nm, a, len(nruns[k])) != planes(em, b, len(eruns[k])):
            bad.append("bits")
        for f in bad:
            fields[f] += 1
        if not bad:
            fields["all"] += 1
        elif len(detail) < args.records:
            detail.append((k, bad, a, b, nruns[k], eruns[k]))

    print(f"\nper-record over {common} common records: {fields['all']} fully identical")
    for f in ("u_size", "v_size", "pan", "u_scale", "v_scale", "run", "bits"):
        print(f"  {f:8} differs on {fields[f]:6} records")

    if detail:
        print("\nfirst diverging records:")
        for k, bad, a, b, nr, er in detail:
            print(f"  #{k} {','.join(bad)}")
            print(f"     native  u={a.u_size} v={a.v_size} pan={a.pan} "
                  f"us={a.u_scale!r} vs={a.v_scale!r} run={nr}")
            print(f"     editor  u={b.u_size} v={b.v_size} pan={b.pan} "
                  f"us={b.u_scale!r} vs={b.v_scale!r} run={er}")

    # Bit-level agreement over records whose grid and run length match (the honest shadow measure).
    same_bits = tot_bits = 0
    for k in range(common):
        a, b = nm.light_map[k], em.light_map[k]
        if (a.u_size, a.v_size, len(nruns[k])) != (b.u_size, b.v_size, len(eruns[k])):
            continue
        pa, pb = planes(nm, a, len(nruns[k])), planes(em, b, len(eruns[k]))
        for x, y in zip(pa, pb):
            same_bits += 8 - bin(x ^ y).count("1")
            tot_bits += 8
    if tot_bits:
        print(f"\nshadow bits on grid+run-matched records: {same_bits}/{tot_bits} "
              f"= {100.0 * same_bits / tot_bits:.2f}% equal")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
