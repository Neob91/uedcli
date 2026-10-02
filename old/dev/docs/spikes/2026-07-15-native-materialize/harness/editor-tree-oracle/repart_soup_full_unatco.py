#!/usr/bin/env python3
r"""EDITOR bspRepartition ROOT SOUP ORACLE at FULL-UNATCO scale -- full poly content, not just count.

Extends `repart_numpolys_unatco.py` (which only counted the root soup: 2514) with the full per-poly
dump `editor_polys_oracle.py` already does at castle scale (index, nv, ilink, normal, base, flags,
verts) -- same breakpoint VA, same FPoly offsets, same asset-mount project setup.  Needed to check
whether the editor's real root soup, in ORDER and CONTENT, matches native's (`UEDCLI_BSPCSG_SOUP_ORDER`)
closely enough that a `FindBestSplit` candidate-slot comparison downstream is meaningful -- order
fidelity was only ever confirmed at castle scale (199/199 multiset AND order); at UNATCO only the
COUNT was confirmed close (2514 vs 2504, +0.4%).

FPoly fields (from `editor_polys_oracle.py`): Base=+0x00, Normal=+0x0c, Vertex[0]=+0x30 (stride
0xc), NumVertices=+0x1c0, iLink=+0x1c4.  PolyFlags=+0x1b0 (`bspcsg.rs`'s `find_best_split_exact`
comment: "test byte [eax+0x1b0],0x28" -- the structural/portal eligibility mask).

Usage:  repart_soup_full_unatco.py [golden.dx]   ->  logs/repart-soup-full-unatco.log
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
VA = 0x1004A041
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
break *{va:#x}
commands
silent
set $model = *(unsigned int *)($esp)
set $polys = *(unsigned int *)($model + 0x54)
set $data = *(unsigned int *)($polys + 0x28)
set $num = *(int *)($polys + 0x2c)
printf "POLYSBEGIN model=%#x polys=%#x num=%d\n", $model, $polys, $num
set $i = 0
while $i < $num
  set $fpol = $data + $i * 0x1d8
  set $nv = *(int *)($fpol + 0x1c0)
  printf "POLY %d nv=%d ilink=%d flags=%#x N=%.6f,%.6f,%.6f B=%.6f,%.6f,%.6f\n", $i, $nv, *(int *)($fpol + 0x1c4), *(unsigned int *)($fpol + 0x1b0), *(float *)($fpol + 0xc), *(float *)($fpol + 0x10), *(float *)($fpol + 0x14), *(float *)($fpol), *(float *)($fpol + 4), *(float *)($fpol + 8)
  set $i = $i + 1
end
printf "POLYSEND\n"
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
    user_config = config.load_user_config()
    search_dirs = config.composed_search_dirs(project, user_config)
    mounts = resource_mounts(search_dirs)
    state_dir = config.state_dir(project.root, create=True)

    container = "uned-repartsoupfull-unatco"
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
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/rsf.gdb"],
                       input=GDB.format(pid=pid, va=VA), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/rsf.gdb > /tmp/rsf.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/rsf.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        print("attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        for _ in range(1500):
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c POLYSEND /tmp/rsf.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                break
            time.sleep(1.0)
        out = HERE / "logs" / "repart-soup-full-unatco.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        data = subprocess.run(["docker", "exec", container, "cat", "/tmp/rsf.log"],
                              capture_output=True).stdout
        out.write_bytes(data)
        print(f"wrote {out}", flush=True)
        nd = subprocess.run(["bash", "-c", f"grep -c '^POLY ' {out}"],
                            capture_output=True, text=True).stdout.strip()
        print(f"{nd} POLY lines")
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    main()
