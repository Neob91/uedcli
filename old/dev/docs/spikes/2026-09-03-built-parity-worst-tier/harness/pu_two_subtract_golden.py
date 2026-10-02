#!/usr/bin/env python3
"""Discriminator for the Paris Underground 2-brush divergence: rebuild the SAME pair live with
`Brush1246`'s absent `CsgOper` replaced by explicit `CSG_Subtract`.

As authored (CsgOper absent = Active): editor 16 nodes/12 surfs/6 leaves, native 14/11/2, and
native builds Active and explicit-Subtract identically (14/11/2). So:
  - editor still 16/12/6 with the explicit Subtract -> general subtract-overlap gap (not Active);
  - editor 14/11/2 -> the editor's Active differs from Subtract in brush interactions, refining
    the `CsgOper::Active` model (dispatch-identical but not outcome-identical).
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import prefix_search_lib as PSL  # noqa: E402
from uedcli.native import umodel as UM  # noqa: E402
import utexture_decode as UT  # noqa: E402

TRUNK = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-check/_scratch/uedcli-parity-cache"
             "/bdf66b5dc02df008a53f5018b5aeab950cf13481c2a49bd0f683dd714429c718/trunk")


def main():
    wt = HERE.parents[4]
    root = wt / "_scratch/pu-prefix-sub2"
    ps = PSL.PrefixSearch("11_paris_underground", TRUNK / "maps/11_paris_underground",
                          root, TRUNK)
    dst, proj = ps._write_prefix_trunk(2)
    t3d = dst / "actors/Brush1246/actor.t3d"
    text = t3d.read_text()
    assert "CsgOper" not in text
    t3d.write_text(text.replace("    Tag=Brush\n", "    CsgOper=CSG_Subtract\n    Tag=Brush\n"))
    golden = proj / "golden_sub2.dx"
    cmd = [PSL.PYEXE, str(PSL.BUILD_SCRIPT), "--trunk", str(dst), "--out", str(golden),
           "--world-only", "--no-light", "--no-obj-load", "--overwrite"]
    print("building:", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=str(PSL.WORKTREE))
    if r.returncode != 0:
        raise SystemExit(f"golden build failed rc={r.returncode}")
    m = ps._parse_golden(golden)
    print(f"editor [Subtract,Subtract]: nodes={len(m.nodes)} surfs={len(m.surfs)} "
          f"leaves={len(m.leaves)}  (Active variant was 16/12/6; native is 14/11/2 either way)")


if __name__ == "__main__":
    main()
