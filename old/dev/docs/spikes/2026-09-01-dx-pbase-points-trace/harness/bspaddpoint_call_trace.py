#!/usr/bin/env python3
r"""Live GDB capture: every `bspAddPoint` call (Editor.dll VA `0x10035430`, resolved this round from
the shared `UModel` vtable at `0x100cf5d4+0x1f4` -- confirmed against the already-known `bspRefresh`
slot `+0x200 -> 0x10036cd0`) during a full `MAP REBUILD` of `DX.dx`'s trunk: the `Model` this-pointer
(`ecx`, moved to `esi` at entry+0x2d), the input `FVector` (`[ebp+8]`), the `Exact` flag (`[ebp+0x10]`
before it gets overwritten with an epsilon), and the RETURNED pool index (`eax`) at either of this
function's two `ret 0xc` epilogues (`0x100354ce`, `0x100355a7` -- a third `ret` seen in the same
disassembly window, `0x1003567b ret 0x18`, has the wrong arg-count for this 3-stack-arg signature and
was excluded as belonging to a different function).

WHY. `points_pool_refresh_trace.py` (this same round) proved the reordering that makes `DX.dx`'s
`Brush3` (`i_actor=2`) `p_base` diverge from native happens BEFORE the world's first `bspRefresh`
call -- the pre-compaction pool at that call's ENTRY already has the brush's 5 base points (A,E,H,G,F
in golden's final order) at raw pool positions [0,4,5,6,7], not the [0,1,2,3,4]-with-G,F,H-shuffled
order a naive "walk authored polygon Origins in order" reconstruction predicts. Every later
`bspRefresh` call preserves the survivors' relative order (proven directly: call1's AFTER and call5's
AFTER both reproduce this same relative order, and call5's AFTER is byte-identical to golden's real
final `Points` array). So the ACTUAL reordering-determining event is the original `bspAddPoint` call
SEQUENCE during Brush3's own CSG processing -- this script captures it directly.

Usage:  bspaddpoint_call_trace.py [golden.dx]
  -> logs/bspaddpoint-call-trace.log
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

GOLDEN = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    ROOT / "_scratch/dx-pbase-points-trace/golden_dx.dx")
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
set $callidx = 0
break *0x1003545d
commands
silent
set $callidx = $callidx + 1
set $model = $esi
set $arg1 = *(unsigned int *)($ebp + 8)
set $arg2 = *(unsigned int *)($ebp + 0xc)
set $arg3 = *(unsigned int *)($ebp + 0x10)
set $x = *(float *)$arg1
set $y = *(float *)($arg1 + 4)
set $z = *(float *)($arg1 + 8)
set $x2 = *(float *)$arg2
set $y2 = *(float *)($arg2 + 4)
set $z2 = *(float *)($arg2 + 8)
printf "CALL callidx=%d ecx=%#x model=%#x ebp=%#x arg1=%#x arg2=%#x arg3=%#x x=%.6f y=%.6f z=%.6f x2=%.6f y2=%.6f z2=%.6f\n", $callidx, $ecx, $model, $ebp, $arg1, $arg2, $arg3, $x, $y, $z, $x2, $y2, $z2
continue
end
break *0x100354ce
commands
silent
printf "RET1 callidx=%d idx=%d\n", $callidx, $eax
continue
end
break *0x100355a7
commands
silent
printf "RET2 callidx=%d idx=%d\n", $callidx, $eax
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

    container = "uned-dxaddpoint"
    O.stop_dbg_editor(container, state_dir)
    print(f"[dxap] golden={GOLDEN}", flush=True)
    print(f"[dxap] starting {container} ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        print(f"[dxap] editor pid {pid}; attaching gdb ...", flush=True)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/dxap.gdb"],
                       input=GDB.format(pid=pid), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/dxap.gdb > /tmp/dxap.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/dxap.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[dxap] attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        prev, quiet, deadline = -1, 0.0, time.monotonic() + DEADLINE
        while quiet < QUIET_FOR:
            if time.monotonic() > deadline:
                print(f"[dxap] WARNING: gave up after {DEADLINE:.0f}s, {max(prev,0)} lines seen",
                      flush=True)
                break
            n = subprocess.run(["docker", "exec", container, "bash", "-c",
                                "wc -l < /tmp/dxap.log 2>/dev/null || true"],
                               capture_output=True, text=True).stdout.strip()
            n = int(n or 0)
            quiet = quiet + POLL if (n == prev and n > 0) else 0.0
            prev = n
            time.sleep(POLL)
        out = HERE.parent / "logs" / "bspaddpoint-call-trace.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/dxap.log"],
                                       capture_output=True).stdout)
        print(f"[dxap] wrote {out} ({prev} lines seen)", flush=True)
        text = out.read_text(errors="replace")
        print(f"[dxap] CALL count = {text.count('CALL ')}, RET1 = {text.count('RET1 ')}, "
              f"RET2 = {text.count('RET2 ')}", flush=True)
    finally:
        O.stop_dbg_editor(container, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
