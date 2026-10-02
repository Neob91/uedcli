#!/usr/bin/env python3
r"""Live GDB capture: editor's per-call `bspRepartition` A_entry/E_bsprefresh Verts/Points/Nodes,
TAGGED WITH THE CHILD NODE INDEX (`esp+8` at entry) — Wanchai, `wanchai-verts-points-residual-
independently`'s "identify the specific ~8 calls" follow-up.

WHY. `repart_stage_unatco.py` (reused for Wanchai as `wanchai-ed-repart-stage.log`) captures the
SAME 5 breakpoints but does NOT log the child index, so its 119 subtree groups can only be matched to
native's own 119 calls by SEQUENCE POSITION — which does not correspond (positional diff gave 100/119
"mismatches", almost certainly order noise: `collect_repartition_frontier`'s list_a/list_b vs the
editor's real List1/List2 may not enumerate in the same relative order even though `prepart_tree_
wanchai.py` confirms the underlying NODE INDICES and pre-repartition subtree CONTENTS correspond
1:1 between native and editor at this checkpoint). This capture adds `child=` to the A_entry line so
every group is directly attributable to a specific node index, letting native's per-call table
(`UEDCLI_REPART_PERCALL_VERTS`) be joined by CHILD IDENTITY instead of position.

Usage:  repart_stage_child_wanchai.py [golden.dx]   ->  logs/repart-stage-child-wanchai.log
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

GOLDEN = Path(sys.argv[1]) if len(sys.argv) > 1 else (ROOT / "_scratch/golden_wanchai_world.dx")
PROJECT_DIR = ROOT / "_scratch/oracle-project"
POLL, QUIET_FOR, DEADLINE = 2.0, 60.0, 2400.0

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
set $child = *(int *)($esp + 8)
printf "A_entry child=%d nodes=%d verts=%d points=%d surfs=%d\n", $child, *(int *)($m + 0x5c), *(int *)($m + 0x6c), *(int *)($m + 0x8c), *(int *)($m + 0x9c)
continue
end
break *0x1004a05f
commands
silent
printf "E_bsprefresh child=%d nodes=%d verts=%d points=%d surfs=%d\n", $child, *(int *)($m + 0x5c), *(int *)($m + 0x6c), *(int *)($m + 0x8c), *(int *)($m + 0x9c)
printf "STAGEEND\n"
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def _wait(container, needle, tries, log="/tmp/rscw.log"):
    for _ in range(tries):
        out = subprocess.run(["docker", "exec", container, "bash", "-c",
                              f"grep -c {needle} {log} 2>/dev/null || true"],
                             capture_output=True, text=True).stdout.strip()
        if out and out != "0":
            return True
        time.sleep(1.0)
    return False


def main():
    if not PROJECT_DIR.exists():
        PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        (PROJECT_DIR / "uedcli.toml").write_text('game = "deusex"\n')

    O._ensure_dbg_image()
    project = config.load_project(str(PROJECT_DIR))
    user_config = config.load_user_config()
    mounts = resource_mounts(config.composed_search_dirs(project, user_config))
    state_dir = config.state_dir(project.root, create=True)

    container = "uned-repartstagechild-wanchai"
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
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/rscw.gdb"],
                       input=GDB.format(pid=pid), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/rscw.gdb > /tmp/rscw.log 2>&1"], check=True)
        _wait(container, "ORACLE_ATTACHED", 120)
        print("attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        prev, quiet, deadline = -1, 0.0, time.monotonic() + DEADLINE
        while quiet < QUIET_FOR:
            if time.monotonic() > deadline:
                print(f"WARNING: gave up after {DEADLINE:.0f}s with {max(prev, 0)} groups seen",
                      flush=True)
                break
            n = subprocess.run(["docker", "exec", container, "bash", "-c",
                                "grep -c STAGEEND /tmp/rscw.log 2>/dev/null || true"],
                               capture_output=True, text=True).stdout.strip()
            n = int(n or 0)
            quiet = quiet + POLL if (n == prev and n > 0) else 0.0
            prev = n
            time.sleep(POLL)
        out = HERE.parent / "logs" / "repart-stage-child-wanchai.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/rscw.log"],
                                       capture_output=True).stdout)
        print(f"wrote {out}", flush=True)
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    main()
