#!/usr/bin/env python3
r"""EDITOR PRE-bspOptGeom TREE ORACLE — dump Model->Nodes at bspOptGeom ENTRY (0x10036870).

The fair node-for-node counterpart to native's `UEDCTL_BSPCSG_PREOPT_NODES` dump: both sides are
post-refresh, post-Pass-D, PRE-weld, in engine child convention.  This disambiguates a partitioner
(SplitPolyList) ring-vertex gap from a bspOptGeom weld gap — is the editor's SplitPolyList already
producing fat fragments (node nv > native's) BEFORE the T-junction weld, or does the weld create
the fatness?

Loads the golden `.dx` directly (default Test_Castle.dx) + MAP REBUILD, same as bspopt_pool_oracle.
FBspNode is 0x40 bytes: plane +0x00 (4 float), iSurf +0x1c, iBack +0x20, iFront +0x24, iPlane +0x28,
iVertPool +0x18, NumVertices +0x36 (byte), NodeFlags +0x37 (byte).  Model->Nodes.Data=+0x58,
Nodes.Num=+0x5c.

Usage:  editor_preopt_nodes.py [golden.dx]  ->  logs/editor-preopt-nodes.log
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
ENTRY = 0x10036870

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
break *{entry:#x}
commands
silent
set $model = *(unsigned int *)($esp + 4)
set $nodes = *(unsigned int *)($model + 0x58)
set $num = *(int *)($model + 0x5c)
printf "TREEBEGIN num=%d\n", $num
set $i = 0
while $i < $num
  set $n = $nodes + $i * 0x40
  printf "PN node=%d plane=(%.5f,%.5f,%.5f,%.5f) iF=%d iB=%d iP=%d isurf=%d ivp=%d nv=%d\n", $i, *(float *)($n), *(float *)($n+4), *(float *)($n+8), *(float *)($n+0xc), *(int *)($n+0x24), *(int *)($n+0x20), *(int *)($n+0x28), *(int *)($n+0x1c), *(int *)($n+0x18), *(unsigned char *)($n+0x36)
  set $i = $i + 1
end
printf "TREEEND\n"
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
    container = "uned-preoptnodes"
    O.stop_dbg_editor(container, state_dir)
    print(f"starting {container} ... golden={GOLDEN}")
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "cp", str(GOLDEN), f"{container}:/work/golden.dx"], check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/pn.gdb"],
                       input=GDB.format(pid=pid, entry=ENTRY), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/pn.gdb > /tmp/pn.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/pn.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        print("attached; MAP REBUILD ...")
        drv.exec("MAP REBUILD")
        for _ in range(300):
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c TREEEND /tmp/pn.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                break
            time.sleep(1.0)
        out = HERE / "logs" / "editor-preopt-nodes.log"
        subprocess.run(["docker", "cp", f"{container}:/tmp/pn.log", str(out)], check=True)
        nd = subprocess.run(["bash", "-c", f"grep -c '^PN ' {out}"], capture_output=True, text=True).stdout.strip()
        print(f"wrote {out} ({nd} PN lines)")
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    main()
