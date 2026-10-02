#!/usr/bin/env python3
"""Per-brush node-plane-owner attribution for `03_NYC_747.dx`'s open residual (nodes native=4530
golden=4462 d=+68; surfs EXACT 2026/2026; leaves native=560 golden=570 d=-10 -- confirmed unchanged
2026-09-02, same as the `INDEPENDENT PASS` ring-pool round measured). Since surfs is exact, the
surf-count attribution (`nyc747_surf_diff.py`'s method, already used to fix the -5 surf gap) shows
nothing new -- this uses node-plane-owner (`node.i_surf -> surf.i_actor`, `vandenberg_attrib.py`'s
method) instead, the same technique that isolates a tree-SHAPE divergence when surf counts already
match.

Run as part of the rotated-brush-transform cross-validation (parallel to the same hypothesis on
Area51 Entrance): `nyc747_scan_rotations.py` found exactly ONE genuine non-cardinal multi-axis brush
in the level's world-CSG set, `Brush562` (Pitch=32768, Yaw=32768, Roll=59392 -- Roll is not a
multiple of 16384). This script checks whether that brush's node ownership actually diverges.

Usage: .venv/bin/python nyc747_attrib.py
"""
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

CACHE = ROOT / "_scratch/uedcli-parity-cache/3c2fa42895d171d2453f62a38ade7e6be33247f29def5fa335bd2e70e9d1c953"
TRUNK = CACHE / "trunk/maps/03_nyc_747"
GOLDEN = Path("/tmp/uedcli-parity-cache/3c2fa42895d171d2453f62a38ade7e6be33247f29def5fa335bd2e70e9d1c953/golden.dx")
os.environ.setdefault("UEDCLI_PROJECT", str(CACHE / "trunk"))

from uedcli import trunk                          # noqa: E402
from uedcli.native import brush_marshal as BM      # noqa: E402
from uedcli.native import umodel as UM             # noqa: E402
import uedcli_native                               # noqa: E402
import utexture_decode as UT                       # noqa: E402
from spike_classindex import class_index           # noqa: E402


def parse_golden(path):
    pkg = UT.load_package(str(path))
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    m = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])
    return pkg, m


def main():
    level, _ranks = trunk.read_level(TRUNK)
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    ins = [BM._build_brush_input(n, level.actors[n]) for n in names]
    print("total world-csg brushes:", len(names))

    built = uedcli_native.build_geometry_bspcsg(ins)
    nbody = uedcli_native.serialize_model(built)
    nm = UM.parse_model_body(nbody, 0, len(nbody))

    epkg, em = parse_golden(GOLDEN)

    print(f"native surfs={len(nm.surfs)}  editor surfs={len(em.surfs)}")
    print(f"native nodes={len(nm.nodes)}  editor nodes={len(em.nodes)}")
    print(f"native leaves={len(nm.leaves)}  editor leaves={len(em.leaves)}")

    def node_owner_counts(model, surf_owner_fn):
        c = Counter()
        for node in model.nodes:
            if 0 <= node.i_surf < len(model.surfs):
                c[surf_owner_fn(model.surfs[node.i_surf].i_actor)] += 1
            else:
                c[None] += 1
        return c

    n_owner = node_owner_counts(nm, lambda ia: names[ia] if 0 <= ia < len(names) else ia)
    e_owner = node_owner_counts(em, lambda ia: epkg.name_of_ref(ia))

    all_owner_names = set(n_owner) | set(e_owner)
    node_diffs = [(nam, n_owner.get(nam, 0), e_owner.get(nam, 0)) for nam in all_owner_names
                  if n_owner.get(nam, 0) != e_owner.get(nam, 0)]
    node_diffs.sort(key=lambda t: -abs(t[1] - t[2]))
    total_abs = sum(abs(n - e) for _, n, e in node_diffs)
    net = sum(n - e for _, n, e in node_diffs)
    print(f"\n=== NODE-PLANE-OWNER: {len(node_diffs)}/{len(names)} brushes differ, "
          f"abs-sum={total_abs}, net={net:+d} (full node delta={len(nm.nodes)-len(em.nodes):+d}) ===")
    for nam, n, e in node_diffs[:40]:
        idx = names.index(nam) if nam in names else -1
        a = level.actors[nam] if nam in level.actors else None
        p = dict(a.props) if a else {}
        cls = p.get("CsgOper", "?")
        flags = p.get("PolyFlags", "?")
        rot = p.get("Rotation", "()")
        npolys = len(a.brush.polys) if a and a.brush else "?"
        marker = "  <-- Brush562 (non-cardinal multi-axis)" if nam == "Brush562" else ""
        print(f"  idx={idx:4} {str(nam):20s} native={n:4} editor={e:4} d={n-e:+d}  "
              f"CsgOper={cls} PolyFlags={flags} npolys={npolys} Rotation={rot}{marker}")

    print(f"\nBrush562 present in owner diffs: {'Brush562' in dict((n, 1) for n, *_ in node_diffs)}")
    if "Brush562" in n_owner or "Brush562" in e_owner:
        print(f"  Brush562 node-owner: native={n_owner.get('Brush562', 0)} "
              f"editor={e_owner.get('Brush562', 0)}")

    print("\nnode/leaf/surf totals: native", len(nm.nodes), len(nm.surfs), len(nm.leaves),
          " editor", len(em.nodes), len(em.surfs), len(em.leaves))


if __name__ == "__main__":
    raise SystemExit(main())
