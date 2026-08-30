#!/usr/bin/env python3
r"""Live GDB capture, round 5: find a ray with MULTIPLE genuine crossings through `0x17ce190`
(round 3-4 identified this as the REAL recursive shadow-ray walker; round 4 pinned the crossing
formula `t'=de/(de-ds)` for the ONE ray traced so far, but that ray only crossed a single BSP plane
before resolving -- not enough to tell whether `0x17ce190`'s recursion structure alternates which of
`point1`/`point2` gets replaced by `mid` (matching `line_clear`'s near/far alternation) or whether
`point2` staying fixed (observed depth 1->2 for that one ray) is a genuine structural invariant.

This reuses round 3-4's proven breakpoint set (`CALL_ENTRY`/`CROSS_ENTRY`/`CROSS_T`/`MID`/
`RECURSE_CALL`/`EARLY_RETURN_A`/`EARLY_RETURN_B`, all at fixed offsets from `0x17ce190` -- confirmed
STABLE across separate editor restarts in rounds 3-4, so no live re-resolution needed here) but drops
the single-ray `px`/`py`/`pz` filter: arms on the FIRST call to `illuminateSurf` (whichever surface
that happens to be) and logs full per-ray recursion structure (depth-tagged) for the first N rays of
that surface, watching for any ray whose `CALL_ENTRY depth` reaches >= 3 (two or more real crossings).

Usage: linecheck_multicrossing_survey.py [golden.dx] [--rays N]
  -> logs/linecheck-multicrossing-survey.log
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
RAYS = 12
for i, a in enumerate(sys.argv):
    if a == "--rays":
        RAYS = int(sys.argv[i + 1])

PROJECT_DIR = ROOT / "_scratch/oracle-project"
CONTAINER = "uned-linecheck-multicrossing"
LOGF = HERE.parent / "logs" / "linecheck-multicrossing-survey.log"

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
set $active = 0
set $n = 0
set $ray = 0
set $armed_surf = 0
set $depth = 0
set $max_depth_seen = 0

break *0x100a5043
commands
silent
if $armed_surf == 0
  set $armed_surf = 1
  set $isurf = *(int*)($ebp+0xc)
  printf "SURF_ENTER isurf=%d\n", $isurf

  break *0x100a5a04
  commands
  silent
  set $active = 1
  set $ray = $ray + 1
  set $depth = 0
  set $max_depth_seen = 0
  set $px = *(float*)($esp+0x14)
  set $py = *(float*)($esp+0x18)
  set $pz = *(float*)($esp+0x1c)
  printf "RAY_ENTER ray=%d px=%.9g py=%.9g pz=%.9g\n", $ray, $px, $py, $pz
  continue
  end

  break *0x17ce1b4
  commands
  silent
  if $active == 1
    set $depth = $depth + 1
    if $depth > $max_depth_seen
      set $max_depth_seen = $depth
    end
    set $p1x = *(float*)($ebp+0x1c)
    set $p1y = *(float*)($ebp+0x20)
    set $p1z = *(float*)($ebp+0x24)
    set $p2x = *(float*)($ebp+0x28)
    set $p2y = *(float*)($ebp+0x2c)
    set $p2z = *(float*)($ebp+0x30)
    printf "  CALL_ENTRY ray=%d depth=%d point1=(%.9g,%.9g,%.9g) point2=(%.9g,%.9g,%.9g)\n", $ray, $depth, $p1x, $p1y, $p1z, $p2x, $p2y, $p2z
  end
  continue
  end

  break *0x17ce2ae
  commands
  silent
  if $active == 1
    set $A = *(float*)($ebp-0x8)
    set $B = *(float*)($ebp-0xc)
    printf "    CROSS_ENTRY ray=%d depth=%d A=%.9g B=%.9g\n", $ray, $depth, $A, $B
  end
  continue
  end

  break *0x17ce2e6
  commands
  silent
  if $active == 1
    set $t = $xmm4.v4_float[0]
    printf "    CROSS_T ray=%d depth=%d t=%.9g\n", $ray, $depth, $t
  end
  continue
  end

  break *0x17ce387
  commands
  silent
  if $active == 1
    set $midx = *(float*)($ebp-0x1c)
    set $midy = *(float*)($ebp-0x18)
    set $midz = *(float*)($ebp-0x14)
    printf "    MID ray=%d depth=%d mid=(%.9g,%.9g,%.9g)\n", $ray, $depth, $midx, $midy, $midz
  end
  continue
  end

  break *0x17ce3b4
  commands
  silent
  if $active == 1
    printf "    RECURSE_CALL ray=%d depth=%d\n", $ray, $depth
  end
  continue
  end

  break *0x17ce249
  commands
  silent
  if $active == 1
    printf "    EARLY_RETURN_A ray=%d depth=%d\n", $ray, $depth
    set $depth = $depth - 1
  end
  continue
  end

  break *0x17ce29c
  commands
  silent
  if $active == 1
    printf "    EARLY_RETURN_B ray=%d depth=%d\n", $ray, $depth
    set $depth = $depth - 1
  end
  continue
  end

  break *0x100a5a07
  commands
  silent
  if $active == 1
    printf "RAY_RETURN ray=%d result=%d max_depth=%d\n", $ray, $eax, $max_depth_seen
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
        print(f"[multicrossing] golden not found: {GOLDEN}", file=sys.stderr)
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
    print(f"[multicrossing] golden={GOLDEN} rays={RAYS}", flush=True)
    print(f"[multicrossing] starting {CONTAINER} ...", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(CONTAINER)
        print(f"[multicrossing] editor pid {pid}; attaching gdb ...", flush=True)
        gdb_script = GDB.replace("__PID__", str(pid)).replace("__RAYS__", str(RAYS))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/lmc.gdb"],
                       input=gdb_script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/lmc.gdb > /tmp/lmc.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/lmc.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[multicrossing] attached; LIGHT APPLY ...", flush=True)
        drv.exec("LIGHT APPLY")
        deadline = time.monotonic() + 600.0
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                   "grep -c '^TARGET_DONE' /tmp/lmc.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                print("[multicrossing] TARGET_DONE seen", flush=True)
                break
            time.sleep(3.0)
        else:
            print("[multicrossing] WARNING: gave up waiting", flush=True)
        LOGF.parent.mkdir(parents=True, exist_ok=True)
        LOGF.write_bytes(subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/lmc.log"],
                                        capture_output=True).stdout)
        print(f"[multicrossing] wrote {LOGF}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
