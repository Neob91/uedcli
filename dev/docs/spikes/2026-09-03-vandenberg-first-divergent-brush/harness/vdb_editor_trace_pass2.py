#!/usr/bin/env python3
r"""Vandenberg Pass-2 twin of `vdb_editor_trace.py`: capture EVERY `bspBrushCSG` entry (Pass 1 AND
the post-repartition Pass-2 detail calls), every `bspRepartition` entry (counts; node dump at the
FIRST post-Pass-2 one = the state after the last detail brush), and detach at `bspOptGeom` entry
(`Editor.dll 0x10036870`, export-table).  Node binaries are dumped only from k>=728 (Pass 2) —
the Pass-1 dumps already exist from the first trace.

Usage: vdb_editor_trace_pass2.py [golden.dx] [outdir]
  -> <outdir>/pass2-brush-trace-vdb.log  +  <outdir>/p2nodes/n%04d.bin (+ nrepart1.bin, nfinal.bin)
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OLD_HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(OLD_HARNESS))
sys.path.insert(0, str(OLD_HARNESS / "editor-tree-oracle"))
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

sys.path.insert(0, str(HERE))
from vdb_editor_trace import wait_editor_idle  # noqa: E402

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
set $r = 0
break *0x100355e0
commands
silent
set $m = *(unsigned int *)($esp + 8)
set $nd = *(unsigned int *)($m + 0x58)
set $nn = *(int *)($m + 0x5c)
printf "CSGENTRY k=%d model=%#x nodes=%d verts=%d vectors=%d points=%d surfs=%d\n", $k, $m, $nn, *(int*)($m+0x6c), *(int*)($m+0x7c), *(int*)($m+0x8c), *(int*)($m+0x9c)
if $k >= 728 && $nn > 0
  eval "dump binary memory /tmp/p2nodes/n%04d.bin %#x %#x", $k, $nd, $nd + $nn*0x40
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
printf "REPART r=%d atk=%d nodes=%d verts=%d vectors=%d points=%d surfs=%d\n", $r, $k, $nn2, *(int*)($m2+0x6c), *(int*)($m2+0x7c), *(int*)($m2+0x8c), *(int*)($m2+0x9c)
if $r == 1 && $nn2 > 0
  eval "dump binary memory /tmp/p2nodes/nrepart1.bin %#x %#x", $nd2, $nd2 + $nn2*0x40
end
set $r = $r + 1
continue
end
break *0x10036870
commands
silent
set $m3 = *(unsigned int *)($esp + 4)
set $nd3 = *(unsigned int *)($m3 + 0x58)
set $nn3 = *(int *)($m3 + 0x5c)
printf "OPTGEOM atk=%d atr=%d nodes=%d verts=%d vectors=%d points=%d surfs=%d\n", $k, $r, $nn3, *(int*)($m3+0x6c), *(int*)($m3+0x7c), *(int*)($m3+0x8c), *(int*)($m3+0x9c)
if $nn3 > 0
  eval "dump binary memory /tmp/p2nodes/nfinal.bin %#x %#x", $nd3, $nd3 + $nn3*0x40
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
    container = "uned-pass2-vdb"
    O.stop_dbg_editor(container, state_dir)
    print(f"[pass2] golden={GOLDEN}", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        subprocess.run(["docker", "exec", container, "mkdir", "-p", "/tmp/p2nodes"], check=True)
        pid = O._editor_pid(container)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        wait_editor_idle(drv, pid, label="map-load")
        print(f"[pass2] editor pid {pid}; attaching gdb ...", flush=True)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/p2bt.gdb"],
                       input=GDB.format(pid=pid), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/p2bt.gdb > /tmp/p2bt.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/p2bt.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[pass2] attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        deadline = time.monotonic() + DEADLINE
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c '^TREEEND' /tmp/p2bt.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                break
            time.sleep(2.0)
        else:
            print(f"[pass2] WARNING: gave up after {DEADLINE:.0f}s", flush=True)
        OUTDIR.mkdir(parents=True, exist_ok=True)
        log = OUTDIR / "pass2-brush-trace-vdb.log"
        log.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/p2bt.log"],
                                       capture_output=True).stdout)
        bins = OUTDIR / "p2nodes"
        bins.mkdir(exist_ok=True)
        subprocess.run(["docker", "exec", container, "bash", "-c",
                        "cd /tmp/p2nodes && tar cf /tmp/p2nodes.tar ."], check=True)
        tar = subprocess.run(["docker", "exec", container, "cat", "/tmp/p2nodes.tar"],
                             capture_output=True).stdout
        subprocess.run(["tar", "xf", "-", "-C", str(bins)], input=tar, check=True)
        n = log.read_text(errors="replace").count("\nCSGENTRY ")
        print(f"[pass2] wrote {log}; {n} CSGENTRY lines; "
              f"{len(list(bins.glob('*.bin')))} node dumps", flush=True)
        return 0 if n else 1
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    raise SystemExit(main())
