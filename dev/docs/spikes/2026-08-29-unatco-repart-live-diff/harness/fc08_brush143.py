#!/usr/bin/env python3
"""Deep dive into freeclinic08's Brush143 (idx=144 world-csg): native attributes 6 surfs to
it, editor attributes 5. Print plane/texture/pan for every surf attributed to this brush on
both sides, plus the raw brush polys as authored in the trunk.

Usage: .venv/bin/python fc08_brush143.py
"""
import os
import sys
from pathlib import Path

ROOT = Path("/workspace/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))
os.environ.setdefault("UEDCLI_PROJECT", "/workspace/uedcli/_scratch/geo-confirm-freeclinic08-wk")

from uedcli import trunk                          # noqa: E402
from uedcli.native import brush_marshal as BM      # noqa: E402
from uedcli.native import umodel as UM             # noqa: E402
import uedcli_native                               # noqa: E402
import utexture_decode as UT                       # noqa: E402
from spike_classindex import class_index           # noqa: E402

TRUNK = "/workspace/uedcli/_scratch/geo-confirm-freeclinic08-wk/maps/freeclinic08"
GOLDEN = "/workspace/uedcli/_scratch/geo-confirm-freeclinic08-wk/golden_freeclinic08_generous.dx"
TARGET = "Brush143"


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
    idx = names.index(TARGET)
    print(f"{TARGET} is world-csg index {idx}")

    actor = level.actors[TARGET]
    print(f"\n--- authored brush polys ({TARGET}, CSG op) ---")
    print("brush class/props of interest:", actor.cls,
          [(k, v) for k, v in actor.props if k in ("CsgOper", "PolyFlags")])
    for i, poly in enumerate(actor.brush.polys):
        print(f"  poly {i}: texture={poly.texture!r} n_verts={len(poly.vertices)} "
              f"flags={poly.flags!r}")

    built = uedcli_native.build_geometry_bspcsg(ins)
    nbody = uedcli_native.serialize_model(built)
    nm = UM.parse_model_body(nbody, 0, len(nbody))

    epkg, em = parse_golden(GOLDEN)

    def texname_native(surf):
        # texture_ref resolution not wired in this harness path; report raw ref.
        return surf.texture_ref

    print(f"\n--- native surfs attributed to {TARGET} (world-csg idx {idx}) ---")
    for si, s in enumerate(nm.surfs):
        if s.i_actor == idx:
            print(f"  surf {si}: tex_ref={s.texture_ref} poly_flags={s.poly_flags:#x} "
                  f"i_brush_poly={s.i_brush_poly} p_base={s.p_base} v_normal={s.v_normal} "
                  f"pan={s.pan}")
            print(f"    base point = {nm.points[s.p_base]}")
            print(f"    normal vec = {nm.vectors[s.v_normal]}")

    print(f"\n--- editor surfs attributed to {TARGET} ---")
    for si, s in enumerate(em.surfs):
        if epkg.name_of_ref(s.i_actor) == TARGET:
            texname = epkg.name_of_ref(s.texture_ref) if s.texture_ref else None
            print(f"  surf {si}: tex_ref={s.texture_ref} ({texname}) poly_flags={s.poly_flags:#x} "
                  f"i_brush_poly={s.i_brush_poly} p_base={s.p_base} v_normal={s.v_normal} "
                  f"pan={s.pan}")
            print(f"    base point = {em.points[s.p_base]}")
            print(f"    normal vec = {em.vectors[s.v_normal]}")


if __name__ == "__main__":
    raise SystemExit(main())
