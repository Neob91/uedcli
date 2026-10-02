#!/usr/bin/env python3
r"""Round 7 pass 1: cheap outcome-only scan to locate a genuinely CLEAR (`result=1`) shadow ray.

Round 6's state trace only sampled 6 rays, all on the SAME surface's first row, and all came back
BLOCKED -- it never exercised the clear-return code path (the non-solid/empty terminal handling,
`0x17ce456`/`0x17ce464`+), which is exactly what round 7 needs to pin the `edi` state formula and
terminal polarity properly.

This scans across the first `--surfs` surfaces (`illuminateSurf` entries) and, within each, the
first `--rays-per-surf` shadow rays, logging ONLY `RAY_ENTER`/`RAY_RETURN` (no per-node detail --
keeps this fast and the log small) tagged with a running global ray counter and the surf it belongs
to, so a downstream targeted deep-trace can skip straight to a known-clear (surf, ray-within-surf)
pair.

Usage: linecheck_find_clear_ray.py [golden.dx] [--surfs N] [--rays-per-surf N]
  -> logs/linecheck-find-clear-ray.log
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
SURFS = 40
RAYS_PER_SURF = 40
for i, a in enumerate(sys.argv):
    if a == "--surfs":
        SURFS = int(sys.argv[i + 1])
    if a == "--rays-per-surf":
        RAYS_PER_SURF = int(sys.argv[i + 1])

PROJECT_DIR = ROOT / "_scratch/oracle-project"
CONTAINER = "uned-linecheck-find-clear"
LOGF = HERE.parent / "logs" / "linecheck-find-clear-ray.log"

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

set $surf_n = 0
set $cur_isurf = -1
set $ray_in_surf = 0
set $active = 0

break *0x100a5043
commands
silent
set $isurf = *(int*)($ebp+0xc)
if $isurf != $cur_isurf
  set $cur_isurf = $isurf
  set $ray_in_surf = 0
  set $surf_n = $surf_n + 1
  printf "SURF_ENTER n=%d isurf=%d\n", $surf_n, $isurf
end
continue
end

break *0x100a5a04
commands
silent
if $surf_n >= 1 && $surf_n <= __SURFS__ && $ray_in_surf < __RAYSPERSURF__
  set $ray_in_surf = $ray_in_surf + 1
  set $active = 1
end
continue
end

break *0x100a5a07
commands
silent
if $active == 1
  printf "RESULT surf_n=%d isurf=%d ray_in_surf=%d result=%d\n", $surf_n, $cur_isurf, $ray_in_surf, $eax
  set $active = 0
end
if $surf_n > __SURFS__
  printf "TARGET_DONE\n"
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
        print(f"[find-clear] golden not found: {GOLDEN}", file=sys.stderr)
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
    print(f"[find-clear] golden={GOLDEN} surfs={SURFS} rays_per_surf={RAYS_PER_SURF}", flush=True)
    print(f"[find-clear] starting {CONTAINER} ...", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(CONTAINER)
        print(f"[find-clear] editor pid {pid}; attaching gdb ...", flush=True)
        gdb_script = GDB.replace("__PID__", str(pid)).replace("__SURFS__", str(SURFS)).replace(
            "__RAYSPERSURF__", str(RAYS_PER_SURF))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/lfc.gdb"],
                       input=gdb_script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/lfc.gdb > /tmp/lfc.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/lfc.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[find-clear] attached; LIGHT APPLY ...", flush=True)
        drv.exec("LIGHT APPLY")
        deadline = time.monotonic() + 600.0
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                   "grep -c '^TARGET_DONE' /tmp/lfc.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                print("[find-clear] TARGET_DONE seen", flush=True)
                break
            time.sleep(3.0)
        else:
            print("[find-clear] WARNING: gave up waiting", flush=True)
        LOGF.parent.mkdir(parents=True, exist_ok=True)
        LOGF.write_bytes(subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/lfc.log"],
                                        capture_output=True).stdout)
        print(f"[find-clear] wrote {LOGF}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
