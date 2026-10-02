#!/usr/bin/env python3
"""Per-brush surf-count attribution for smuggler (native surfs = golden+4).

Same convention as fc08_surf_diff.py.
"""
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/workspace/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))
os.environ.setdefault("UEDCLI_PROJECT", "/workspace/uedcli/_scratch/geo-confirm-smuggler")

from uedcli import trunk                          # noqa: E402
from uedcli.native import brush_marshal as BM      # noqa: E402
from uedcli.native import umodel as UM             # noqa: E402
import uedcli_native                               # noqa: E402
import utexture_decode as UT                       # noqa: E402
from spike_classindex import class_index           # noqa: E402

TRUNK = "/workspace/uedcli/_scratch/geo-confirm-smuggler/maps/smuggler"
GOLDEN = "/workspace/uedcli/_scratch/geo-confirm-smuggler/golden_smuggler_resume.dx"


def parse_golden(path):
    pkg = UT.load_package(str(path))
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    m = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])
    return pkg, m


def main():
    level, _ranks = trunk.read_level(Path(TRUNK))
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
        print(f"  idx={idx:4} {nam:20s} native={n:3} editor={e:3} d={n-e:+d}")

    print("\nnode/leaf/surf totals: native", len(nm.nodes), len(nm.surfs), len(nm.leaves),
          " editor", len(em.nodes), len(em.surfs), len(em.leaves))


if __name__ == "__main__":
    raise SystemExit(main())
