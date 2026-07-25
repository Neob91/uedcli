#!/usr/bin/env python3
r"""EDITOR bspOptGeom INSERTER ORACLE — log every T-junction weld (0x31920) during MAP REBUILD.

Ground truth for the pass-1 T-junction detector: which (node, edge, point) the editor actually
inserts.  Native's detector fires ~22 times; the editor ~2600.  Each hit dumps the node's PLANE and
the POINT's world coords so it can be matched against native's (identical-plane) tree node-for-node.

Inserter 0x10031920 signature (disasm-verified): at ENTRY (pre-`push ebp`),
  [esp+4]=Model  [esp+0xc]=iNode  [esp+0x10]=edge  [esp+0x14]=point
UModel: Nodes.Data=+0x58 (stride 0x40, plane@+0x00 = 4 f32), Points.Data=+0x88 (stride 0xc = 3 f32).

Usage:  bspopt_insert_oracle.py [golden.dx]  ->  logs/bspopt-insert.log
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
VA = 0x10031920

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
set $model = *(unsigned int *)($esp + 4)
set $inode = *(int *)($esp + 0xc)
set $edge = *(int *)($esp + 0x10)
set $point = *(int *)($esp + 0x14)
set $nd = *(unsigned int *)($model + 0x58) + $inode * 0x40
set $pd = *(unsigned int *)($model + 0x88) + $point * 0xc
printf "INS node=%d edge=%d point=%d plane=%.4f,%.4f,%.4f,%.4f P=%.4f,%.4f,%.4f nv=%d\n", $inode, $edge, $point, *(float *)($nd), *(float *)($nd+4), *(float *)($nd+8), *(float *)($nd+0xc), *(float *)($pd), *(float *)($pd+4), *(float *)($pd+8), *(unsigned char *)($nd+0x36)
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def main():
    O._ensure_dbg_image()
    mounts = O._composed_mounts(subset_diff.CASTLE_PROJECT)
    state_dir = O._state_dir(subset_diff.CASTLE_PROJECT)
    container = "uned-insdump"
    O.stop_dbg_editor(container, state_dir)
    print(f"starting {container} ... golden={GOLDEN}")
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "cp", str(GOLDEN), f"{container}:/work/golden.dx"], check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/ins.gdb"],
                       input=GDB.format(pid=pid, va=VA), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/ins.gdb > /tmp/ins.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/ins.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        print("attached; MAP REBUILD ...")
        drv.exec("MAP REBUILD")
        # Wait for INS-line quiescence (rebuild done): stable count for 8s.
        last, stable_since = -1, time.monotonic()
        for _ in range(600):
            c = subprocess.run(["docker", "exec", container, "bash", "-c",
                                "grep -c '^INS ' /tmp/ins.log 2>/dev/null || true"],
                               capture_output=True, text=True).stdout.strip()
            c = int(c) if c.isdigit() else 0
            now = time.monotonic()
            if c != last:
                last, stable_since = c, now
            elif c > 0 and now - stable_since >= 8:
                break
            time.sleep(1.0)
        out = HERE / "logs" / "bspopt-insert.log"
        subprocess.run(["docker", "cp", f"{container}:/tmp/ins.log", str(out)], check=True)
        nd = subprocess.run(["bash", "-c", f"grep -c '^INS ' {out}"], capture_output=True, text=True).stdout.strip()
        print(f"wrote {out} ({nd} INS lines)")
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    main()
