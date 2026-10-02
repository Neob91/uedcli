#!/usr/bin/env python3
"""Editor-tree oracle AUGMENTED with the parent node's PLANE (structural-divergence probe).

Same as editor_tree_oracle.run but the bspAddNode breakpoint also prints
Model->Nodes[iParent].Plane (PP=X,Y,Z,W) and NumVertices (pnv). Writes oracle-pp-N.log.
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

N = int(sys.argv[1]) if len(sys.argv) > 1 else 33
VA = 0x10034E80

# At bspAddNode entry: [esp+4]=Model,[esp+8]=iParent,[esp+0xc]=place,[esp+0x10]=flags,[esp+0x14]=EdPoly.
# Parent plane: Model->Nodes(+0x58)[iParent].Plane(+0). pnv at node+0x36.
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
set $e = *(unsigned int *)($esp + 0x14)
set $model = *(unsigned int *)($esp + 4)
set $ip = *(int *)($esp + 8)
set $ppx = 0.0
set $ppy = 0.0
set $ppz = 0.0
set $ppw = 0.0
set $pnv = -1
set $nodes = *(unsigned int *)($model + 0x58)
set $nnum = *(int *)($model + 0x5c)
if $ip >= 0 && $nodes != 0 && $ip < $nnum
  set $pn = $nodes + $ip * 0x40
  set $ppx = *(float *)($pn)
  set $ppy = *(float *)($pn + 4)
  set $ppz = *(float *)($pn + 8)
  set $ppw = *(float *)($pn + 0xc)
  set $pnv = *(unsigned char *)($pn + 0x36)
end
printf "ADD ret=%#x model=%#x parent=%d place=%d flags=%#x ilink=%d nv=%d N=%.5f,%.5f,%.5f B=%.5f,%.5f,%.5f PP=%.5f,%.5f,%.5f,%.5f pnv=%d\n", *(unsigned int *)($esp), $model, $ip, *(int *)($esp + 0xc), *(unsigned int *)($esp + 0x10), *(int *)($e + 0x1c4), *(int *)($e + 0x1c0), *(float *)($e + 0xc), *(float *)($e + 0x10), *(float *)($e + 0x14), *(float *)($e), *(float *)($e + 4), *(float *)($e + 8), $ppx, $ppy, $ppz, $ppw, $pnv
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def main():
    O._ensure_dbg_image()
    golden = subset_diff.build_editor_subset(N)
    mounts = O._composed_mounts(subset_diff.CASTLE_PROJECT)
    state_dir = O._state_dir(subset_diff.CASTLE_PROJECT)
    container = f"uned-oraclepp-n{N}"
    O.stop_dbg_editor(container, state_dir)
    print(f"starting {container} ...")
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "cp", str(golden), f"{container}:/work/golden.dx"], check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/opp.gdb"],
                       input=GDB.format(pid=pid, va=VA), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/opp.gdb > /tmp/opp.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/opp.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        print("attached; MAP REBUILD ...")
        drv.exec("MAP REBUILD")
        last = -1; stable = 0
        for _ in range(900):
            c = subprocess.run(["docker", "exec", container, "bash", "-c",
                                "grep -c '^ADD ' /tmp/opp.log 2>/dev/null || true"],
                               capture_output=True, text=True).stdout.strip()
            c = int(c) if c.isdigit() else 0
            if c == last and c > 0:
                stable += 1
                if stable >= 6:
                    break
            else:
                stable = 0
            last = c
            time.sleep(1.0)
        out = HERE / "logs" / f"oracle-pp-{N}.log"
        subprocess.run(["docker", "cp", f"{container}:/tmp/opp.log", str(out)], check=True)
        print(f"wrote {out} ({last} ADD lines)")
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    main()
