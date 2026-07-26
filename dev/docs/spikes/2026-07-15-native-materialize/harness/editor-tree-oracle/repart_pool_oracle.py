#!/usr/bin/env python3
r"""EDITOR POOL ORACLE at bspRepartition ENTRY vs bspOptGeom ENTRY.

Pins the editor's Points/Verts/Surfs/Vectors pool at bspRepartition ENTRY (0x49fc0) — the
CSG-phase pool BEFORE EmptyModel(0,0) (which keeps Points/Vectors/Surfs, clears Nodes/Verts) —
so native's uncleared CSG pool (3447) can be compared to the editor's real CSG pool.  Also
re-dumps at bspOptGeom ENTRY (0x36870) for the growth delta.

UModel offsets: Nodes.Num=+0x5c, Verts.Num=+0x6c, Vectors.Num=+0x7c, Points.Num=+0x8c,
Surfs.Num=+0x9c, NumSharedSides=+0xfc.

Usage:  repart_pool_oracle.py [golden.dx]  ->  logs/repart-pool.log
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

GOLDEN = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx")

DUMP = (
    r'printf "%s nodes=%d verts=%d vectors=%d points=%d surfs=%d nss=%d\n", "{lbl}", '
    r'*(int *)($m + 0x5c), *(int *)($m + 0x6c), *(int *)($m + 0x7c), '
    r'*(int *)($m + 0x8c), *(int *)($m + 0x9c), *(int *)($m + 0xfc)'
)

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
break *0x10049fc0
commands
silent
set $m = *(unsigned int *)($esp + 4)
""" + DUMP.format(lbl="REPART") + r"""
continue
end
break *0x10036870
commands
silent
set $m = *(unsigned int *)($esp + 4)
""" + DUMP.format(lbl="OPT") + r"""
printf "POOLEND\n"
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def main():
    O._ensure_dbg_image()
    mounts = O._composed_mounts(subset_diff.CASTLE_PROJECT)
    state_dir = O._state_dir(subset_diff.CASTLE_PROJECT)
    container = "uned-repartpool"
    O.stop_dbg_editor(container, state_dir)
    print(f"starting {container} ... golden={GOLDEN}")
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "cp", str(GOLDEN), f"{container}:/work/golden.dx"], check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/rp.gdb"],
                       input=GDB.format(pid=pid), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/rp.gdb > /tmp/rp.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/rp.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        print("attached; MAP REBUILD ...")
        drv.exec("MAP REBUILD")
        for _ in range(300):
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c POOLEND /tmp/rp.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                break
            time.sleep(1.0)
        out = HERE / "logs" / "repart-pool.log"
        subprocess.run(["docker", "cp", f"{container}:/tmp/rp.log", str(out)], check=True)
        print(f"wrote {out}")
        print(subprocess.run(["bash", "-c", f"grep -E 'REPART|OPT' {out}"],
                             capture_output=True, text=True).stdout)
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    main()
