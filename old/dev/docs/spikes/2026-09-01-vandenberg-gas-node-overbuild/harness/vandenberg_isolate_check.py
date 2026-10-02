#!/usr/bin/env python3
"""Native-vs-isolated-golden check for Vandenberg Gas Brush54 (see `vandenberg_isolate_golden.py`
for the isolation context: one 20000uu ADD shell + Brush54 itself, CSG_Subtract).

Builds the SAME two-brush set through native's own `build_geometry_bspcsg` and compares node/surf/
leaf/vert/point/vector counts against the live-editor-built isolated golden -- confirms whether
Brush54's own over-build (node d=+901, surf d=+110 in the full-level per-brush attribution) is
INTRINSIC to this one brush's geometry (reproduces isolated) or a CONTEXTUAL effect of the other
869 brushes in the level.

Usage: .venv/bin/python vandenberg_isolate_check.py
"""
import sys
from pathlib import Path

ROOT = Path("/workspace/uedcli/.claude/worktrees/vandenberg-gas-parity")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

from uedcli import trunk, builders, writes                # noqa: E402
from uedcli.native import brush_marshal as BM              # noqa: E402
from uedcli.native import umodel as UM                     # noqa: E402
import uedcli_native                                        # noqa: E402
import utexture_decode as UT                                # noqa: E402

TRUNK = (ROOT / "_scratch/uedcli-parity-cache/"
         "7d06dd6155e5daa7c78e76ed19a66068852973670d1c56dddd9628b2ca393c13/trunk/maps/12_vandenberg_gas")
GOLDEN = ROOT / "_scratch/vandenberg-isolate/golden_Brush54.dx"


def parse_golden(path):
    pkg = UT.load_package(str(path))
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    m = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])
    return pkg, m


def main():
    lvl, _ranks = trunk.read_level(TRUNK)
    target = lvl.actors["Brush54"]
    lo, hi = writes.actor_bounds(target)
    center = (float((lo[0] + hi[0]) / 2), float((lo[1] + hi[1]) / 2), float((lo[2] + hi[2]) / 2))
    shell = builders.make_brush_actor("CtxShell", builders.cube(20000, 20000, 20000),
                                       location=center, csg="add")

    names = ["CtxShell", "Brush54"]
    actors = {"CtxShell": shell, "Brush54": target}
    ins = [BM._build_brush_input(n, actors[n]) for n in names]

    built = uedcli_native.build_geometry_bspcsg(ins)
    nbody = uedcli_native.serialize_model(built)
    nm = UM.parse_model_body(nbody, 0, len(nbody))

    epkg, em = parse_golden(GOLDEN)

    print(f"native  nodes={len(nm.nodes):5} surfs={len(nm.surfs):5} leaves={len(nm.leaves):5} "
          f"verts={len(nm.verts):6} points={len(nm.points):6} vectors={len(nm.vectors):6}")
    print(f"editor  nodes={len(em.nodes):5} surfs={len(em.surfs):5} leaves={len(em.leaves):5} "
          f"verts={len(em.verts):6} points={len(em.points):6} vectors={len(em.vectors):6}")
    print(f"delta   nodes={len(nm.nodes)-len(em.nodes):+5} surfs={len(nm.surfs)-len(em.surfs):+5} "
          f"leaves={len(nm.leaves)-len(em.leaves):+5} verts={len(nm.verts)-len(em.verts):+6} "
          f"points={len(nm.points)-len(em.points):+6} vectors={len(nm.vectors)-len(em.vectors):+6}")

    # Attribute native/editor nodes to CtxShell vs Brush54 (i_actor 0 vs 1).
    from collections import Counter
    nc = Counter(names[s.i_actor] if 0 <= s.i_actor < len(names) else s.i_actor for s in nm.surfs)
    ec = Counter(epkg.name_of_ref(s.i_actor) for s in em.surfs)
    print(f"native surf-by-brush: {dict(nc)}")
    print(f"editor surf-by-brush: {dict(ec)}")


if __name__ == "__main__":
    raise SystemExit(main())
