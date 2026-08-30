#!/usr/bin/env python3
r"""Live GDB capture, round 3: diagnose WHY the target ray (`rec=14 Light42 v=3 u=0`) never reaches
the recursive walker (`inner=target+0x5b0`) that round 1's un-gated, first-N-hits capture proved is a
real, reachable, self-recursive function.

Round 2 (surf-gated, `linecheck_singlestep_rec14_v2.py`) successfully reached the target ray (matched
`px/py/pz` exactly) but then observed: the dispatcher's own `Nodes.Num` check (`target+0x47`,
`edi+0x5c`) read a NON-ZERO count (23808) -- so it does NOT take the "empty model" short path
(`target+0x559`) -- yet NEITHER that short path NOR `inner` (`target+0x5b0`) was ever reached before
the call returned. Some OTHER early-exit branch inside the dispatcher (there are several visible in
the 300-instruction dispatcher dump already captured -- `target+0x3a7`≈`0x17ce867`,
`target+0x3c8`≈`0x17ce888`, and possibly others past that dump's range) must be taken instead.

This round removes the single-ray filter and instead logs the dispatch OUTCOME (which of the four
known landmarks -- short-path/inner/0x17ce867/0x17ce888 -- is reached, or none of them within a
bounded single-step budget) for the first N rays of the SAME surface (`iSurf=4556`), to see whether
skipping the recursive walker is ray-specific (e.g. a distance/attenuation shortcut) or general to
this surface.

Usage: linecheck_singlestep_rec14_v3.py [golden.dx] [--isurf N] [--limit N]
  -> logs/linecheck-singlestep-rec14-v3.log
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
ISURF = 4556
LIMIT = 20
for i, a in enumerate(sys.argv):
    if a == "--isurf":
        ISURF = int(sys.argv[i + 1])
    if a == "--limit":
        LIMIT = int(sys.argv[i + 1])

PROJECT_DIR = ROOT / "_scratch/oracle-project"
CONTAINER = "uned-linecheck-singlestep-v3"
LOGF = HERE.parent / "logs" / "linecheck-singlestep-rec14-v3.log"

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
set $armed_ray = 0
set $outcome = 0

break *0x100a5043
commands
silent
set $isurf = *(int*)($ebp+0xc)
if $isurf == __ISURF__ && $armed_surf == 0
  set $armed_surf = 1
  printf "SURF_ENTER isurf=%d\n", $isurf

  break *0x100a5a04
  commands
  silent
  set $active = 1
  set $ray = $ray + 1
  set $outcome = 0
  set $px = *(float*)($esp+0x14)
  set $py = *(float*)($esp+0x18)
  set $pz = *(float*)($esp+0x1c)
  printf "RAY_ENTER ray=%d px=%.9g py=%.9g pz=%.9g\n", $ray, $px, $py, $pz
  if $armed_ray == 0
    set $model = $ecx
    set $vtbl = *(int *)$model
    set $target = *(int *)($vtbl + 0x58)
    set $inner = $target + 0x5b0

    break *$target+0x47
    commands
    silent
    if $active == 1
      printf "  nodes_num=%d\n", *(int*)($edi+0x5c)
    end
    continue
    end

    break *$target+0x559
    commands
    silent
    if $active == 1
      set $outcome = 1
      printf "  OUTCOME=short_path_empty_model\n"
    end
    continue
    end

    break *$inner
    commands
    silent
    if $active == 1
      set $outcome = 2
      printf "  OUTCOME=reached_inner_walker\n"
    end
    continue
    end

    break *0x17ce867
    commands
    silent
    if $active == 1 && $outcome == 0
      set $outcome = 3
      printf "  OUTCOME=early_exit_0x17ce867\n"
    end
    continue
    end

    break *0x17ce888
    commands
    silent
    if $active == 1 && $outcome == 0
      set $outcome = 4
      printf "  OUTCOME=nan_guard_0x17ce888\n"
    end
    continue
    end

    set $armed_ray = 1
  end
  continue
  end

  break *0x100a5a07
  commands
  silent
  if $active == 1
    printf "RAY_RETURN ray=%d result=%d outcome=%d\n", $ray, $eax, $outcome
    set $active = 0
    if $outcome == 0
      printf "  ** outcome never classified -- some OTHER exit was taken **\n"
    end
  end
  if $ray >= __LIMIT__
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
        print(f"[singlestep-v3] golden not found: {GOLDEN}", file=sys.stderr)
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
    print(f"[singlestep-v3] golden={GOLDEN} isurf={ISURF} limit={LIMIT}", flush=True)
    print(f"[singlestep-v3] starting {CONTAINER} ...", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(CONTAINER)
        print(f"[singlestep-v3] editor pid {pid}; attaching gdb ...", flush=True)
        gdb_script = GDB.replace("__PID__", str(pid)).replace("__ISURF__", str(ISURF)).replace(
            "__LIMIT__", str(LIMIT))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/ls3.gdb"],
                       input=gdb_script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/ls3.gdb > /tmp/ls3.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/ls3.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[singlestep-v3] attached; LIGHT APPLY ...", flush=True)
        drv.exec("LIGHT APPLY")
        deadline = time.monotonic() + 600.0
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                   "grep -c '^TARGET_DONE' /tmp/ls3.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                print("[singlestep-v3] TARGET_DONE seen", flush=True)
                break
            time.sleep(3.0)
        else:
            print("[singlestep-v3] WARNING: gave up waiting", flush=True)
        LOGF.parent.mkdir(parents=True, exist_ok=True)
        LOGF.write_bytes(subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/ls3.log"],
                                        capture_output=True).stdout)
        print(f"[singlestep-v3] wrote {LOGF}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
