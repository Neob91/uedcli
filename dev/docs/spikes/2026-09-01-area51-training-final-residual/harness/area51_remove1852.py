#!/usr/bin/env python3
"""Decisive test: rebuild the FULL Area51 Entrance world-CSG brush set with `Brush1852` removed
(the first-diverging brush the prefix binary search localized -- n=506=Brush1851 exact, n=507
adding Brush1852 diverges nodes=+48/leaves=-18/surfs=+0), both native in-process and a fresh
live-editor world-only rebuild, same pattern as fc08_n12_noactive_search.py's Brush586-removal
decisive test. Quantifies how much of the full-level +85 nodes/+51 leaves residual this one brush
explains.
"""
import os
import sys
from pathlib import Path

WORKTREE = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-fresh")
sys.path.insert(0, str(WORKTREE))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

TRUNK = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-check/_scratch/uedcli-parity-cache/"
             "65b9261c371bdf8573cb7bf9128a3f6664b14d2ac360ef6fbfd4a0d292986ece/trunk/maps/15_area51_entrance")
PROJECT_ENV = TRUNK.parent.parent
os.environ["UEDCLI_PROJECT"] = str(PROJECT_ENV)

from uedcli import trunk as trunk_mod              # noqa: E402
from uedcli.native import brush_marshal as BM      # noqa: E402
from uedcli.native import umodel as UM             # noqa: E402
import uedcli_native                               # noqa: E402
import utexture_decode as UT                       # noqa: E402
from spike_classindex import class_index           # noqa: E402

DROP = "Brush1852"
OUT_ROOT = WORKTREE / "_scratch/a51_no1852"
BUILD_SCRIPT = WORKTREE / "dev/docs/spikes/2026-07-15-native-materialize/harness/build_ued_golden.py"


def parse_golden(path):
    pkg = UT.load_package(str(path))
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    return UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])


def main():
    level, ranks = trunk_mod.read_level(TRUNK)
    ci = class_index()
    brush_names = [n for n in level.order
                   if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    other_names = [n for n in level.order if n not in set(brush_names)]
    assert DROP in brush_names, f"{DROP} not found in world-csg brush set"
    kept_brush_names = [n for n in brush_names if n != DROP]
    print(f"total world-csg brushes: {len(brush_names)}; dropping {DROP}; kept {len(kept_brush_names)}")

    # Native: build with Brush1852 removed.
    ins = [BM._build_brush_input(n, level.actors[n]) for n in kept_brush_names]
    built = uedcli_native.build_geometry_bspcsg(ins)
    nbody = uedcli_native.serialize_model(built)
    nm = UM.parse_model_body(nbody, 0, len(nbody))
    print(f"native (no {DROP}): nodes={len(nm.nodes)} surfs={len(nm.surfs)} leaves={len(nm.leaves)}")

    # Editor: write a trunk with Brush1852 removed, world-only rebuild.
    keep = set(other_names) | set(kept_brush_names)
    new_order = [n for n in level.order if n in keep]
    dst = OUT_ROOT / f"maps/15_area51_entrance"
    dst.parent.mkdir(parents=True, exist_ok=True)
    new_level = type(level)(actors={k: v for k, v in level.actors.items() if k in keep}, order=new_order)
    new_ranks = {k: v for k, v in ranks.items() if k in keep}
    trunk_mod.write_level(dst, new_level, new_ranks)
    (dst.parent.parent / "uedcli.toml").write_text('game = "deusex"\nmaps = "maps"\n')

    golden = dst.parent.parent / "golden_no1852.dx"
    import subprocess
    cmd = [str(WORKTREE / ".venv/bin/python"), str(BUILD_SCRIPT), "--trunk", str(dst),
           "--out", str(golden), "--world-only", "--no-light", "--no-obj-load", "--overwrite"]
    print("building editor golden:", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd="/workspace/uedcli")
    if r.returncode != 0:
        raise RuntimeError(f"build_ued_golden.py failed rc={r.returncode}")
    em = parse_golden(golden)
    print(f"editor (no {DROP}): nodes={len(em.nodes)} surfs={len(em.surfs)} leaves={len(em.leaves)}")

    d_nodes = len(nm.nodes) - len(em.nodes)
    d_surfs = len(nm.surfs) - len(em.surfs)
    d_leaves = len(nm.leaves) - len(em.leaves)
    print(f"\nRESULT (no {DROP}): d_nodes={d_nodes:+d} d_surfs={d_surfs:+d} d_leaves={d_leaves:+d}")
    print("compare to WITH Brush1852 (full level, already measured): d_nodes=+85 d_surfs=+0 d_leaves=+51")


if __name__ == "__main__":
    raise SystemExit(main())
