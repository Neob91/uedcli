#!/usr/bin/env python3
r"""EDITOR bspOptGeom POOL-COUNT ORACLE — dump Model pool sizes at bspOptGeom ENTRY vs EXIT.

Decides the load-bearing question for the vert/point/vector byte-parity gap: is native's shortfall
in the T-junction DETECTOR (pass 1 under-fires on an identical tree) or UPSTREAM (native's
pre-bspOptGeom tree/pool already has fewer points/verts than the editor's)?

Breakpoints (Editor.dll @ ImageBase 0x10000000, loaded un-relocated):
  * bspOptGeom ENTRY  0x10036870 — first insn (push ebp, prologue not run) → Model=[esp+4].
  * bspOptGeom EXIT   0x10036c32 — the `ret 4`.  Model is saved into a gdb convenience var at
    entry ($optmodel) and re-read here (one csgRebuild = one bspOptGeom, no recursion).

UModel in-memory field offsets (decode §42.1): Nodes.Num=+0x5c, Verts.Num=+0x6c, Points.Num=+0x8c,
NumSharedSides=+0xfc.  Vectors/Surfs .Num offsets are unknown — we dump a scan of candidate TArray
Num slots and identify them by matching the golden's known final counts (Vectors=26, Surfs=485).

Usage:  bspopt_pool_oracle.py [/path/to/golden.dx=Test_Castle.dx]   ->  logs/bspopt-pool.log
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
ENTRY = 0x10036870
EXIT = 0x10036C32

# Dump a labelled row of pool counts for the Model in $m.  Scan candidate TArray Num slots so
# Vectors/Surfs can be pinned by matching known golden counts.
DUMP = (
    r'printf "%s nodes=%d verts=%d points=%d nss=%d '
    r'| c64=%d c6c=%d c74=%d c7c=%d c80=%d c84=%d c8c=%d c94=%d c9c=%d ca4=%d\n", '
    r'"{lbl}", '
    r'*(int *)($m + 0x5c), *(int *)($m + 0x6c), *(int *)($m + 0x8c), *(int *)($m + 0xfc), '
    r'*(int *)($m + 0x64), *(int *)($m + 0x6c), *(int *)($m + 0x74), *(int *)($m + 0x7c), '
    r'*(int *)($m + 0x80), *(int *)($m + 0x84), *(int *)($m + 0x8c), *(int *)($m + 0x94), '
    r'*(int *)($m + 0x9c), *(int *)($m + 0xa4)'
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
break *{entry:#x}
commands
silent
set $optmodel = *(unsigned int *)($esp + 4)
set $m = $optmodel
""" + DUMP.format(lbl="PRE") + r"""
continue
end
break *{exit:#x}
commands
silent
set $m = $optmodel
""" + DUMP.format(lbl="POST") + r"""
printf "POOLEND\n"
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
    container = "uned-bspoptpool"
    O.stop_dbg_editor(container, state_dir)
    print(f"starting {container} ... golden={GOLDEN}")
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "cp", str(GOLDEN), f"{container}:/work/golden.dx"], check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/bp.gdb"],
                       input=GDB.format(pid=pid, entry=ENTRY, exit=EXIT), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/bp.gdb > /tmp/bp.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/bp.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        print("attached; MAP REBUILD ...")
        drv.exec("MAP REBUILD")
        for _ in range(300):
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c POOLEND /tmp/bp.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                break
            time.sleep(1.0)
        out = HERE / "logs" / "bspopt-pool.log"
        subprocess.run(["docker", "cp", f"{container}:/tmp/bp.log", str(out)], check=True)
        print(f"wrote {out}")
        print(subprocess.run(["bash", "-c", f"grep -E 'PRE|POST' {out}"],
                             capture_output=True, text=True).stdout)
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    main()
