#!/usr/bin/env python3
"""Decisive test: build the fc08 12-brush set EXCLUDING Brush586 (the leading CsgOper-absent /
CSG_Active brush) -- brushes 2..13 in CSG order (Brush1,3,4,5,6,7,8,9,10,22,23,47) -- both native
and live-editor, to see whether the -12 node / -4 leaf divergence found at n=13 (WITH Brush586)
persists or disappears. If it disappears, Brush586's CSG_Active mishandling (native silently
defaults it to CSG_Add) is implicated as the real driver, not Brush47/the diffuse repartition
class. Per `unrealed/quirks.md` ("Unreal's world is solid by default"), a Subtract-heavy brush set
with no enclosing Add is still meaningful -- it carves the infinite default-solid world directly.
"""
import sys
from pathlib import Path

WORKTREE = Path("/workspace/uedcli/.claude/worktrees/nsfhq04-residual-investigation")
sys.path.insert(0, str(WORKTREE))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

import os
os.environ["UEDCLI_PROJECT"] = "/workspace/uedcli/_scratch/fc08-structural-only"

from uedcli import trunk                          # noqa: E402
from uedcli.native import brush_marshal as BM      # noqa: E402
from uedcli.native import umodel as UM             # noqa: E402
import uedcli_native                               # noqa: E402
import utexture_decode as UT                       # noqa: E402
from spike_classindex import class_index           # noqa: E402
import subprocess

ROOT = Path("/workspace/uedcli")
SRC_TRUNK = ROOT / "_scratch/fc08-structural-only/maps/freeclinic08"
BUILD_SCRIPT = WORKTREE / "dev/docs/spikes/2026-07-15-native-materialize/harness/build_ued_golden.py"
PYEXE = str(WORKTREE / ".venv/bin/python")
DST_ROOT = ROOT / "_scratch/fc08-n12-noactive"


def main():
    level, ranks = trunk.read_level(SRC_TRUNK)
    ci = class_index()
    brush_names = [n for n in level.order
                   if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    names12 = brush_names[1:13]  # skip Brush586 (index 0)
    print("12 brushes (excl Brush586):", names12)

    # native
    ins = [BM._build_brush_input(nm, level.actors[nm]) for nm in names12]
    built = uedcli_native.build_geometry_bspcsg(ins)
    nbody = uedcli_native.serialize_model(built)
    nm = UM.parse_model_body(nbody, 0, len(nbody))
    print(f"native: nodes={len(nm.nodes)} surfs={len(nm.surfs)} leaves={len(nm.leaves)}")

    # editor: write trunk with just these 12 brushes + all non-brush actors
    other_names = [n for n in level.order if n not in set(brush_names)]
    keep = set(other_names) | set(names12)
    new_order = [n for n in level.order if n in keep]
    dst = DST_ROOT / "maps/freeclinic08"
    import shutil
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    new_level = type(level)(actors={k: v for k, v in level.actors.items() if k in keep}, order=new_order)
    new_ranks = {k: v for k, v in ranks.items() if k in keep}
    trunk.write_level(dst, new_level, new_ranks)
    (dst.parent.parent / "uedcli.toml").write_text('game = "deusex"\nmaps = "maps"\n')

    golden = dst.parent.parent / "golden_n12noactive.dx"
    cmd = [PYEXE, str(BUILD_SCRIPT), "--trunk", str(dst), "--out", str(golden),
           "--world-only", "--no-light", "--no-obj-load", "--overwrite"]
    print("building editor golden:", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=str(ROOT))
    if r.returncode != 0:
        raise RuntimeError(f"build failed rc={r.returncode}")

    pkg = UT.load_package(str(golden))
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    gm = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])
    print(f"editor: nodes={len(gm.nodes)} surfs={len(gm.surfs)} leaves={len(gm.leaves)}")
    print(f"DELTA (native-editor): nodes={len(nm.nodes)-len(gm.nodes):+d} "
          f"surfs={len(nm.surfs)-len(gm.surfs):+d} leaves={len(nm.leaves)-len(gm.leaves):+d}")


if __name__ == "__main__":
    raise SystemExit(main())
