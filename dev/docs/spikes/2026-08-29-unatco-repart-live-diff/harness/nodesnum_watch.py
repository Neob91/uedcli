#!/usr/bin/env python3
r"""Live GDB capture: hardware watchpoint on the persistent Model's own `Nodes.Num` field
(`+0x5c`), across a full `MAP REBUILD`, to find the exact instruction(s) that change it.

WHY. `repart_addnode_model_trace.py` (2026-08-30) found bspAddNode's own `Model` argument
matches bspRepartition's `Model` argument (persistent, not a scratch object) with ZERO mismatches
across 29 node-adds for one subtree call (child=6108) -- directly refuting the "nodes accumulate in
a separate scratch UModel" reading of the earlier `bspBuild`/`bspRefresh` disassembly
(`native-materialize-findings.md`, "bspRepartition's per-subtree call builds into a SEPARATE...").
But the SAME capture showed the persistent Model's own `Nodes.Num` (`+0x5c`) reads FLAT at 6314
(the golden final value) across at least 42 consecutive subtree calls, even though real
bspAddNode writes are landing in that same array underneath. So nodes land directly in the
persistent Model, but `Num` does not grow per-add -- something bumps it separately, or not at all
during the subtree loop. This watches the field directly to find out.

MECHANISM: set a hardware watchpoint on `*(int*)(Model+0x5c)` as soon as Model's address is known
(captured from the first `bspRepartition` (`Editor.dll 0x10049fc0`) hit), then log every write
(GDB's own "Old value = X / New value = Y") plus a short backtrace, for the whole `MAP REBUILD`.

Usage:  nodesnum_watch.py [golden.dx]
  -> logs/nodesnum-watch.log
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
    ROOT / "_scratch/bsp-parity-proj/golden_unatco_control.dx")
PROJECT_DIR = ROOT / "_scratch/oracle-project"
POLL, QUIET_FOR, DEADLINE = 2.0, 20.0, 2400.0

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
set $wpset = 0
break *0x10049fc0
commands
silent
set $callidx = $callidx + 1
if $wpset == 0
  set $wpset = 1
  set $m = *(unsigned int *)($esp + 4)
  printf "PERSISTENT_MODEL model=%#x nodesnum0=%d\n", $m, *(int *)($m + 0x5c)
  watch *(int*)($m + 0x5c)
  commands
  printf "WATCHHIT callidx=%d pc=%#x\n", $callidx, $pc
  bt 3
  continue
  end
end
printf "CALL idx=%d\n", $callidx
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

    container = "uned-nodesnum-watch"
    O.stop_dbg_editor(container, state_dir)
    print(f"[nnwatch] golden={GOLDEN}", flush=True)
    print(f"[nnwatch] starting {container} ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        print(f"[nnwatch] editor pid {pid}; attaching gdb ...", flush=True)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/nnw.gdb"],
                       input=GDB.format(pid=pid), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/nnw.gdb > /tmp/nnw.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/nnw.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[nnwatch] attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        prev, quiet, deadline = -1, 0.0, time.monotonic() + DEADLINE
        while quiet < QUIET_FOR:
            if time.monotonic() > deadline:
                print(f"[nnwatch] WARNING: gave up after {DEADLINE:.0f}s, {max(prev,0)} lines seen",
                      flush=True)
                break
            n = subprocess.run(["docker", "exec", container, "bash", "-c",
                                "wc -l < /tmp/nnw.log 2>/dev/null || true"],
                               capture_output=True, text=True).stdout.strip()
            n = int(n or 0)
            quiet = quiet + POLL if (n == prev and n > 0) else 0.0
            prev = n
            time.sleep(POLL)
        out = HERE.parent / "logs" / "nodesnum-watch.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/nnw.log"],
                                       capture_output=True).stdout)
        print(f"[nnwatch] wrote {out} ({prev} lines seen)", flush=True)
        text = out.read_text(errors="replace")
        print(f"[nnwatch] WATCHHIT count = {text.count('WATCHHIT')}", flush=True)
    finally:
        O.stop_dbg_editor(container, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
