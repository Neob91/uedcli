#!/usr/bin/env python3
r"""Round 11: live-capture the REAL `NodeFlags` byte for a SPECIFIC node, AT CAST TIME, during a
real Wanchai `LIGHT APPLY`, for rays belonging to a specific target surface -- extends round 10's
`linecheck_nearstate_recheck.py` technique (same NODE breakpoint, `0x17ce1cd`, `*(unsigned
char*)($esi+0x37)`) to audit round 8's ORIGINAL fix-bucket evidence (not the round-10 regression
side): `round11_decisive_node_order.py` found candidate fix-cases whose decisive node's OWNING
surface is processed LATER (by LightMap record index) than the ray's own record -- the same shape as
round 10's confirmed artifact (node 5394, `NF_BrightCorners` set in golden.dx's SAVED tree but 0x00
at the real ray's actual cast time). This script gets the ground truth for one representative shared
node (5409, decisive for 16 of the 239 candidate fix-cases) instead of relying on the record-index
heuristic alone.

Usage: round11_node_flags_at_cast.py [golden.dx] --isurf N --node M [--rays N]
  -> logs/round11-node-flags-at-cast.log
"""
from __future__ import annotations

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

GOLDEN = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else (
    ROOT / "_scratch/wanchai-relight-2026-08-29/golden.dx")
RAYS = 400
TARGET_ISURF = None
TARGET_NODE = None
for i, a in enumerate(sys.argv):
    if a == "--rays":
        RAYS = int(sys.argv[i + 1])
    if a == "--isurf":
        TARGET_ISURF = int(sys.argv[i + 1])
    if a == "--node":
        TARGET_NODE = int(sys.argv[i + 1])

if TARGET_ISURF is None or TARGET_NODE is None:
    print(__doc__)
    raise SystemExit(2)

PROJECT_DIR = ROOT / "_scratch/oracle-project"
CONTAINER = "uned-r11-node-flags-at-cast"
LOGF = HERE.parent / "logs" / "round11-node-flags-at-cast.log"

GDB = r"""
set pagination off
set confirm off
set height 0
set width 0
attach __PID__
handle SIGSEGV nostop noprint pass
handle SIGUSR1 nostop noprint pass
handle SIGUSR2 nostop noprint pass
handle SIGPIPE nostop noprint pass

set $cur_isurf = -1
set $active = 0
set $ray = 0
set $hits = 0
set $reached_target_isurf = 0

break *0x100a5043
commands
silent
set $cur_isurf = *(int*)($ebp+0xc)
if $cur_isurf == __ISURF__ && $reached_target_isurf == 0
  set $reached_target_isurf = 1
  printf "SURF_ENTER_TARGET isurf=%d ray_so_far=%d\n", $cur_isurf, $ray
end
continue
end

break *0x100a5a04
commands
silent
set $active = 1
set $ray = $ray + 1
continue
end

break *0x17ce1cd
commands
silent
if $active == 1
  set $cur_inode = *(int*)($ebp+0x18)
  if $cur_inode == __NODE__
    set $hits = $hits + 1
    printf "NODEFLAGS_AT_CAST ray=%d isurf=%d inode=%d nodeflags=0x%x\n", $ray, $cur_isurf, $cur_inode, *(unsigned char*)($esi+0x37)
  end
end
continue
end

break *0x100a5a07
commands
silent
if $active == 1
  set $active = 0
end
if $ray >= __RAYS__
  printf "TARGET_DONE hits=%d final_isurf=%d\n", $hits, $cur_isurf
  detach
  quit
end
continue
end

printf "ORACLE_ATTACHED\n"
continue
"""


def main() -> int:
    if not GOLDEN.exists():
        print(f"[node-flags-at-cast] golden not found: {GOLDEN}", file=sys.stderr)
        return 2
    if not PROJECT_DIR.exists():
        PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        (PROJECT_DIR / "uedcli.toml").write_text('game = "deusex"\n')

    O._ensure_dbg_image()
    project = config.load_project(str(PROJECT_DIR))
    user_config = config.load_user_config()
    mounts = resource_mounts(config.composed_search_dirs(project, user_config))
    state_dir = config.state_dir(project.root, create=True)

    O.stop_dbg_editor(CONTAINER, state_dir)
    print(f"[node-flags-at-cast] golden={GOLDEN} isurf={TARGET_ISURF} node={TARGET_NODE} "
          f"rays={RAYS}", flush=True)
    print(f"[node-flags-at-cast] starting {CONTAINER} ...", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(CONTAINER)
        print(f"[node-flags-at-cast] editor pid {pid}; attaching gdb ...", flush=True)
        gdb_script = (GDB.replace("__PID__", str(pid)).replace("__RAYS__", str(RAYS))
                      .replace("__ISURF__", str(TARGET_ISURF)).replace("__NODE__", str(TARGET_NODE)))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/r11nfac.gdb"],
                       input=gdb_script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/r11nfac.gdb > /tmp/r11nfac.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/r11nfac.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[node-flags-at-cast] attached; LIGHT APPLY ...", flush=True)
        drv.exec("LIGHT APPLY")
        deadline = time.monotonic() + 600.0
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                   "grep -c '^TARGET_DONE' /tmp/r11nfac.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                print("[node-flags-at-cast] TARGET_DONE seen", flush=True)
                break
            time.sleep(3.0)
        else:
            print("[node-flags-at-cast] WARNING: gave up waiting", flush=True)
        LOGF.parent.mkdir(parents=True, exist_ok=True)
        LOGF.write_bytes(subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/r11nfac.log"],
                                        capture_output=True).stdout)
        print(f"[node-flags-at-cast] wrote {LOGF}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
