#!/usr/bin/env python3
r"""Live GDB capture: trace the SPECIFIC known-mismatching ray (`rec=14 light=Light42 v=3 u=0` on
the Wanchai golden) through the editor's REAL recursive shadow-ray walker
(`Editor.dll`-resolved target, disassembled by `linecheck_target_disasm.py` at `target+0x5b0`), to
pin the exact per-node formula that `line-clear-shadow-ray-algorithm-gap-found-real/overview.md`'s
Finding D left undecoded.

Exact ray endpoints (from `line_clear_algorithm_check.py`, this session, current golden/native.dx):
    p_golden     = (1760.0, 1148.125, 191.87503051757812)     # the lumel position ("start" arg)
    light_loc    = (1570.3885498046875, 1147.6253662109375, 283.4671325683594)  # ("end" arg)
native says BLOCKED (bit=0), the editor's real golden says CLEAR (bit=1).

ONE gdb session, ONE pass: a breakpoint at the outer call site (`0x100a5a04`, fixed -- Editor.dll
loads unrelocated) is conditioned on the pushed (start) point matching the target ray; only once
that fires does it resolve the recursive walker's real (relocatable) load address (`target+0x5b0`,
same method as `linecheck_target_disasm.py`) and set TWO FURTHER breakpoints at fixed OFFSETS from
that resolved base -- `+0x92` (right after both `front_start=ds>=0`/`front_end=de>=0` flags are
computed, this session's static hand-decode of `linecheck-target-disasm.log`) and `+0xd5` (right
before the recursive call, once the crossing-point `mid` has been computed into xmm2) -- gated by an
`$active` flag so only nodes visited by THIS ONE ray's recursion are logged, not any other
concurrent/later ray's calls through the same code.

Usage: linecheck_singlestep_rec14.py [golden.dx]
  -> logs/linecheck-singlestep-rec14.log
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

PROJECT_DIR = ROOT / "_scratch/oracle-project"
CONTAINER = "uned-linecheck-singlestep"
LOGF = HERE.parent / "logs" / "linecheck-singlestep-rec14.log"

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
set $hits = 0
set $armed = 0

break *0x100a5a04
commands
silent
set $px = *(float*)($esp+0x14)
set $py = *(float*)($esp+0x18)
set $pz = *(float*)($esp+0x1c)
if $px > 1759.999 && $px < 1760.001 && $py > 1148.10 && $py < 1148.15 && $pz > 191.8 && $pz < 191.95
  set $active = 1
  printf "TARGET_ENTER px=%.9g py=%.9g pz=%.9g\n", $px, $py, $pz
  if $armed == 0
    set $model = $ecx
    set $vtbl = *(int *)$model
    set $target = *(int *)($vtbl + 0x58)
    set $inner = $target + 0x5b0
    printf "RESOLVED model=0x%x target=0x%x inner=0x%x\n", $model, $target, $inner
    break *$inner+0x92
    commands
    silent
    if $active == 1
      set $hits = $hits + 1
      set $ds = $xmm1.v4_float[0]
      set $de = $xmm3.v4_float[0]
      set $nodeaddr = $esi
      set $nf = *(unsigned char*)($esi+0x37)
      set $ifront = *(int*)($esi+0x20)
      set $iback = *(int*)($esi+0x24)
      set $nv = *(unsigned short*)($esi+0x1c)
      printf "NODE hit=%d addr=0x%x nf=%d nv=%d ifront=%d iback=%d ds=%.9g de=%.9g ecx=%d eax=%d\n", $hits, $nodeaddr, $nf, $nv, $ifront, $iback, $ds, $de, $ecx, $eax
    end
    continue
    end
    break *$inner+0xd5
    commands
    silent
    if $active == 1
      set $midx = $xmm2.v4_float[0]
      set $midy = $xmm2.v4_float[1]
      set $midz = $xmm2.v4_float[2]
      printf "MID hit=%d mid=%.9g,%.9g,%.9g pushed_child=%d pushed_state=%d\n", $hits, $midx, $midy, $midz, *(int*)($esp+4), *(int*)$esp
    end
    continue
    end
    set $armed = 1
  end
end
continue
end

break *0x100a5a07
commands
silent
if $active == 1
  printf "TARGET_RETURN result=%d\n", $eax
  set $active = 0
  set $n = $n + 1
end
if $n >= 1
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
        print(f"[singlestep] golden not found: {GOLDEN}", file=sys.stderr)
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
    print(f"[singlestep] golden={GOLDEN}", flush=True)
    print(f"[singlestep] starting {CONTAINER} ...", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(CONTAINER)
        print(f"[singlestep] editor pid {pid}; attaching gdb ...", flush=True)
        gdb_script = GDB.replace("__PID__", str(pid))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/ls.gdb"],
                       input=gdb_script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/ls.gdb > /tmp/ls.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/ls.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[singlestep] attached; LIGHT APPLY ...", flush=True)
        drv.exec("LIGHT APPLY")
        deadline = time.monotonic() + 1800.0
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                   "grep -c '^TARGET_DONE' /tmp/ls.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                print("[singlestep] TARGET_DONE seen", flush=True)
                break
            time.sleep(2.0)
        else:
            print("[singlestep] WARNING: gave up waiting", flush=True)
        LOGF.parent.mkdir(parents=True, exist_ok=True)
        LOGF.write_bytes(subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/ls.log"],
                                        capture_output=True).stdout)
        print(f"[singlestep] wrote {LOGF}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
