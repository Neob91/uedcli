#!/usr/bin/env python3
r"""Round 14: live GDB capture of `bspAddPoint` AND `bspRefresh` calls INTERLEAVED in one gdb session,
with a single global sequence counter, so the exact call ORDER between the two functions can be read
directly off one log -- round 9/11/12 traced them separately and could only correlate by call-index
heuristics.

WHY. Round 13's incremental-point-pool implementation calls the (pre-existing)
`passes::bsp_refresh_points_vectors` GC exactly ONCE per brush, in `bsp_brush_csg`'s tail -- matching
round 9's "5 bspRefresh calls for DX.dx's 5 brushes" correlation. That measured WORSE on DX.dx and
CRASHED on UNATCO ("vert iVertex index -1 out of range"), which round 13 attributed to the real
editor's cadence being FINER than once-per-brush. But round 9's own case (DX.dx) has ZERO cross-brush
splits, so "5 calls for 5 brushes" is equally consistent with a true per-brush cadence OR a finer
cadence that happens to fire once per brush when nothing else triggers it early. This script re-runs
the trace on round 12's T-junction synthetic trunk (4 brushes: Room/PillarB/PillarC/PillarD, WITH a
real persisting cross-brush split) to settle it: does `bspRefresh`'s call COUNT still equal brush
count (4) on a case with real splits, and if not, WHERE (relative to the addpoint/split sequence) do
the extra calls land?

VAs (both already pinned by round 9, reused unmodified):
  bspAddPoint entry  0x1003545d (post-prologue), ret 0x100354ce / 0x100355a7
  bspRefresh  entry  0x10036cd0,                 ret 0x1003718f

Usage:  combined_refresh_addpoint_trace.py [golden.dx]
  -> logs/combined-refresh-addpoint-trace.log (also copied to a caller-given --out if passed via env)
"""
import os
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

GOLDEN = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    ROOT / "_scratch/round14/golden_tjunction.dx")
OUT_NAME = os.environ.get("ROUND14_OUT_NAME", "combined-refresh-addpoint-trace.log")
PROJECT_DIR = ROOT / "_scratch/oracle-project"
POLL, QUIET_FOR, DEADLINE = 1.0, 15.0, 900.0

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
set $seq = 0
set $apidx = 0
break *0x1003545d
commands
silent
set $seq = $seq + 1
set $apidx = $apidx + 1
set $arg1 = *(unsigned int *)($ebp + 8)
set $arg2 = *(unsigned int *)($ebp + 0xc)
set $arg3 = *(unsigned int *)($ebp + 0x10)
set $x2 = *(float *)$arg2
set $y2 = *(float *)($arg2 + 4)
set $z2 = *(float *)($arg2 + 8)
printf "SEQ=%d AP_CALL apidx=%d exact=%d x=%.6f y=%.6f z=%.6f\n", $seq, $apidx, $arg3, $x2, $y2, $z2
continue
end
break *0x100354ce
commands
silent
set $seq = $seq + 1
printf "SEQ=%d AP_RET1 apidx=%d idx=%d\n", $seq, $apidx, $eax
continue
end
break *0x100355a7
commands
silent
set $seq = $seq + 1
printf "SEQ=%d AP_RET2 apidx=%d idx=%d\n", $seq, $apidx, $eax
continue
end
set $rfidx = 0
break *0x10036cd0
commands
silent
set $seq = $seq + 1
set $rfidx = $rfidx + 1
set $m = *(unsigned int *)($esp + 4)
set $pnum = *(int *)($m + 0x8c)
set $nnum = *(int *)($m + 0x5c)
set $vnum = *(int *)($m + 0x9c)
printf "SEQ=%d RF_ENTRY rfidx=%d model=%#x nodes_num=%d points_num=%d vectors_num=%d\n", $seq, $rfidx, $m, $nnum, $pnum, $vnum
continue
end
break *0x1003718f
commands
silent
set $seq = $seq + 1
set $pnum2 = *(int *)($m + 0x8c)
set $nnum2 = *(int *)($m + 0x5c)
set $vnum2 = *(int *)($m + 0x9c)
printf "SEQ=%d RF_EXIT rfidx=%d model=%#x nodes_num=%d points_num=%d vectors_num=%d\n", $seq, $rfidx, $m, $nnum2, $pnum2, $vnum2
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

    container = "uned-round14-combined"
    O.stop_dbg_editor(container, state_dir)
    print(f"[r14combined] golden={GOLDEN}", flush=True)
    print(f"[r14combined] starting {container} ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        print(f"[r14combined] editor pid {pid}; attaching gdb ...", flush=True)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/r14c.gdb"],
                       input=GDB.format(pid=pid), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/r14c.gdb > /tmp/r14c.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/r14c.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[r14combined] attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        prev, quiet, deadline = -1, 0.0, time.monotonic() + DEADLINE
        while quiet < QUIET_FOR:
            if time.monotonic() > deadline:
                print(f"[r14combined] WARNING: gave up after {DEADLINE:.0f}s, {max(prev,0)} lines seen",
                      flush=True)
                break
            n = subprocess.run(["docker", "exec", container, "bash", "-c",
                                "wc -l < /tmp/r14c.log 2>/dev/null || true"],
                               capture_output=True, text=True).stdout.strip()
            n = int(n or 0)
            quiet = quiet + POLL if (n == prev and n > 0) else 0.0
            prev = n
            time.sleep(POLL)
        out = HERE.parent / "logs" / OUT_NAME
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/r14c.log"],
                                       capture_output=True).stdout)
        print(f"[r14combined] wrote {out} ({prev} lines seen)", flush=True)
        text = out.read_text(errors="replace")
        print(f"[r14combined] AP_CALL={text.count('AP_CALL ')} RF_ENTRY={text.count('RF_ENTRY ')} "
              f"RF_EXIT={text.count('RF_EXIT ')}", flush=True)
    finally:
        O.stop_dbg_editor(container, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
