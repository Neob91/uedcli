#!/usr/bin/env python3
"""Garage 2-brush minimal case, live: editor golden for [Brush20, Brush21] only (all non-brush
actors kept, every other brush dropped), vs native's 58/32/12 (`wg_localize.py pairs`)."""
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import prefix_search_lib as PSL  # noqa: E402
from uedcli import trunk as TR  # noqa: E402

CACHE = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-check/_scratch/uedcli-parity-cache"
             "/21326d2b4c841cc3e3e2424699c2f5f07f1b9daa41eefbd4efa00bf9bf30af1e/trunk")
KEEP_BRUSHES = ["Brush20", "Brush21"]


def main():
    wt = HERE.parents[4]
    ps = PSL.PrefixSearch("06_hongkong_wanchai_garage", CACHE / "maps/06_hongkong_wanchai_garage",
                          wt / "_scratch/wg-minimal", CACHE)
    keep = set(ps.other_names) | set(KEEP_BRUSHES)
    new_order = [nm for nm in ps.level.order if nm in keep]
    dst = ps.prefix_root / "pair" / "maps/06_hongkong_wanchai_garage"
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    new_level = type(ps.level)(
        actors={k: v for k, v in ps.level.actors.items() if k in keep}, order=new_order)
    TR.write_level(dst, new_level, {k: v for k, v in ps.ranks.items() if k in keep})
    proj = dst.parent.parent
    (proj / "uedcli.toml").write_text('game = "deusex"\nmaps = "maps"\n')
    golden = proj / "golden_pair.dx"
    if not golden.exists() or "--force" in sys.argv:
        ps._yield_editor_slot()
        cmd = [PSL.PYEXE, str(PSL.BUILD_SCRIPT), "--trunk", str(dst), "--out", str(golden),
               "--world-only", "--no-light", "--no-obj-load", "--overwrite"]
        print("building:", " ".join(cmd), flush=True)
        r = subprocess.run(cmd, cwd=str(PSL.WORKTREE))
        if r.returncode != 0:
            raise SystemExit(f"golden build failed rc={r.returncode}")
    m = ps._parse_golden(golden)
    print(f"editor [Brush20, Brush21]: nodes={len(m.nodes)} surfs={len(m.surfs)} "
          f"leaves={len(m.leaves)}  (native: 58/32/12)")


if __name__ == "__main__":
    main()
