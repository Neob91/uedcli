#!/usr/bin/env python3
"""Bit-level check for one or few isolated OceanLab Lab brushes: native vs the context-isolated
live-editor golden built by `oceanlab_isolate_golden.py`. Adapted from
`dev/docs/spikes/2026-09-01-oceanlab-overbuild/harness/oceanlab_isolate_check.py`, retargeted at
this round's worktree and extended to dump per-poly PLANE bits (the transformed Normal + plane
distance) for the focus brush, not just surf-count attribution -- this round's question is whether
native's rotated-brush vertex/normal transform is bit-exact with the real editor, not the surf-merge
count the prior round answered.

Usage: .venv/bin/python oceanlab_isolate_check.py Brush1081 [Brush128 ...]
"""
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/workspace/uedcli/.claude/worktrees/agent-ad11af2d5c5e7d2ab")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

CACHE = ROOT / "_scratch/uedcli-parity-cache/4e3757c3f3b2144f3750084db83cdbbc8bd4412047aadffa17c0494f4fa51a39"
TRUNK = CACHE / "trunk/maps/14_oceanlab_lab"
os.environ.setdefault("UEDCLI_PROJECT", str(CACHE / "trunk"))

from uedcli import trunk, builders                 # noqa: E402
from uedcli.native import brush_marshal as BM       # noqa: E402
from uedcli.native import umodel as UM              # noqa: E402
import uedcli_native                                # noqa: E402
import utexture_decode as UT                        # noqa: E402


def parse_golden(path):
    pkg = UT.load_package(str(path))
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    m = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])
    return pkg, m


def context_brushes(center):
    cx, cy, cz = center
    shell = builders.make_brush_actor("CtxShell", builders.cube(16000, 16000, 16000),
                                      location=(cx, cy, cz), csg="add")
    room = builders.make_brush_actor("CtxRoom", builders.cube(4000, 4000, 4000),
                                     location=(cx, cy, cz), csg="subtract")
    return [shell, room]


def dump_focus_polys(label, model, actor_index, name_of_ref):
    surfs = [(i, s) for i, s in enumerate(model.surfs) if name_of_ref(s.i_actor) == label]
    print(f"  {label}: {len(surfs)} surf(s)")
    for i, s in surfs:
        n = (s.v_normal.x, s.v_normal.y, s.v_normal.z) if hasattr(s, "v_normal") else None
        print(f"    surf[{i}] plane=({s.plane_x:.9g},{s.plane_y:.9g},{s.plane_z:.9g},{s.plane_w:.9g})"
              if hasattr(s, "plane_x") else f"    surf[{i}] {s}")


def main():
    names = sys.argv[1:] or ["Brush1081"]
    level, _ranks = trunk.read_level(TRUNK)
    focus = [level.actors[n] for n in names]
    loc = focus[0].location
    ctx = context_brushes((float(loc[0]), float(loc[1]), float(loc[2])))
    all_names = ["CtxShell", "CtxRoom"] + names
    all_actors = {a.name: a for a in ctx}
    all_actors.update({n: level.actors[n] for n in names})

    ins = [BM._build_brush_input(n, all_actors[n]) for n in all_names]
    built = uedcli_native.build_geometry_bspcsg(ins)
    nbody = uedcli_native.serialize_model(built)
    nm = UM.parse_model_body(nbody, 0, len(nbody))

    golden_path = ROOT / f"_scratch/oceanlab-isolate/golden_{'_'.join(names)}.dx"
    epkg, em = parse_golden(golden_path)

    print(f"context-isolated {names}: native nodes={len(nm.nodes)} surfs={len(nm.surfs)} "
          f"leaves={len(nm.leaves)}  editor nodes={len(em.nodes)} surfs={len(em.surfs)} "
          f"leaves={len(em.leaves)}")

    nc = Counter(all_names[s.i_actor] if 0 <= s.i_actor < len(all_names) else s.i_actor
                 for s in nm.surfs)
    ec = Counter(epkg.name_of_ref(s.i_actor) for s in em.surfs)
    for n in all_names:
        print(f"  {n}: native={nc.get(n,0)} editor={ec.get(n,0)}")

    def fmt_vec(v):
        x, y, z = v
        return f"{x!r},{y!r},{z!r}  bits={float(x).hex()},{float(y).hex()},{float(z).hex()}"

    print("\n--- native raw vectors (Normal pool) ---")
    for i, v in enumerate(nm.vectors):
        print(f"  n_vec[{i}] = {fmt_vec(v)}")

    print("\n--- editor raw vectors (Normal pool) ---")
    for i, v in enumerate(em.vectors):
        print(f"  e_vec[{i}] = {fmt_vec(v)}")

    print("\n--- native points pool ---")
    for i, v in enumerate(nm.points):
        print(f"  n_pt[{i}] = {fmt_vec(v)}")

    print("\n--- editor points pool ---")
    for i, v in enumerate(em.points):
        print(f"  e_pt[{i}] = {fmt_vec(v)}")

    print("\n--- native surfs (all) ---")
    for i, s in enumerate(nm.surfs):
        actor_label = all_names[s.i_actor] if 0 <= s.i_actor < len(all_names) else s.i_actor
        print(f"  n_surf[{i}] actor={actor_label} v_normal={s.v_normal} poly_flags={s.poly_flags}")

    print("\n--- editor surfs (all) ---")
    for i, s in enumerate(em.surfs):
        actor_label = epkg.name_of_ref(s.i_actor)
        print(f"  e_surf[{i}] actor={actor_label} v_normal={s.v_normal} poly_flags={s.poly_flags}")


if __name__ == "__main__":
    raise SystemExit(main())
