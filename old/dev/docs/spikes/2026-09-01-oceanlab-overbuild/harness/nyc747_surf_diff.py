#!/usr/bin/env python3
"""Per-brush surf-count attribution for `03_NYC_747.dx`'s residual post-`bsp_validate_brush_links`
Base-fix (`d07622e`): nodes native=4530 golden=4462 d=+68; surfs native=2021 golden=2026 d=-5;
leaves native=560 golden=570 d=-10 (breadth pass 2026-09-01, cached golden re-measured against the
already-shipped fix).

Same brush-index convention as `fc08_surf_diff.py`/`oceanlab_isolate_check.py`: native `BspSurf.i_actor`
is a 0-based index into the world-CSG brush `names` list; golden `BspSurf.i_actor` is an editor obj-ref
resolved via `epkg.name_of_ref`.

Usage: .venv/bin/python nyc747_surf_diff.py
"""
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/workspace/uedcli/.claude/worktrees/nyc747-parity-residual")
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

    nc = Counter(names[s.i_actor] if 0 <= s.i_actor < len(names) else s.i_actor
                 for s in nm.surfs)
    ec = Counter(epkg.name_of_ref(s.i_actor) for s in em.surfs)

    all_names = set(nc) | set(ec)
    diffs = [(nam, nc.get(nam, 0), ec.get(nam, 0)) for nam in all_names
              if nc.get(nam, 0) != ec.get(nam, 0)]
    diffs.sort(key=lambda t: names.index(t[0]) if t[0] in names else -1)
    print(f"\n{len(diffs)} brushes differ in surf count (native, editor):")
    for nam, n, e in diffs:
        idx = names.index(nam) if nam in names else -1
        a = level.actors[nam] if nam in level.actors else None
        p = dict(a.props) if a else {}
        cls = p.get("CsgOper", "?")
        flags = p.get("PolyFlags", "?")
        print(f"  idx={idx:4} {nam:20s} native={n:3} editor={e:3} d={n-e:+d}  CsgOper={cls} PolyFlags={flags}")

    print("\nnode/leaf/surf totals: native", len(nm.nodes), len(nm.surfs), len(nm.leaves),
          " editor", len(em.nodes), len(em.surfs), len(em.leaves))


if __name__ == "__main__":
    raise SystemExit(main())
