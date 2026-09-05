#!/usr/bin/env python3
r"""Log every shadow ray `LIGHT APPLY` casts for one surface: its two endpoints and its RESULT.

Companion to `nodeflags_at_lightapply.py`. Breaks on `illuminateSurf` (`0x100a5043`) entering with
`iSurf == --isurf`, then on the instruction AFTER the per-lumel `call [eax+0x58]`
(`0x100a5a04` + 3 = `0x100a5a07`), where `eax` is the walker's return (non-zero = CLEAR) and the
caller's argument block is still on the stack: `esp+0x08..0x10` = point1 (the LIGHT), `esp+0x14..0x1c`
= point2 (the lumel).

Comparing the logged CLEAR pattern against the bit-plane the same build stored tells you whether the
run reproduces the golden's lighting, and exactly which rays disagree with the native port.

Usage: ray_results_at_lightapply.py <built.dx> --isurf N [--rays N] [--out log]
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

PROJECT_DIR = ROOT / "_scratch/oracle-project"
CONTAINER = "uned-lightapply-rays"

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

set $armed = 0
set $dumped = 0
set $n = 0

break *0x100a5043
commands
silent
set $hit = *(int*)($ebp+0xc)
if $armed == 0 && $hit == __ISURF__
  set $armed = 1
  printf "SURF_ENTER isurf=%d\n", $hit
  break *0x17ce193
  commands
  silent
  if $dumped == 0
    set $dumped = 1
    set $model = *(unsigned int*)($ebp+0x0c)
    set $nodes = *(unsigned int*)($model+0x58)
    set $i = 0
    while $i < __NODES__
      printf "NODE %d flags=0x%02x nv=%d\n", $i, *(unsigned char*)($nodes+$i*64+0x37), *(unsigned char*)($nodes+$i*64+0x36)
      set $i = $i + 1
    end
  end
  continue
  end

  break *0x100a5a04
  commands
  silent
  set $n = $n + 1
  printf "ARGS %d light=(%.7g,%.7g,%.7g) lumel=(%.7g,%.7g,%.7g)\n", $n, *(float*)($esp+0x08), *(float*)($esp+0x0c), *(float*)($esp+0x10), *(float*)($esp+0x14), *(float*)($esp+0x18), *(float*)($esp+0x1c)
  continue
  end

  break *0x100a5a07
  commands
  silent
  printf "RESULT %d clear=%d\n", $n, $eax
  if $n >= __RAYS__
    printf "TARGET_DONE\n"
    detach
    quit
  end
  continue
  end
  continue
end
continue
end

printf "ORACLE_ATTACHED\n"
continue
"""


def main() -> int:
    built = Path(sys.argv[1]).resolve()
    isurf = None
    rays = 2000
    nnodes = 0
    out = HERE.parent / "logs" / "ray-results-at-lightapply.log"
    for i, a in enumerate(sys.argv):
        if a == "--isurf":
            isurf = int(sys.argv[i + 1])
        if a == "--rays":
            rays = int(sys.argv[i + 1])
        if a == "--nodes":
            nnodes = int(sys.argv[i + 1])
        if a == "--out":
            out = Path(sys.argv[i + 1]).resolve()
    if not built.exists() or isurf is None:
        print(__doc__)
        return 2

    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    (PROJECT_DIR / "uedcli.toml").write_text('game = "deusex"\n')
    O._ensure_dbg_image()
    project = config.load_project(str(PROJECT_DIR))
    mounts = resource_mounts(config.composed_search_dirs(project, config.load_user_config()))
    state_dir = config.state_dir(project.root, create=True)

    O.stop_dbg_editor(CONTAINER, state_dir)
    print(f"[rays] {built.name} isurf={isurf} rays={rays}; starting {CONTAINER}", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /work/built.dx"],
                       input=built.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/built.dx')}")
        time.sleep(3.0)
        if "--rebuild-first" in sys.argv:
            # The golden is built MAP IMPORT -> MAP REBUILD -> LIGHT APPLY. A plain MAP LOAD leaves
            # different transient node state than a fresh rebuild does, which is exactly what this
            # probe is testing, so allow re-running the rebuild before lighting.
            print("[rays] MAP REBUILD ...", flush=True)
            drv.exec("MAP REBUILD")
            time.sleep(20.0)
        batch = "--batch" in sys.argv
        pid = O._editor_pid(CONTAINER)
        script = (GDB.replace("__PID__", str(pid)).replace("__ISURF__", str(isurf))
                  .replace("__RAYS__", str(rays)).replace("__NODES__", str(nnodes)))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/rays.gdb"],
                       input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/rays.gdb > /tmp/rays.log 2>&1"], check=True)
        for _ in range(120):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/rays.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        if batch:
            # The golden runs MAP REBUILD -> LIGHT APPLY -> MAP SAVE inside ONE `EXEC` batch, with
            # no editor tick (and so no viewport redraw / `OccludeBsp` recompute of the transient
            # node flags) between them. Reproduce that shape, not a hand-typed sequence.
            print("[rays] attached; batched MAP REBUILD -> LIGHT APPLY -> MAP SAVE ...", flush=True)
            drv.begin_script()
            drv.exec("MAP REBUILD")
            drv.light_apply()
            saved = "/work/probe_out.dx"
            drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
            drv.run_script(produces=saved, timeout=1800.0)
        else:
            print("[rays] attached; LIGHT APPLY ...", flush=True)
            drv.exec("LIGHT APPLY")
        deadline = time.monotonic() + 1800.0
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                   "grep -c '^TARGET_DONE' /tmp/rays.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                break
            time.sleep(5.0)
        else:
            print("[rays] WARNING: gave up waiting", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/rays.log"],
                                       capture_output=True).stdout)
        print(f"[rays] wrote {out}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
