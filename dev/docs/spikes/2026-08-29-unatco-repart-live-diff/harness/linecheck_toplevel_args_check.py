#!/usr/bin/env python3
r"""Round 8: live-verify the TOP-LEVEL (non-recursive) call's exact argument layout into the real
shadow-ray walker `0x17ce190`.

Motivation: a fresh, from-scratch static byte-accounting of `illuminateSurf`'s call-site push
sequence (`Editor.dll 0x100a598b`-`0x100a5a04`, re-disassembled this round via `rdis.py dis Editor
0x100a5900 0x180`) only accounts for 0x30 bytes of pushed/reserved argument space, but the
RECURSIVE self-call inside `0x17ce190` (`0x17ce363`-`0x17ce3b4`) pushes 0x34 bytes for the same
7-argument shape (5 dwords + 2 Vec3s). That's a 4-byte (one dword) discrepancy between the two call
sites' apparent argument counts -- either the top-level call passes one fewer real argument (and the
callee's `[ebp+0x38]` extra_flags slot reads stale/adjacent stack data on the ROOT call only), or the
static byte-accounting above has an error. Static reasoning alone was not trusted (this investigation's
own repeated lesson) -- this script settles it live.

Two breakpoints:
  1. `0x100a5a04` (the `call [eax+0x58]` instruction itself, in illuminateSurf's per-lumel loop):
     dumps the caller's own prepared stack (`esp+0x00` .. `esp+0x37`) as raw dwords/floats, PLUS
     eax/ecx/edx, right before the call executes.
  2. `0x17ce193` (`0x17ce190`+3, right after `mov ebp,esp`, before the prologue touches anything):
     dumps every one of the callee's own argument slots (`[ebp+0x08]`..`[ebp+0x38]`) as the callee
     itself will read them -- the ground truth for what the algorithm actually receives.

Gated on a specific `isurf` (record 3 / isurf=1, Wanchai's Light391 problem case from this round's
offline sweep) via the surf-gate technique (`illuminateSurf` per-surface entry, `0x100a5010`, `iSurf`
at `[ebp+0xc]` -- confirmed live in round 3).

Usage: linecheck_toplevel_args_check.py [golden.dx] [--isurf N] [--calls N]
  -> logs/linecheck-toplevel-args-check.log
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
CALLS = 6
TARGET_ISURF = 1
for i, a in enumerate(sys.argv):
    if a == "--calls":
        CALLS = int(sys.argv[i + 1])
    if a == "--isurf":
        TARGET_ISURF = int(sys.argv[i + 1])

PROJECT_DIR = ROOT / "_scratch/oracle-project"
CONTAINER = "uned-linecheck-toplevel-args"
LOGF = HERE.parent / "logs" / "linecheck-toplevel-args-check.log"

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
set $n = 0

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
  set $n = $n + 1
  printf "CALL n=%d caller_eax(vtbl)=0x%x caller_ecx=0x%x caller_edx=0x%x\n", $n, $eax, $ecx, $edx
  printf "  esp+00(E outptr)=0x%x\n", *(unsigned int*)($esp+0x00)
  printf "  esp+04           =0x%x\n", *(unsigned int*)($esp+0x04)
  printf "  esp+08 f=%.6g\n", *(float*)($esp+0x08)
  printf "  esp+0c f=%.6g\n", *(float*)($esp+0x0c)
  printf "  esp+10 f=%.6g\n", *(float*)($esp+0x10)
  printf "  esp+14 f=%.6g\n", *(float*)($esp+0x14)
  printf "  esp+18 f=%.6g\n", *(float*)($esp+0x18)
  printf "  esp+1c f=%.6g\n", *(float*)($esp+0x1c)
  printf "  esp+20           =0x%x\n", *(unsigned int*)($esp+0x20)
  printf "  esp+24           =0x%x\n", *(unsigned int*)($esp+0x24)
  printf "  esp+28           =0x%x\n", *(unsigned int*)($esp+0x28)
  printf "  esp+2c           =0x%x\n", *(unsigned int*)($esp+0x2c)
  printf "  esp+30           =0x%x\n", *(unsigned int*)($esp+0x30)
  continue
  end

  break *0x17ce193
  commands
  silent
  printf "ENTRY n=%d ebp08(E)=0x%x ebp0c(D)=0x%x ebp10(C)=0x%x ebp14(B)=0x%x ebp18(A/inode)=%d\n", $n, *(unsigned int*)($ebp+0x08), *(unsigned int*)($ebp+0x0c), *(unsigned int*)($ebp+0x10), *(unsigned int*)($ebp+0x14), *(int*)($ebp+0x18)
  printf "  point1(ebp1c,20,24)=(%.6g,%.6g,%.6g)\n", *(float*)($ebp+0x1c), *(float*)($ebp+0x20), *(float*)($ebp+0x24)
  printf "  point2(ebp28,2c,30)=(%.6g,%.6g,%.6g)\n", *(float*)($ebp+0x28), *(float*)($ebp+0x2c), *(float*)($ebp+0x30)
  printf "  ebp34(edi_in)=0x%x ebp38(extra_flags)=0x%x\n", *(unsigned int*)($ebp+0x34), *(unsigned int*)($ebp+0x38)
  if $n >= __CALLS__
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
    if not GOLDEN.exists():
        print(f"[toplevel-args] golden not found: {GOLDEN}", file=sys.stderr)
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
    print(f"[toplevel-args] golden={GOLDEN} isurf={TARGET_ISURF} calls={CALLS}", flush=True)
    print(f"[toplevel-args] starting {CONTAINER} ...", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(CONTAINER)
        print(f"[toplevel-args] editor pid {pid}; attaching gdb ...", flush=True)
        gdb_script = GDB.replace("__PID__", str(pid)).replace("__CALLS__", str(CALLS)).replace(
            "__ISURF__", str(TARGET_ISURF))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/lta.gdb"],
                       input=gdb_script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/lta.gdb > /tmp/lta.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/lta.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[toplevel-args] attached; LIGHT APPLY ...", flush=True)
        drv.exec("LIGHT APPLY")
        deadline = time.monotonic() + 600.0
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                   "grep -c '^TARGET_DONE' /tmp/lta.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                print("[toplevel-args] TARGET_DONE seen", flush=True)
                break
            time.sleep(3.0)
        else:
            print("[toplevel-args] WARNING: gave up waiting", flush=True)
        LOGF.parent.mkdir(parents=True, exist_ok=True)
        LOGF.write_bytes(subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/lta.log"],
                                        capture_output=True).stdout)
        print(f"[toplevel-args] wrote {LOGF}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
