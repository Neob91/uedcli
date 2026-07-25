#!/usr/bin/env python3
r"""EDITOR bspBuild-ENTRY SOUP ORACLE (direct golden load) — dump Model->Polys at the exact instant
`bspBuild` is entered, i.e. the REAL face list `SplitPolyList`/`FindBestSplit` repartitions.

Unlike `editor_polys_oracle.py` this loads a given golden `.dx` DIRECTLY (default Test_Castle.dx),
sidestepping `subset_diff.build_editor_subset` (whose `apply.run_materialize` signature the config
session changed).  MAP LOAD + MAP REBUILD reproduces the same csgRebuild.

bspBuild call site inside bspRepartition (0x49fc0): `call [edx+0x1fc]` @ 0x1004a041, [esp]=Model.
Model->Polys @ +0x54 (UPolys*), Element TArray Data=+0x28 Num=+0x2c, sizeof(FPoly)=0x1d8,
NumVertices=+0x1c0.  Dumps one POLY line (idx, nv) per element.

Usage:  bspbuild_soup_oracle.py [golden.dx]  ->  logs/bspbuild-soup.log
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl")
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
HERE = HARNESS / "editor-tree-oracle"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HERE))

import editor_tree_oracle as O  # noqa: E402
from uedctl.driver import Driver, to_z_path  # noqa: E402
import subset_diff  # noqa: E402

GOLDEN = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx")
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
printf "POLYSBEGIN num=%d\n", $num
set $i = 0
set $tv = 0
while $i < $num
  set $fpol = $data + $i * 0x1d8
  set $nv = *(int *)($fpol + 0x1c0)
  printf "POLY %d nv=%d\n", $i, $nv
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
    mounts = O._composed_mounts(subset_diff.CASTLE_PROJECT)
    state_dir = O._state_dir(subset_diff.CASTLE_PROJECT)
    container = "uned-soupdump"
    O.stop_dbg_editor(container, state_dir)
    print(f"starting {container} ... golden={GOLDEN}")
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "cp", str(GOLDEN), f"{container}:/work/golden.dx"], check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/bs.gdb"],
                       input=GDB.format(pid=pid, va=VA), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/bs.gdb > /tmp/bs.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/bs.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        print("attached; MAP REBUILD ...")
        drv.exec("MAP REBUILD")
        for _ in range(300):
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c POLYSEND /tmp/bs.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                break
            time.sleep(1.0)
        out = HERE / "logs" / "bspbuild-soup.log"
        subprocess.run(["docker", "cp", f"{container}:/tmp/bs.log", str(out)], check=True)
        nd = subprocess.run(["bash", "-c", f"grep -c '^POLY ' {out}"], capture_output=True, text=True).stdout.strip()
        print(f"wrote {out} ({nd} POLY lines)")
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    main()
