#!/usr/bin/env python3
r"""EDITOR FindBestSplit stride/param oracle — resolve the world-repartition candidate STRIDE.

The decoded `FindBestSplit` (`0x335d0`) strides its candidate loop by `Inc` = f(Opt): Opt=0→N/4,
Opt=1→N/10, Opt=2→1 (`0x336c8: mov [ebp-0x18], ebx` holds the computed `Inc`).  The editor's root
splitter (final Nodes[0]) lands on a soup index that is NOT a multiple of N/10, which contradicts the
static reading that the world repartition passes Opt=1 (GOOD).  So OBSERVE the real value: breakpoint
`0x100336c8` at the FIRST FindBestSplit call (the SplitPolyList root) and log NumPolys, Opt, Balance
and the computed stride `Inc`.

FindBestSplit(NumPolys=[ebp+8], PolyList=[ebp+0xc], Opt=[ebp+0x10], Balance=[ebp+0x14]); at 0x336c8
ebx=Inc, esi=NumPolys.

Usage:  fbs_stride_oracle.py [N=33]
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
# FindBestSplit return (0x338ee `mov eax,ebx`): eax=winner FPoly*, [ebp-0x18]=stride Inc,
# [ebp+8]=NumPolys, [ebp+0x10]=Opt, [ebp+0x14]=Balance.  The FIRST call with NumPolys>100 is the
# WORLD-repartition SplitPolyList root (temp-brush builds are all small, <=~20 polys).
VA = 0x100338EE

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
break *{va:#x} if *(int *)($ebp + 8) > 100
commands
silent
set $w = $eax
printf "FBS numpolys=%d opt=%d balance=%d stride=%d winN=%.5f,%.5f,%.5f winB=%.5f,%.5f,%.5f\n", *(int *)($ebp + 8), *(int *)($ebp + 0x10), *(int *)($ebp + 0x14), *(int *)($ebp - 0x18), *(float *)($w + 0xc), *(float *)($w + 0x10), *(float *)($w + 0x14), *(float *)($w), *(float *)($w + 4), *(float *)($w + 8)
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
    container = f"uned-fbs-n{N}"
    O.stop_dbg_editor(container, state_dir)
    print(f"starting {container} ...")
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "cp", str(golden), f"{container}:/work/golden.dx"], check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/fbs.gdb"],
                       input=GDB.format(pid=pid, va=VA), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/fbs.gdb > /tmp/fbs.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/fbs.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        print("attached; MAP REBUILD ...")
        drv.exec("MAP REBUILD")
        for _ in range(120):
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c '^FBS ' /tmp/fbs.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                break
            time.sleep(1.0)
        out = subprocess.run(["docker", "exec", container, "bash", "-c",
                              "grep '^FBS ' /tmp/fbs.log | head -1"],
                             capture_output=True, text=True).stdout.strip()
        print("RESULT:", out)
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    main()
