#!/usr/bin/env python3
r"""EDITOR bspBuild-ENTRY ORACLE — dump `Model->Polys` (the UPolys Element array) in the exact
order `SplitPolyList`/`FindBestSplit` consumes it, i.e. the true repartition-input face ORDER.

WHY.  Native's pre-repartition SOUP is byte-EXACT vs the editor golden as a MULTISET (`soup_cmp.py`
0/0), yet the FINAL repartitioned tree diverges from node[0] (`node_diff.py` prefix 0/1156, native
over-splits 1251 vs 1156).  Since the repartition INPUT content is identical, the divergence must be
the ORDER in which `bspBuild`→`SplitPolyList`→`FindBestSplit` sees those faces — a different order
picks different partition planes and different tie-breaks.  The saved golden `.dx` `Model.Polys` is
NOT a valid oracle for this order (later passes may perturb it), so we must observe the array at the
exact instant `bspBuild` is entered.

WHERE (decoded from Editor.dll).  `bspRepartition` (`0x49fc0`) issues, in order, four vtable calls:
`bspBuildFPolys` (`[edx+0x20c]`), `bspMergeCoplanars` (`[edx+0x210]`), **`bspBuild` (`[edx+0x1fc]`
at VA 0x1004a041)**, `bspRefresh` (`[edx+0x200]`).  At the `bspBuild` CALL site the args are already
pushed: `[esp]=Model`.  `bspBuild` (`0x35ef0`) reads the poly list as `Model->Polys` (UModel+0x54,
a UPolys*), whose `Element` TArray is `Data=UPolys+0x28`, `Num=UPolys+0x2c`, `sizeof(FPoly)=0x1d8`
(`imul ...,0x1d8`).  It then builds a temporary pointer array over the elements FILTERING OUT
`NumVertices==0` (`cmp [fp+0x1c0],0; je skip`) and hands THAT (in element order) to `SplitPolyList`.
So the SplitPolyList input order == `Element[0..Num)` with `NumVertices>0`, in array order.

FPoly fields (verified via bspAddNode / bspBuild disasm): Base=+0x00, Normal=+0x0c, Vertex[0]=+0x30
(right after TextureU +0x18 / TextureV +0x24), NumVertices=+0x1c0, iLink=+0x1c4.

HOW.  Same container/gdb machinery as `editor_struct.py`: MAP LOAD the golden{N}.dx subset (the same
N brushes native builds), attach gdb with a breakpoint at 0x1004a041, MAP REBUILD, at the hit walk
`Model->Polys->Element` and print one `POLY` line per element (index, nv, iLink, normal, base,
vert0), then detach.  One hit = the whole structural repartition (semisolid brushes are incremental,
never repartitioned — §80).

Usage:  editor_polys_oracle.py [N=33]   ->  logs/editor-polys-N.log
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
HERE = HARNESS / "editor-tree-oracle"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HERE))

import editor_tree_oracle as O  # noqa: E402
from uedcli.driver import Driver, to_z_path  # noqa: E402
import subset_diff  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 33
# bspBuild call site inside bspRepartition (0x49fc0): `call [edx+0x1fc]`. [esp]=Model.
VA = 0x1004A041

GDB = r"""
set pagination off
set confirm off
set height 0
set width 0
attach {pid}
handle SIGSEGV nostop noprint pass
handle SIGUSR1 nostop noprint pass
handle SIGUSR2 nostop noprint pass
handle SIGPIPE nostop noprint pass
break *{va:#x}
commands
silent
set $model = *(unsigned int *)($esp)
set $polys = *(unsigned int *)($model + 0x54)
set $data = *(unsigned int *)($polys + 0x28)
set $num = *(int *)($polys + 0x2c)
printf "POLYSBEGIN model=%#x polys=%#x num=%d\n", $model, $polys, $num
set $i = 0
while $i < $num
  set $fpol = $data + $i * 0x1d8
  set $nv = *(int *)($fpol + 0x1c0)
  printf "POLY %d nv=%d ilink=%d N=%.5f,%.5f,%.5f B=%.5f,%.5f,%.5f\n", $i, $nv, *(int *)($fpol + 0x1c4), *(float *)($fpol + 0xc), *(float *)($fpol + 0x10), *(float *)($fpol + 0x14), *(float *)($fpol), *(float *)($fpol + 4), *(float *)($fpol + 8)
  set $k = 0
  while $k < $nv
    set $vp = $fpol + 0x30 + $k * 0xc
    printf "VERT %.5f,%.5f,%.5f\n", *(float *)($vp), *(float *)($vp + 4), *(float *)($vp + 8)
    set $k = $k + 1
  end
  set $i = $i + 1
end
printf "POLYSEND\n"
detach
quit
end
printf "ORACLE_ATTACHED\n"
continue
"""


def main():
    O._ensure_dbg_image()
    golden = subset_diff.build_editor_subset(N)
    mounts = O._composed_mounts(subset_diff.CASTLE_PROJECT)
    state_dir = O._state_dir(subset_diff.CASTLE_PROJECT)
    container = f"uned-polys-n{N}"
    O.stop_dbg_editor(container, state_dir)
    print(f"starting {container} ...")
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "cp", str(golden), f"{container}:/work/golden.dx"], check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/ep.gdb"],
                       input=GDB.format(pid=pid, va=VA), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/ep.gdb > /tmp/ep.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/ep.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        print("attached; MAP REBUILD ...")
        drv.exec("MAP REBUILD")
        for _ in range(300):
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c POLYSEND /tmp/ep.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                break
            time.sleep(1.0)
        out = HERE / "logs" / f"editor-polys-{N}.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["docker", "cp", f"{container}:/tmp/ep.log", str(out)], check=True)
        nd = subprocess.run(["bash", "-c", f"grep -c '^POLY ' {out}"],
                            capture_output=True, text=True).stdout.strip()
        print(f"wrote {out} ({nd} POLY lines)")
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    main()
