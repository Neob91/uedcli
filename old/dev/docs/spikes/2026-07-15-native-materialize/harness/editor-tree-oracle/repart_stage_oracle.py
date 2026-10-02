#!/usr/bin/env python3
r"""Trace the editor's Verts/Points pool through bspRepartition SUB-STAGES.

bspRepartition (0x49fc0) issues, in order:
  0x1004a00d  after bspBuildFPolys (MakeEdPolys -> Model->Polys)
  0x1004a027  after bspMergeCoplanars
  0x1004a047  after bspBuild (EmptyModel(0,0) + SplitPolyList)
  0x1004a05f  after bspRefresh(Model, NoRemapSurfs=1)
Reads Verts.Num(+0x6c), Points.Num(+0x8c), Surfs.Num(+0x9c), Nodes.Num(+0x5c) at each — the Model
is [edi]... actually the Model arg is [ebp+8] at entry; we save it into $m at 0x49feb (mov edi,ecx
is thiscall engine; Model is [ebp+8]).

Usage:  repart_stage_oracle.py [golden.dx]  ->  logs/repart-stage.log
"""
import subprocess, sys, time
from pathlib import Path
ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
HERE = HARNESS / "editor-tree-oracle"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HARNESS)); sys.path.insert(0, str(HERE))
import editor_tree_oracle as O
from uedcli.driver import Driver, to_z_path
import subset_diff

GOLDEN = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx")

def dump(lbl):
    return (r'printf "%s nodes=%d verts=%d points=%d surfs=%d\n", "'+lbl+r'", '
            r'*(int *)($m + 0x5c), *(int *)($m + 0x6c), *(int *)($m + 0x8c), *(int *)($m + 0x9c)')

# Model at bspRepartition: ecx=this(engine), Model arg=[ebp+8].  We capture at entry into $m.
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
""" + dump("A_entry") + r"""
continue
end
break *0x1004a00d
commands
silent
""" + dump("B_makeedpolys") + r"""
continue
end
break *0x1004a027
commands
silent
""" + dump("C_mergecoplanar") + r"""
continue
end
break *0x1004a047
commands
silent
""" + dump("D_bspbuild") + r"""
continue
end
break *0x1004a05f
commands
silent
""" + dump("E_bsprefresh") + r"""
printf "STAGEEND\n"
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""

def main():
    O._ensure_dbg_image()
    mounts = O._composed_mounts(subset_diff.CASTLE_PROJECT)
    state_dir = O._state_dir(subset_diff.CASTLE_PROJECT)
    container = "uned-repartstage"
    O.stop_dbg_editor(container, state_dir)
    print(f"starting {container} ...")
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "cp", str(GOLDEN), f"{container}:/work/golden.dx"], check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/rs.gdb"],
                       input=GDB.format(pid=pid), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/rs.gdb > /tmp/rs.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/rs.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        print("attached; MAP REBUILD ...")
        drv.exec("MAP REBUILD")
        for _ in range(300):
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c STAGEEND /tmp/rs.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                break
            time.sleep(1.0)
        out = HERE / "logs" / "repart-stage.log"
        subprocess.run(["docker", "cp", f"{container}:/tmp/rs.log", str(out)], check=True)
        print(subprocess.run(["bash", "-c", f"grep -E 'A_|B_|C_|D_|E_' {out}"],
                             capture_output=True, text=True).stdout)
    finally:
        O.stop_dbg_editor(container, state_dir)

if __name__ == "__main__":
    main()
