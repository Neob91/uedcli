#!/usr/bin/env python3
r"""Live ENTRY dump of the real `FPoly::RemoveColinears` (Engine.dll) call TryToMerge makes on the
6-vertex merge ring for `iLink`s 300/878/888/889/896/977/1144/1163 -- the exact nested call the
prior session (`bspmergecoplanars-8-case-merge-gap-live-traced`) could not isolate: their first
attempt broke on a NAIVELY rebased Engine.dll address and, even after correcting via the IAT-slot
read, produced data inconsistent with being the TryToMerge-nested call (probably a different,
far more frequent caller, e.g. `FPoly::Finalize`).

This script fixes BOTH gaps at once:
  1. Resolves RemoveColinears's REAL runtime entry address by reading Editor.dll's own IAT slot
     live (`*(int*)0x100cee2c`), exactly as the prior session did for their one probe -- Engine.dll
     is rebased ~-0xF00000 relative to its declared image base; Editor.dll is not.
  2. Filters the breakpoint by RETURN ADDRESS, not just iLink: only the return address that
     immediately follows TryToMerge's OWN `call [RemoveColinears]` at Editor.dll VA 0x10034de2 --
     `call dword ptr [imm32]` is 6 bytes (`FF 15 <imm32>`), so the return address is 0x10034de8, NOT
     0x10034de7 (an earlier draft of this script had this off by one, which would have silently
     matched nothing) -- this isolates the TryToMerge-nested call from every other RemoveColinears
     call site in the binary.

  Editor.dll has exactly TWO call sites through the RemoveColinears IAT slot (confirmed by scanning
  the whole module for the `FF 15 <iat-slot-imm32>` byte pattern, not guessed): TryToMerge's, above,
  and a second one at VA 0x10036804 (return addr 0x1003680a) inside an entirely different function
  (0x100365b0) that reconstructs a single FPoly from a BSP node's stored vertex-pool data -- the
  "far more frequent caller" the prior session's abandoned probe most likely actually hit. Both
  return addresses are logged here (tagged SITE=TTM / SITE=NODE) so a caller mixup is visible in the
  log itself, not just assumed away.

At entry (before the prologue clobbers anything -- breakpoint sits on the very first instruction,
`push ebp`), ecx = `this` (the scratch ring FPoly TryToMerge built). Field offsets (established by
this session's + the prior session's disassembly of RemoveColinears/TryToMerge, cross-checked
against Engine.dll's own PE export table for `?RemoveColinears@FPoly@@QAEHXZ`): Normal=+0xc (3
floats), NumVertices=+0x1c0, iLink=+0x1c4, Verts[]=+0x30 (up to 16, stride 12 bytes/3 floats).

Usage:  removecolinears_entry_unatco.py [golden.dx]   ->  logs/removecolinears-entry-unatco.log
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
HERE = HARNESS / "editor-tree-oracle"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HARNESS)); sys.path.insert(0, str(HERE))
import editor_tree_oracle as O
from uedcli import config
from uedcli.container_assets import resource_mounts
from uedcli.driver import Driver, to_z_path

GOLDEN = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/UEDGolden_unatco_full.dx")
PROJECT_DIR = ROOT / "_scratch/oracle-project"

# TryToMerge's own call site + the instruction immediately after it (return address).  The other
# known call site (FPoly-from-BSP-node reconstruction) returns to 0x1003680a -- logged separately.
TTM_CALL_RET_VA = 0x10034de8
NODE_CALL_RET_VA = 0x1003680a
RC_IAT_SLOT_VA = 0x100cee2c

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

set $rc_addr = *(int *)0x100cee2c
printf "RC_LIVE_ADDR=%#x\n", $rc_addr
break *$rc_addr
commands
silent
if *(int *)$esp == 0x10034de8
  printf "RC_ENTRY SITE=TTM ret=%#x this=%#x ilink=%d nv=%d N=%.6f,%.6f,%.6f NHEX=%#x,%#x,%#x\n", *(int *)$esp, $ecx, *(int *)($ecx + 0x1c4), *(int *)($ecx + 0x1c0), *(float *)($ecx + 0xc), *(float *)($ecx + 0x10), *(float *)($ecx + 0x14), *(int *)($ecx + 0xc), *(int *)($ecx + 0x10), *(int *)($ecx + 0x14)
  printf "RC_V0 %.6f,%.6f,%.6f HEX=%#x,%#x,%#x\n", *(float *)($ecx + 0x30), *(float *)($ecx + 0x34), *(float *)($ecx + 0x38), *(int *)($ecx + 0x30), *(int *)($ecx + 0x34), *(int *)($ecx + 0x38)
  printf "RC_V1 %.6f,%.6f,%.6f HEX=%#x,%#x,%#x\n", *(float *)($ecx + 0x3c), *(float *)($ecx + 0x40), *(float *)($ecx + 0x44), *(int *)($ecx + 0x3c), *(int *)($ecx + 0x40), *(int *)($ecx + 0x44)
  printf "RC_V2 %.6f,%.6f,%.6f HEX=%#x,%#x,%#x\n", *(float *)($ecx + 0x48), *(float *)($ecx + 0x4c), *(float *)($ecx + 0x50), *(int *)($ecx + 0x48), *(int *)($ecx + 0x4c), *(int *)($ecx + 0x50)
  printf "RC_V3 %.6f,%.6f,%.6f HEX=%#x,%#x,%#x\n", *(float *)($ecx + 0x54), *(float *)($ecx + 0x58), *(float *)($ecx + 0x5c), *(int *)($ecx + 0x54), *(int *)($ecx + 0x58), *(int *)($ecx + 0x5c)
  printf "RC_V4 %.6f,%.6f,%.6f HEX=%#x,%#x,%#x\n", *(float *)($ecx + 0x60), *(float *)($ecx + 0x64), *(float *)($ecx + 0x68), *(int *)($ecx + 0x60), *(int *)($ecx + 0x64), *(int *)($ecx + 0x68)
  printf "RC_V5 %.6f,%.6f,%.6f HEX=%#x,%#x,%#x\n", *(float *)($ecx + 0x6c), *(float *)($ecx + 0x70), *(float *)($ecx + 0x74), *(int *)($ecx + 0x6c), *(int *)($ecx + 0x70), *(int *)($ecx + 0x74)
end
if *(int *)$esp == 0x1003680a
  printf "RC_ENTRY SITE=NODE ret=%#x this=%#x ilink=%d nv=%d\n", *(int *)$esp, $ecx, *(int *)($ecx + 0x1c4), *(int *)($ecx + 0x1c0)
end
continue
end

break *0x1004a041
commands
silent
printf "REPART_ENTRY\n"
continue
end

printf "ORACLE_ATTACHED\n"
continue
"""


def main():
    if not PROJECT_DIR.exists():
        PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        (PROJECT_DIR / "uedcli.toml").write_text('game = "deusex"\n')

    O._ensure_dbg_image()
    project = config.load_project(str(PROJECT_DIR))
    user_config = config.load_user_config()
    search_dirs = config.composed_search_dirs(project, user_config)
    mounts = resource_mounts(search_dirs)
    state_dir = config.state_dir(project.root, create=True)

    container = "uned-rcentry-unatco"
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
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/rc.gdb"],
                       input=GDB.format(pid=pid), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/rc.gdb > /tmp/rc.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/rc.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        print("attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        for _ in range(1500):
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c REPART_ENTRY /tmp/rc.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                break
            time.sleep(1.0)
        time.sleep(2.0)
        out = HERE / "logs" / "removecolinears-entry-unatco.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        data = subprocess.run(["docker", "exec", container, "cat", "/tmp/rc.log"],
                              capture_output=True).stdout
        out.write_bytes(data)
        print(f"wrote {out}", flush=True)
        nd = subprocess.run(["bash", "-c", f"grep -c '^RC_ENTRY ' {out}"],
                            capture_output=True, text=True).stdout.strip()
        print(f"{nd} RC_ENTRY lines")
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    main()
