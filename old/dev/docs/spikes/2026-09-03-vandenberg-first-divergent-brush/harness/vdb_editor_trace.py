#!/usr/bin/env python3
r"""Vandenberg Gas twin of `2026-08-29-unatco-repart-live-diff/harness/pass1_brush_trace_unatco.py`
(same gdb capture, retargeted defaults: cached Vandenberg golden, this spike's logs dir, a
longer deadline for the 728-call build). Live GDB capture: per-brush Pass-1 tree state — counts at EVERY `bspBrushCSG` entry plus a raw
binary dump of `Model->Nodes` at each, ending with the state at the world-level `bspRepartition`
entry (= state after the LAST structural brush).

WHY. The UNATCO-class residual is inherited from Pass 1's own incrementally-built world tree
(findings ledger, "Poly-list order divergence localized one stage further"), and every candidate
mechanism EXCEPT a specific brush's own CSG-add has been ruled out (brush order, refresh cadence,
27 decompiled pipeline functions, transform precision).  This capture finds the FIRST brush k where
the editor's tree shape diverges from native's (`UEDCLI_BSPCSG_BRUSH_STATE`, the paired native-side
dump) — per-brush counts first, full node-array bit compare (`pass1_compare.py`) second.

MECHANISM.  `bspBrushCSG` entry is `Editor.dll 0x100355e0` (thiscall: ecx=this, esp+4=Actor,
esp+8=Model).  At entry of the k-th call the Model still holds the state after brush k-1 — so hit k
dumps "after k-1", and the first `bspRepartition` entry (`0x10049fc0`, esp+4=Model) dumps "after the
last".  Node dumps go to /tmp/p1nodes/n%04d.bin in the container (stride 0x40: Plane +0x00,
iVertPool +0x18, iSurf +0x1c, iBack +0x20, iFront +0x24, iPlane +0x28, NumVertices +0x36 byte,
NodeFlags +0x37 byte).  Model Num fields: Nodes +0x5c (Data +0x58), Verts +0x6c, Vectors +0x7c,
Points +0x8c, Surfs +0x9c (offsets live-validated by `emptymodel_worldlevel_trace.py`).

Usage: pass1_brush_trace_unatco.py [golden.dx] [outdir]
  -> <outdir>/pass1-brush-trace-vdb.log  +  <outdir>/p1nodes/n%04d.bin (+ nfinal.bin)
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
from uedcli import config  # noqa: E402
from uedcli.container_assets import resource_mounts  # noqa: E402
from uedcli.driver import Driver, to_z_path  # noqa: E402

GOLDEN = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "/tmp/uedcli-parity-cache/7d06dd6155e5daa7c78e76ed19a66068852973670d1c56dddd9628b2ca393c13"
    "/golden.dx")
OUTDIR = Path(sys.argv[2]) if len(sys.argv) > 2 else (HERE.parent / "logs")
PROJECT_DIR = ROOT / "_scratch/oracle-project"
DEADLINE = 5400.0

def _proc_ticks(container: str, pid: int) -> int:
    out = subprocess.run(["docker", "exec", container, "cat", f"/proc/{pid}/stat"],
                         capture_output=True, text=True).stdout.split()
    return int(out[13]) + int(out[14])  # utime + stime, 100 ticks/s


def wait_editor_idle(drv: Driver, pid: int, *, label: str, thresh_pct: float = 10.0,
                     quiet_reads: int = 8, min_seconds: float = 20.0,
                     timeout: float = 1800.0) -> None:
    """Idle barrier on the unrealed.exe PROCESS (via /proc/<pid>/stat), not `docker stats` —
    container-level CPUPerc reads a constant ~50% on this box even for a fully-idle editor
    (in-container `top` shows 0%; observed live 2026-09-02), so `build_ued_golden._wait_idle`'s
    30% threshold can never fire here.  Same shape otherwise: consecutive quiet reads, a
    min-seconds floor, and a defensive GC-dialog dismiss per poll."""
    t0 = time.time()
    quiet = 0
    prev = _proc_ticks(drv.container, pid)
    while True:
        drv.dismiss_blocking_dialog()
        time.sleep(1.5)
        cur = _proc_ticks(drv.container, pid)
        pct = (cur - prev) / 1.5  # ticks/s = %CPU at 100Hz
        prev = cur
        quiet = quiet + 1 if pct < thresh_pct else 0
        el = time.time() - t0
        if quiet >= quiet_reads and el >= min_seconds:
            print(f"    [{label}] idle after {el:.0f}s (proc cpu {pct:.1f}%)", flush=True)
            return
        if el > timeout:
            raise TimeoutError(f"editor not idle after {timeout:.0f}s [{label}] (proc cpu {pct:.1f}%)")


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
set $k = 0
break *0x100355e0
commands
silent
set $m = *(unsigned int *)($esp + 8)
set $nd = *(unsigned int *)($m + 0x58)
set $nn = *(int *)($m + 0x5c)
printf "CSGENTRY k=%d model=%#x nodes=%d verts=%d vectors=%d points=%d surfs=%d\n", $k, $m, $nn, *(int*)($m+0x6c), *(int*)($m+0x7c), *(int*)($m+0x8c), *(int*)($m+0x9c)
if $nn > 0
  eval "dump binary memory /tmp/p1nodes/n%04d.bin %#x %#x", $k, $nd, $nd + $nn*0x40
end
set $k = $k + 1
continue
end
break *0x10049fc0
commands
silent
set $m2 = *(unsigned int *)($esp + 4)
set $nd2 = *(unsigned int *)($m2 + 0x58)
set $nn2 = *(int *)($m2 + 0x5c)
printf "P1END calls=%d model=%#x nodes=%d verts=%d vectors=%d points=%d surfs=%d\n", $k, $m2, $nn2, *(int*)($m2+0x6c), *(int*)($m2+0x7c), *(int*)($m2+0x8c), *(int*)($m2+0x9c)
if $nn2 > 0
  eval "dump binary memory /tmp/p1nodes/nfinal.bin %#x %#x", $nd2, $nd2 + $nn2*0x40
end
printf "TREEEND\n"
detach
quit
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

    container = "uned-pass1-vdb"
    O.stop_dbg_editor(container, state_dir)
    print(f"[pass1] golden={GOLDEN}", flush=True)
    print(f"[pass1] starting {container} ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        subprocess.run(["docker", "exec", container, "mkdir", "-p", "/tmp/p1nodes"], check=True)
        pid = O._editor_pid(container)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        # `wine_ctl exec` is fire-and-forget (quirks.md "MAP SAVE races the still-running rebuild");
        # UNATCO's MAP LOAD demand-loads for minutes.  Without this barrier the REBUILD keystroke
        # lands on the startup default map and the trace captures an empty Pass 1 (observed live).
        wait_editor_idle(drv, pid, label="map-load")
        print(f"[pass1] editor pid {pid}; attaching gdb ...", flush=True)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/p1bt.gdb"],
                       input=GDB.format(pid=pid), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/p1bt.gdb > /tmp/p1bt.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/p1bt.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[pass1] attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        deadline = time.monotonic() + DEADLINE
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c '^TREEEND' /tmp/p1bt.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                break
            time.sleep(2.0)
        else:
            print(f"[pass1] WARNING: gave up after {DEADLINE:.0f}s", flush=True)
        OUTDIR.mkdir(parents=True, exist_ok=True)
        log = OUTDIR / "pass1-brush-trace-vdb.log"
        log.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/p1bt.log"],
                                       capture_output=True).stdout)
        bins = OUTDIR / "p1nodes"
        bins.mkdir(exist_ok=True)
        subprocess.run(["docker", "exec", container, "bash", "-c",
                        "cd /tmp/p1nodes && tar cf /tmp/p1nodes.tar ."], check=True)
        tar = subprocess.run(["docker", "exec", container, "cat", "/tmp/p1nodes.tar"],
                             capture_output=True).stdout
        subprocess.run(["tar", "xf", "-", "-C", str(bins)], input=tar, check=True)
        print(f"[pass1] wrote {log} + {len(list(bins.glob('*.bin')))} node dumps in {bins}",
              flush=True)
        n = log.read_text(errors="replace").count("\nCSGENTRY ")
        print(f"[pass1] {n} CSGENTRY lines captured", flush=True)
        if n == 0:
            print("[pass1] FAILURE: empty Pass-1 trace — the rebuild ran on an unloaded map", flush=True)
            return 1
    finally:
        O.stop_dbg_editor(container, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
