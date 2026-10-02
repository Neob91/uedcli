#!/usr/bin/env python3
r"""EDITOR bspOptGeom inserter oracle at FULL-UNATCO scale — every T-junction weld ATTEMPT, in order.

UNATCO analog of `bspopt_insert_oracle.py` (castle): MAP LOAD the full-map golden, MAP REBUILD with a
gdb breakpoint at the inserter (`Editor.dll 0x31920`), log one INS line per call.  The breakpoint is
at ENTRY, BEFORE the ring-size cap (`NumVertices+1 >= 16` -> debugf "Node side limit reached" +
return, 0x31960-0x31994, disasm 2026-08-25), so an INS line with `nv>=15` is a REFUSED weld.  Native
(`bspoptgeom.rs insert_ring_vertex`) has no such cap — this log is the live evidence for that gap and
for the editor's weld count/order at real scale (board item front-2-re-characterized).

Entry args (pre-`push ebp`): [esp+4]=Model [esp+0xc]=iNode [esp+0x10]=edge [esp+0x14]=point.
UModel: Nodes.Data +0x58 (stride 0x40, plane +0x00, NumVertices +0x36), Points.Data +0x88 (stride 0xc).

Usage:  bspopt_insert_unatco.py [golden.dx]   ->  logs/bspopt-insert-unatco.log
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]      # editor-tree-oracle/ -> harness/ -> spike/ -> spikes/ -> docs/ -> dev/ -> root
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
HERE = HARNESS / "editor-tree-oracle"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HARNESS)); sys.path.insert(0, str(HERE))
import editor_tree_oracle as O
from uedcli.driver import Driver, to_z_path

GOLDEN = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/UEDGolden_unatco_full.dx")
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
    target = O.resolve_target("unatco")
    project = target.project_dir
    mounts = O._composed_mounts(project)
    state_dir = O._state_dir(project)
    container = "uned-insdump-unatco"
    O.stop_dbg_editor(container, state_dir)
    print(f"starting {container} (golden={GOLDEN}) ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        try:
            ref = target.ref_pkgs(734)
            print(f"OBJ LOAD {len(ref)} referenced packages ...", flush=True)
            for p in ref:
                try:
                    drv.exec(f"OBJ LOAD FILE={to_z_path(str(p))}")
                except Exception as exc:
                    print(f"  WARN OBJ LOAD {p}: {exc}", flush=True)
        except Exception as exc:
            print(f"WARN ref_pkgs: {exc}", flush=True)
        # rootless docker: `docker cp` remount-ro fails on the :ro mounts -> stream via exec cat.
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
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
        print("attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        # Quiescence: INS count stable for 30 s (welds land near the END of the rebuild; a shorter
        # window could fire during the pre-optgeom phases when the count sits at 0 -> also require
        # a nonzero count).  Hard cap 25 min.
        last, stable_since = -1, time.monotonic()
        for _ in range(1500):
            c = subprocess.run(["docker", "exec", container, "bash", "-c",
                                "grep -c '^INS ' /tmp/ins.log 2>/dev/null || true"],
                               capture_output=True, text=True).stdout.strip()
            c = int(c) if c.isdigit() else 0
            now = time.monotonic()
            if c != last:
                last, stable_since = c, now
                print(f"  INS={c}", flush=True)
            elif c > 0 and now - stable_since >= 30:
                break
            time.sleep(1.0)
        out = HERE / "logs" / "bspopt-insert-unatco.log"
        data = subprocess.run(["docker", "exec", container, "cat", "/tmp/ins.log"],
                              capture_output=True).stdout
        out.write_bytes(data)
        print(f"wrote {out} ({last} INS lines)", flush=True)
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    main()
