#!/usr/bin/env python3
r"""Live GDB capture: the editor's per-poly NORMAL bit patterns for a specific brush range during
Pass 1 — (a) right after `bspBrushCSG` LOOP-1's `FPoly::Transform` (call site `0x10035892`, return
`0x10035898`, this=FPoly in ecx at the call), and (b) at `bspFilterFPoly` entry (`0x10031f50`,
EdPoly = esp+0xc; thiscall, stack args FilterFunc/Model/EdPoly) — the value `bspAddNode` will store
as the node/surf plane.

WHY. The per-brush Pass-1 trace (`pass1_brush_trace_unatco.py` + `pass1_compare.py`) proved UNATCO's
Pass-1 tree SHAPE is bit-identical to native's (6368 nodes, all links equal) with exactly 100 nodes
differing ONLY in plane floats by 1 ULP — first at node 359 (`Brush578`, k=24, scaled PostScale,
CSG_Subtract): editor stores the exact axis `0xbf800000`, native's scaled-path
`SafeNormalSlow(VectorXform·N_local)` reproduces `0xbf7fffff` (offline replication
`vecxform_replicate578.py`).  This probe pins WHERE the editor's exact value arises: already at
`FPoly::Transform` output (=> native's covariant matrix/normalize arithmetic differs) or only at
filter time (=> a later recompute native lacks).

FPoly layout: Base +0x0, Normal +0xc, NumVertices +0x1c0, iLink +0x1c4.

Usage: pass1_normal_probe_unatco.py [golden.dx] [outdir] [klo] [khi]
  -> <outdir>/pass1-normal-probe-unatco.log
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OLD_HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
OLD_ORACLE = OLD_HARNESS / "editor-tree-oracle"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(OLD_HARNESS))
sys.path.insert(0, str(OLD_ORACLE))
import editor_tree_oracle as O  # noqa: E402
from pass1_brush_trace_unatco import wait_editor_idle  # noqa: E402
from uedcli import config  # noqa: E402
from uedcli.container_assets import resource_mounts  # noqa: E402
from uedcli.driver import Driver, to_z_path  # noqa: E402

GOLDEN = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    Path("/workspace/uedcli/_scratch/bsp-parity-proj/golden_unatco_control.dx"))
OUTDIR = Path(sys.argv[2]) if len(sys.argv) > 2 else (HERE.parent / "logs")
KLO = int(sys.argv[3]) if len(sys.argv) > 3 else 20
KHI = int(sys.argv[4]) if len(sys.argv) > 4 else 28
PROJECT_DIR = ROOT / "_scratch/oracle-project"
DEADLINE = 1800.0

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
set $k = -1
set $fp1 = 0
break *0x100355e0
commands
silent
set $k = $k + 1
if $k > {khi}
  printf "PROBEEND\n"
  detach
  quit
end
printf "CSGENTRY k=%d\n", $k
continue
end
break *0x10035892
commands
silent
set $fp1 = $ecx
if $k >= {klo}
  printf "PRE k=%d N=%08x,%08x,%08x B=%08x,%08x,%08x nv=%d ilink=%d\n", $k, *(unsigned int*)($fp1+0xc), *(unsigned int*)($fp1+0x10), *(unsigned int*)($fp1+0x14), *(unsigned int*)($fp1), *(unsigned int*)($fp1+4), *(unsigned int*)($fp1+8), *(int*)($fp1+0x1c0), *(int*)($fp1+0x1c4)
end
continue
end
break *0x10035898
commands
silent
if $k >= {klo}
  printf "XFORM k=%d N=%08x,%08x,%08x B=%08x,%08x,%08x nv=%d ilink=%d\n", $k, *(unsigned int*)($fp1+0xc), *(unsigned int*)($fp1+0x10), *(unsigned int*)($fp1+0x14), *(unsigned int*)($fp1), *(unsigned int*)($fp1+4), *(unsigned int*)($fp1+8), *(int*)($fp1+0x1c0), *(int*)($fp1+0x1c4)
end
continue
end
break *0x10031f50
commands
silent
if $k >= {klo}
  set $e = *(unsigned int *)($esp + 0xc)
  printf "FILTER k=%d N=%08x,%08x,%08x B=%08x,%08x,%08x nv=%d ilink=%d\n", $k, *(unsigned int*)($e+0xc), *(unsigned int*)($e+0x10), *(unsigned int*)($e+0x14), *(unsigned int*)($e), *(unsigned int*)($e+4), *(unsigned int*)($e+8), *(int*)($e+0x1c0), *(int*)($e+0x1c4)
end
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def main() -> int:
    if not PROJECT_DIR.exists():
        PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        (PROJECT_DIR / "uedcli.toml").write_text('game = "deusex"\n')

    O._ensure_dbg_image()
    project = config.load_project(str(PROJECT_DIR))
    user_config = config.load_user_config()
    mounts = resource_mounts(config.composed_search_dirs(project, user_config))
    state_dir = config.state_dir(project.root, create=True)

    container = "uned-p1norm-unatco"
    O.stop_dbg_editor(container, state_dir)
    print(f"[p1norm] golden={GOLDEN} k=[{KLO},{KHI}]", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        pid = O._editor_pid(container)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        wait_editor_idle(drv, pid, label="map-load")
        print(f"[p1norm] editor pid {pid}; attaching gdb ...", flush=True)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/p1n.gdb"],
                       input=GDB.format(pid=pid, klo=KLO, khi=KHI), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/p1n.gdb > /tmp/p1n.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/p1n.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[p1norm] attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        deadline = time.monotonic() + DEADLINE
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c '^PROBEEND' /tmp/p1n.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                break
            time.sleep(2.0)
        else:
            print(f"[p1norm] WARNING: gave up after {DEADLINE:.0f}s", flush=True)
        OUTDIR.mkdir(parents=True, exist_ok=True)
        log = OUTDIR / f"pass1-normal-probe-{GOLDEN.stem}.log"
        log.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/p1n.log"],
                                       capture_output=True).stdout)
        txt = log.read_text(errors="replace")
        print(f"[p1norm] wrote {log}: {txt.count(chr(10) + 'XFORM ')} XFORM, "
              f"{txt.count(chr(10) + 'FILTER ')} FILTER lines", flush=True)
    finally:
        O.stop_dbg_editor(container, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
