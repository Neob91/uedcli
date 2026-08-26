#!/usr/bin/env python3
r"""EDITOR post-`bspRepartition` NODE TREE at full-UNATCO scale.

The serialized golden `.dx` carries only the FINISHED tree — nothing in it separates the nodes the
world repartition built from the ones the later semisolid/detail-brush CSG layer appends. This dumps
`Model->Nodes` (and `Model->Surfs`' owning `(iActor, iBrushPoly)` key) at `0x1004a05f` — right after
`bspRefresh(Model, NoRemapSurfs=1)` inside `bspRepartition` (`Editor.dll 0x49fc0`), i.e. exactly the
state a port reaches when its own repartition returns — so the two can be diffed node-for-node.

`FBspNode` offsets (from `editor_preopt_nodes.py`): stride 0x40, Plane at +0x00 (x,y,z,w),
iVertPool +0x18, iSurf +0x1c, iBack +0x20, iFront +0x24, iPlane +0x28, NumVertices +0x36 (byte),
NodeFlags +0x37 (byte).  Model fields: Nodes.Data +0x58 / Num +0x5c ; Surfs.Num +0x9c.

Usage:  repart_tree_unatco.py [golden.dx]   ->  logs/repart-tree-unatco.log
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
HERE = HARNESS / "editor-tree-oracle"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HARNESS)); sys.path.insert(0, str(HERE))
import editor_tree_oracle as O
from uedcli import config
from uedcli.container_assets import resource_mounts
from uedcli.driver import Driver, to_z_path

GOLDEN = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/UEDGolden_unatco_full.dx")
PROJECT_DIR = ROOT / "_scratch/oracle-project"

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
continue
end
break *0x1004a05f
commands
silent
set $nd = *(unsigned int *)($m + 0x58)
set $nn = *(int *)($m + 0x5c)
set $sn = *(int *)($m + 0x9c)
printf "TREEBEGIN nodes=%d surfs=%d\n", $nn, $sn
set $i = 0
while $i < $nn
  set $n = $nd + $i * 0x40
  printf "RNODE %d isurf=%d nv=%d iB=%d iF=%d iP=%d nf=%d plane=%.5f,%.5f,%.5f,%.5f\n", $i, *(int *)($n + 0x1c), *(unsigned char *)($n + 0x36), *(int *)($n + 0x20), *(int *)($n + 0x24), *(int *)($n + 0x28), *(unsigned char *)($n + 0x37), *(float *)($n), *(float *)($n + 4), *(float *)($n + 8), *(float *)($n + 12)
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
    if not PROJECT_DIR.exists():
        PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        (PROJECT_DIR / "uedcli.toml").write_text('game = "deusex"\n')

    O._ensure_dbg_image()
    project = config.load_project(str(PROJECT_DIR))
    mounts = resource_mounts(config.composed_search_dirs(project, config.load_user_config()))
    state_dir = config.state_dir(project.root, create=True)

    container = "uned-reparttree-unatco"
    O.stop_dbg_editor(container, state_dir)
    print(f"starting {container} (golden={GOLDEN}) ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/rtu.gdb"],
                       input=GDB.format(pid=pid), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/rtu.gdb > /tmp/rtu.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/rtu.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        print("attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        for _ in range(2400):
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c TREEEND /tmp/rtu.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                break
            time.sleep(1.0)
        out = HERE / "logs" / "repart-tree-unatco.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/rtu.log"],
                                       capture_output=True).stdout)
        print(f"wrote {out}", flush=True)
        for line in out.read_text(errors="replace").splitlines():
            if line.startswith("TREEBEGIN"):
                print("  " + line)
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    main()
