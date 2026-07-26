#!/usr/bin/env python3
r"""EDITOR bspAddNode RING-SEQUENCE ORACLE — log every `bspAddNode` (ivp, nv) during MAP REBUILD.

WHY.  §70 §11 leaves native entering `bspOptGeom` with +9 vert-pool slots vs the editor (native
10527 vs editor 10518).  The overshoot was localized (`preopt_runs2.py`) to exactly two Pass-D
ORPHAN runs — native run @5596 is 843 long vs the editor's 840 (+3), and native @7591 is 632 vs
the editor's 626 (+6).  Those two runs are contiguous blocks of killed-fragment rings appended by
`AssignAllZones`'s per-landing `bspAddNode`; to fix the over-emit we need the editor's EXACT ring
segmentation of each run (how many rings, each ring's `NumVertices`), which the final `.dx` does
not expose (orphans carry stale point indices, unresolvable to coords).

HOW.  `bspAddNode` (Editor.dll RVA 0x34e80, ImageBase 0x10000000, un-relocated in 32-bit wine) is
the single node/vert emitter for the whole build.  At its entry (first insn, prologue not run):
    [esp+4]  = Model (UModel*)         Model->Verts.Num = +0x6c  (pool size = this ring's iVertPool)
    [esp+0x14] = EdPoly (FPoly*)       FPoly->NumVertices = +0x1c0, iLink = +0x1c4
We MAP LOAD the golden (default Test_Castle.dx), attach gdb with a breakpoint that logs
`ADD ivp=<Verts.Num> nv=<NumVertices> ilink=<iLink>` and continues, then MAP REBUILD.  The result
is the editor's full append sequence: each ring's [ivp, ivp+nv) slot range in emission order, so
the orphan-run ring boundaries can be diffed against native's `UEDCLI_PASSD_DUMP` EMIT lines.

Usage:  bspaddnode_ring_oracle.py [golden.dx] [--target castle|unatco]  ->  logs/bspaddnode-rings.log
        (--target selects the ASSET MOUNTS project — castle default, unatco = bare deusex base dirs.)
"""
import argparse
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

_ap = argparse.ArgumentParser(description="editor bspAddNode ring-sequence oracle")
_ap.add_argument("golden", nargs="?",
                 default="/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx",
                 help="golden .dx to MAP LOAD + MAP REBUILD (default Test_Castle.dx)")
_ap.add_argument("--target", default="castle", choices=sorted(O._TARGETS),
                 help="asset-mounts project for the editor container (castle default / unatco)")
_args = _ap.parse_args()
GOLDEN = Path(_args.golden)
TARGET = O.resolve_target(_args.target)
BSPADDNODE = 0x10034E80

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
set $e = *(unsigned int *)($esp + 0x14)
printf "ADD ivp=%d nv=%d ilink=%d\n", *(int *)($model + 0x6c), *(int *)($e + 0x1c0), *(int *)($e + 0x1c4)
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def main():
    O._ensure_dbg_image()
    mounts = O._composed_mounts(TARGET.project_dir)
    state_dir = O._state_dir(TARGET.project_dir)
    container = f"uned-addnoderings-{TARGET.name}"
    O.stop_dbg_editor(container, state_dir)
    print(f"starting {container} ... golden={GOLDEN}")
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "cp", str(GOLDEN), f"{container}:/work/golden.dx"], check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/ar.gdb"],
                       input=GDB.format(pid=pid, entry=BSPADDNODE), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/ar.gdb > /tmp/ar.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/ar.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        print("attached; MAP REBUILD ...")
        drv.exec("MAP REBUILD")
        # Quiescence: wait until the ADD line count stops growing for a window.
        last = -1
        stable = 0
        for _ in range(600):
            cnt = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c '^ADD ' /tmp/ar.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            cnt = int(cnt) if cnt and cnt != "0" else 0
            if cnt == last and cnt > 0:
                stable += 1
                if stable >= 8:
                    break
            else:
                stable = 0
                last = cnt
            time.sleep(1.0)
        out = HERE / "logs" / "bspaddnode-rings.log"
        subprocess.run(["docker", "cp", f"{container}:/tmp/ar.log", str(out)], check=True)
        nd = subprocess.run(["bash", "-c", f"grep -c '^ADD ' {out}"], capture_output=True, text=True).stdout.strip()
        print(f"wrote {out} ({nd} ADD lines)")
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    main()
