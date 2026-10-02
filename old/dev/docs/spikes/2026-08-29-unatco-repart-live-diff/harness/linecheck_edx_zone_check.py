#!/usr/bin/env python3
r"""Round 7 follow-up: test the zone-transform hypothesis directly. `0x17ce1c5` loads `edx` from
`[ebp+0x10]` at the top of every per-node loop iteration; `0x17ce1d3` tests it (`test edx,edx`) to
decide whether to apply an indirect-call transform (`call *0x1819988`) before computing each plane
dot. Every port attempted this round always takes the "edx is null" path. This script reads the
LIVE value of edx for the first several shadow rays of UNATCO record 0's surface (`isurf=15`, whose
run is `Light70, Light24, Light25, Light54` -- Light70's rays matched the un-fixed formula's
sweep at 100% in an early check, Light24's did not), to see whether edx changes between lights
within the SAME surface (which would directly confirm or refute the hypothesis before any further
static reading).

Usage: linecheck_edx_zone_check.py [golden_unatco.dx] [--rays N]
  -> logs/linecheck-edx-zone-check.log
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
    ROOT / "_scratch/native-visgate-2026-08-29/golden_unatco_lit.dx")
RAYS = 40
TARGET_ISURF = 15
for i, a in enumerate(sys.argv):
    if a == "--rays":
        RAYS = int(sys.argv[i + 1])
    if a == "--isurf":
        TARGET_ISURF = int(sys.argv[i + 1])

PROJECT_DIR = ROOT / "_scratch/oracle-project"
CONTAINER = "uned-linecheck-edx-check"
LOGF = HERE.parent / "logs" / "linecheck-edx-zone-check.log"

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

set $armed_surf = 0
set $active = 0
set $ray = 0

break *0x100a5043
commands
silent
set $hit_isurf = *(int*)($ebp+0xc)
if $armed_surf == 0 && $hit_isurf == __ISURF__
  set $armed_surf = 1
  printf "SURF_ENTER isurf=%d\n", $hit_isurf

  break *0x100a5a04
  commands
  silent
  set $active = 1
  set $ray = $ray + 1
  printf "RAY_ENTER ray=%d\n", $ray
  continue
  end

  # right after edx is loaded from [ebp+0x10] at the TOP-LEVEL call's own frame (depth 1 only would
  # be ideal, but this fires at every loop iteration of every recursion depth too -- log all, the
  # first hit per ray is the depth-1 value)
  break *0x17ce1c8
  commands
  silent
  if $active == 1
    printf "  EDX ray=%d edx=0x%x ebp10=0x%x\n", $ray, $edx, *(int*)($ebp+0x10)
  end
  continue
  end

  break *0x100a5a07
  commands
  silent
  if $active == 1
    printf "RAY_RETURN ray=%d result=%d\n", $ray, $eax
    set $active = 0
  end
  if $ray >= __RAYS__
    printf "TARGET_DONE\n"
    detach
    quit
  end
  continue
  end
end
continue
end

printf "ORACLE_ATTACHED\n"
continue
"""


def main() -> int:
    if not GOLDEN.exists():
        print(f"[edx-check] golden not found: {GOLDEN}", file=sys.stderr)
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
    print(f"[edx-check] golden={GOLDEN} isurf={TARGET_ISURF} rays={RAYS}", flush=True)
    print(f"[edx-check] starting {CONTAINER} ...", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(CONTAINER)
        print(f"[edx-check] editor pid {pid}; attaching gdb ...", flush=True)
        gdb_script = GDB.replace("__PID__", str(pid)).replace("__ISURF__", str(TARGET_ISURF)).replace(
            "__RAYS__", str(RAYS))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/edx.gdb"],
                       input=gdb_script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/edx.gdb > /tmp/edx.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/edx.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[edx-check] attached; LIGHT APPLY ...", flush=True)
        drv.exec("LIGHT APPLY")
        deadline = time.monotonic() + 600.0
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                   "grep -c '^TARGET_DONE' /tmp/edx.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                print("[edx-check] TARGET_DONE seen", flush=True)
                break
            time.sleep(3.0)
        else:
            print("[edx-check] WARNING: gave up waiting", flush=True)
        LOGF.parent.mkdir(parents=True, exist_ok=True)
        LOGF.write_bytes(subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/edx.log"],
                                        capture_output=True).stdout)
        print(f"[edx-check] wrote {LOGF}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
