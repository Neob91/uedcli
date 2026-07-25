#!/usr/bin/env python3
"""Dump the EDITOR's INCREMENTAL world tree (Model->Nodes) at the start of repartition.

Breakpoint bspBuildFPolys (0x10036090); at entry Model=[esp+4]. Walk Nodes[0..Num): plane, iF, iB,
iP, iSurf, nv, nodeflags. This is the complete incremental tree just before bspRepartition rebuilds it
— the direct counterpart of native's UEDCTL_BSPCSG_TREE_STRUCT dump.
"""
import subprocess, sys, time
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl")
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
HERE = HARNESS / "editor-tree-oracle"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HARNESS)); sys.path.insert(0, str(HERE))
import editor_tree_oracle as O
from uedctl.driver import Driver, to_z_path
import subset_diff

N = int(sys.argv[1]) if len(sys.argv) > 1 else 33
VA = 0x10036090  # bspBuildFPolys

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
set $nodes = *(unsigned int *)($model + 0x58)
set $num = *(int *)($model + 0x5c)
printf "TREEBEGIN num=%d\n", $num
set $i = 0
while $i < $num
  set $n = $nodes + $i * 0x40
  printf "ND %d plane=%.5f,%.5f,%.5f,%.5f iF=%d iB=%d iP=%d isurf=%d nv=%d nf=%#x\n", $i, *(float *)($n), *(float *)($n+4), *(float *)($n+8), *(float *)($n+0xc), *(int *)($n+0x24), *(int *)($n+0x20), *(int *)($n+0x28), *(int *)($n+0x1c), *(unsigned char *)($n+0x36), *(unsigned char *)($n+0x37)
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
    golden = subset_diff.build_editor_subset(N)
    mounts = O._composed_mounts(subset_diff.CASTLE_PROJECT)
    state_dir = O._state_dir(subset_diff.CASTLE_PROJECT)
    container = f"uned-estruct-n{N}"
    O.stop_dbg_editor(container, state_dir)
    print(f"starting {container} ...")
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "cp", str(golden), f"{container}:/work/golden.dx"], check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/es.gdb"],
                       input=GDB.format(pid=pid, va=VA), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/es.gdb > /tmp/es.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/es.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        print("attached; MAP REBUILD ...")
        drv.exec("MAP REBUILD")
        for _ in range(300):
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c TREEEND /tmp/es.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                break
            time.sleep(1.0)
        out = HERE / "logs" / f"editor-struct-{N}.log"
        subprocess.run(["docker", "cp", f"{container}:/tmp/es.log", str(out)], check=True)
        nd = subprocess.run(["bash", "-c", f"grep -c '^ND ' {out}"], capture_output=True, text=True).stdout.strip()
        print(f"wrote {out} ({nd} ND lines)")
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    main()
