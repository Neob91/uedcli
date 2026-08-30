#!/usr/bin/env python3
"""For each of smuggler's 4 over-surfed brushes, list native's and golden's surfs
attributed to that brush (base point + normal), to find the extra/mismatched one."""
import os
import sys
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
TARGETS = ["Brush547", "Brush550", "Brush273", "Brush457"]


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

    built = uedcli_native.build_geometry_bspcsg(ins)
    nbody = uedcli_native.serialize_model(built)
    nm = UM.parse_model_body(nbody, 0, len(nbody))

    epkg, em = parse_golden(GOLDEN)

    for target in TARGETS:
        a = level.actors[target]
        props = dict(a.props)
        print(f"\n=== {target} (world-csg idx {names.index(target)}) CsgOper={props.get('CsgOper')} "
              f"PolyFlags={props.get('PolyFlags')} main_scale={a.main_scale} post_scale={a.post_scale} "
              f"rotation={props.get('Rotation')} npolys={len(a.brush.polys)}")

        nsurfs = [s for s in nm.surfs if 0 <= s.i_actor < len(names) and names[s.i_actor] == target]
        esurfs = [s for s in em.surfs if epkg.name_of_ref(s.i_actor) == target]
        print(f"  native {len(nsurfs)} surfs, editor {len(esurfs)} surfs")

        def base_of(model, s):
            return model.points[s.p_base]

        def normal_of(model, s):
            return model.vectors[s.v_normal]

        def key(model, s):
            b = base_of(model, s)
            n = normal_of(model, s)
            return (round(n[0], 3), round(n[1], 3), round(n[2], 3),
                    round(b[0] * n[0] + b[1] * n[1] + b[2] * n[2], 1),  # plane w = base.normal
                    getattr(s, 'i_brush_poly', None))

        nkeys = [key(nm, s) for s in nsurfs]
        ekeys = [key(em, s) for s in esurfs]
        from collections import Counter
        nc, ec = Counter(nkeys), Counter(ekeys)
        only_native = nc - ec
        only_editor = ec - nc
        print(f"  keys (normal,dist,i_brush_poly) only in native: {dict(only_native)}")
        print(f"  keys (normal,dist,i_brush_poly) only in editor: {dict(only_editor)}")
        for i, s in enumerate(nsurfs):
            b, n = base_of(nm, s), normal_of(nm, s)
            print(f"    NATIVE surf i_brush_poly={s.i_brush_poly} base=({b[0]:.2f},{b[1]:.2f},{b[2]:.2f}) "
                  f"normal=({n[0]:.3f},{n[1]:.3f},{n[2]:.3f}) poly_flags={s.poly_flags}")
        for i, s in enumerate(esurfs):
            b, n = base_of(em, s), normal_of(em, s)
            print(f"    EDITOR surf i_brush_poly={s.i_brush_poly} base=({b[0]:.2f},{b[1]:.2f},{b[2]:.2f}) "
                  f"normal=({n[0]:.3f},{n[1]:.3f},{n[2]:.3f}) poly_flags={s.poly_flags}")


if __name__ == "__main__":
    raise SystemExit(main())
