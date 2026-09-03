#!/usr/bin/env python3
"""Full node/surf dump of the 2-brush Paris Underground minimal case, native vs the n=2 prefix
golden (built by pu_prefix_search.py)."""
import os
import sys
from pathlib import Path

WT = Path(__file__).resolve().parents[5]  # harness/<slug>/spikes/docs/dev -> repo root
sys.path.insert(0, str(WT))
sys.path.insert(0, str(WT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(WT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

TRUNK = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-check/_scratch/uedcli-parity-cache"
             "/bdf66b5dc02df008a53f5018b5aeab950cf13481c2a49bd0f683dd714429c718/trunk")
GOLDEN = WT / "_scratch/pu-prefix/n0002/golden_n0002.dx"
os.environ.setdefault("UEDCLI_PROJECT", str(TRUNK))

from uedcli import trunk as TR
from uedcli.native import brush_marshal as BM
from uedcli.native import umodel as UM
import uedcli_native
import utexture_decode as UT
from spike_classindex import class_index

level, _ = TR.read_level(TRUNK / "maps/11_paris_underground")
ci = class_index()
names = [n for n in level.order
         if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)][:2]
ins = [BM._build_brush_input(n, level.actors[n]) for n in names]
built = uedcli_native.build_geometry_bspcsg(ins)
body = uedcli_native.serialize_model(built)
nm = UM.parse_model_body(body, 0, len(body))

pkg = UT.load_package(str(GOLDEN))
models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
em = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])


def dump(model, label, owner):
    print(f"--- {label}: nodes={len(model.nodes)} surfs={len(model.surfs)} "
          f"leaves={len(model.leaves)} ---")
    for i, s in enumerate(model.surfs):
        n = model.vectors[s.v_normal]
        b = model.points[s.p_base]
        print(f" surf {i:2} owner={owner(s.i_actor)!s:10} normal=({n[0]:+.3f},{n[1]:+.3f},{n[2]:+.3f}) "
              f"base=({b[0]:+.1f},{b[1]:+.1f},{b[2]:+.1f}) flags={s.poly_flags:#x}")
    for i, n in enumerate(model.nodes):
        ring = [tuple(round(c, 2) for c in model.points[model.verts[n.i_vert_pool + k].i_vertex])
                for k in range(n.num_vertices)]
        print(f" node {i:2} surf={n.i_surf:2} iF={n.i_front:3} iB={n.i_back:3} iP={n.i_plane:3} "
              f"iZ={list(n.i_leaf) if hasattr(n,'i_leaf') else '?'} nv={n.num_vertices} "
              f"flags={n.node_flags:#04x} plane=({n.plane[0]:+.2f},{n.plane[1]:+.2f},{n.plane[2]:+.2f},"
              f"{n.plane[3]:+.1f})")
        print(f"        ring={ring}")


dump(nm, "native", lambda ia: names[ia] if 0 <= ia < len(names) else ia)
dump(em, "editor", lambda ia: pkg.name_of_ref(ia))
