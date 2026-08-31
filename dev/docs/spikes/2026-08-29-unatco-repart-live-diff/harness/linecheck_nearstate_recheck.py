#!/usr/bin/env python3
r"""Round 10: re-check the near-call incoming-state formula for the specific combination that
round 6-8's calibration set (122 mechanical checks, all-blocked rays + isurf=1060's 4-ray mix)
never happened to exercise: `near_side==FRONT`, `edi_in!=0` (state already proven open by an
ancestor), AND the CURRENT node's own `csg_nostrip` is FALSE (the node is itself flagged
`NF_BrightCorners`, which the near/far "unstripped" CSG mask treats as non-solid even though the
SAME node tests CSG-solid at whole-segment sites, since those strip the bit).

`linecheck_walker_state_trace.py`'s existing `RECURSE_CALL` breakpoint (`0x17ce3b4`) reads
`state_out` from `*(int*)($esp+0xc)` -- but that offset was never independently re-verified against
a direct register read, and round 10's own hand-recount of the intervening `push`/`sub` sequence
(`0x17ce364`-`0x17ce3b4`: mid-vector struct construction + 5 arg pushes) could not make that stack
offset land on the same slot as the freshly-computed state value, unlike round 8's own "closes an
open static-accounting puzzle" note for the TOP-level call's args (a similar but distinct offset
question). This script adds ONE more breakpoint, directly at `0x17ce35e` -- the jump target both
branches (`jne 0x17ce336` / fallthrough via `0x17ce334/0x17ce35c`) converge on, where `%eax` holds
the freshly finalized 0/1 state value BEFORE anything else touches it -- to get the ground truth
directly from the register, no stack-offset arithmetic needed.

Usage: linecheck_nearstate_recheck.py [golden.dx] [--isurf N] [--rays N]
  -> logs/linecheck-nearstate-recheck.log
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
RAYS = 8
TARGET_ISURF = None
for i, a in enumerate(sys.argv):
    if a == "--rays":
        RAYS = int(sys.argv[i + 1])
    if a == "--isurf":
        TARGET_ISURF = int(sys.argv[i + 1])

PROJECT_DIR = ROOT / "_scratch/oracle-project"
CONTAINER = "uned-linecheck-nearstate-recheck"
LOGF = HERE.parent / "logs" / "linecheck-nearstate-recheck.log"

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
set $depth = 0

break *0x100a5043
commands
silent
set $hit_isurf = *(int*)($ebp+0xc)
if $armed_surf == 0 && (__ISURF_GATE__)
  set $armed_surf = 1
  set $isurf = $hit_isurf
  printf "SURF_ENTER isurf=%d\n", $isurf

  break *0x100a5a04
  commands
  silent
  set $active = 1
  set $ray = $ray + 1
  set $depth = 0
  set $px = *(float*)($esp+0x14)
  set $py = *(float*)($esp+0x18)
  set $pz = *(float*)($esp+0x1c)
  printf "RAY_ENTER ray=%d px=%.9g py=%.9g pz=%.9g\n", $ray, $px, $py, $pz
  continue
  end

  break *0x17ce1cd
  commands
  silent
  if $active == 1
    set $depth = $depth + 1
    printf "NODE ray=%d depth=%d inode=%d nodeflags=0x%x edi_in=%d\n", $ray, $depth, *(int*)($ebp+0x18), *(unsigned char*)($esi+0x37), $edi
  end
  continue
  end

  break *0x17ce231
  commands
  silent
  if $active == 1
    printf "DOTS ray=%d depth=%d D1=%.9g D2=%.9g\n", $ray, $depth, *(float*)($ebp-0x8), *(float*)($ebp-0xc)
  end
  continue
  end

  break *0x17ce306
  commands
  silent
  if $active == 1
    set $d1_near = *(float*)($ebp-0x8)
    printf "  CROSS_D1 ray=%d depth=%d D1=%.9g edi_in=%d\n", $ray, $depth, $d1_near, $edi
  end
  continue
  end

  break *0x17ce31c
  commands
  silent
  if $active == 1
    printf "  NEARFLAG ray=%d depth=%d flag=%d\n", $ray, $depth, *(int*)($ebp-0xc)
  end
  continue
  end

  # ground truth: the exact instant %eax is finalized to the near-call incoming state (0 or 1),
  # BEFORE any stack-offset ambiguity in the subsequent mid-vector/arg-push sequence.
  break *0x17ce35e
  commands
  silent
  if $active == 1
    printf "  NEARSTATE_EAX ray=%d depth=%d eax=%d edi_at_this_point=%d\n", $ray, $depth, $eax, $edi
  end
  continue
  end

  break *0x17ce3b4
  commands
  silent
  if $active == 1
    printf "  RECURSE_CALL ray=%d depth=%d child=%d state_out_old_offset=%d\n", $ray, $depth, *(int*)($esp+0x10), *(int*)($esp+0xc)
  end
  continue
  end

  break *0x17ce3bc
  commands
  silent
  if $active == 1
    printf "  RECURSE_RETURN ray=%d depth=%d result=%d\n", $ray, $depth, $eax
  end
  continue
  end

  break *0x17ce3d5
  commands
  silent
  if $active == 1
    printf "  FARBRANCH ray=%d depth=%d kind=A edi_in=%d extra_flags=0x%x nodeflags=0x%x\n", $ray, $depth, $edi, *(unsigned char*)($ebp+0x38), *(unsigned char*)($esi+0x37)
  end
  continue
  end
  break *0x17ce3ef
  commands
  silent
  if $active == 1
    printf "  FARBRANCH ray=%d depth=%d kind=B edi_in=%d extra_flags=0x%x nodeflags=0x%x\n", $ray, $depth, $edi, *(unsigned char*)($ebp+0x38), *(unsigned char*)($esi+0x37)
  end
  continue
  end
  break *0x17ce3df
  commands
  silent
  if $active == 1
    printf "  FAROUT ray=%d depth=%d edi_new=1\n", $ray, $depth
  end
  continue
  end
  break *0x17ce3f9
  commands
  silent
  if $active == 1
    printf "  FAROUT ray=%d depth=%d edi_new=1\n", $ray, $depth
  end
  continue
  end
  break *0x17ce400
  commands
  silent
  if $active == 1
    printf "  FAROUT ray=%d depth=%d edi_new=0\n", $ray, $depth
  end
  continue
  end

  break *0x17ce442
  commands
  silent
  if $active == 1
    printf "  TERMINAL_A ray=%d depth=%d edi=%d\n", $ray, $depth, $edi
  end
  continue
  end
  break *0x17ce445
  commands
  silent
  if $active == 1
    printf "  TERMINAL_B ray=%d depth=%d edi=%d\n", $ray, $depth, $edi
  end
  continue
  end
  break *0x17ce449
  commands
  silent
  if $active == 1
    printf "  TERMINAL_GLOBALCHECK ray=%d depth=%d edi=%d global=%d bl_bit10=%d\n", $ray, $depth, $edi, *(int*)0x18fbbb4, (*(unsigned char*)($ebp+0x38)) & 0x10
  end
  continue
  end
  break *0x17ce456
  commands
  silent
  if $active == 1
    printf "  TERMINAL_BRIGHTCORNERS_CLEAR ray=%d depth=%d\n", $ray, $depth
  end
  continue
  end
  break *0x17ce464
  commands
  silent
  if $active == 1
    printf "  TERMINAL_WRITEOUT ray=%d depth=%d edx=%d edi=%d\n", $ray, $depth, $edx, $edi
  end
  continue
  end
  break *0x17ce4ac
  commands
  silent
  if $active == 1
    printf "  TERMINAL_RETURN_EDI ray=%d depth=%d edi=%d\n", $ray, $depth, $edi
  end
  continue
  end
  break *0x17ce439
  commands
  silent
  if $active == 1
    printf "  SHORTCIRCUIT_BLOCKED ray=%d depth=%d\n", $ray, $depth
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
        print(f"[nearstate-recheck] golden not found: {GOLDEN}", file=sys.stderr)
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
    print(f"[nearstate-recheck] golden={GOLDEN} rays={RAYS} isurf={TARGET_ISURF}", flush=True)
    print(f"[nearstate-recheck] starting {CONTAINER} ...", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(CONTAINER)
        print(f"[nearstate-recheck] editor pid {pid}; attaching gdb ...", flush=True)
        isurf_gate = "1" if TARGET_ISURF is None else f"$hit_isurf == {TARGET_ISURF}"
        gdb_script = GDB.replace("__PID__", str(pid)).replace("__RAYS__", str(RAYS)).replace(
            "__ISURF_GATE__", isurf_gate)
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/lnsr.gdb"],
                       input=gdb_script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/lnsr.gdb > /tmp/lnsr.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/lnsr.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[nearstate-recheck] attached; LIGHT APPLY ...", flush=True)
        drv.exec("LIGHT APPLY")
        deadline = time.monotonic() + 600.0
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                   "grep -c '^TARGET_DONE' /tmp/lnsr.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                print("[nearstate-recheck] TARGET_DONE seen", flush=True)
                break
            time.sleep(3.0)
        else:
            print("[nearstate-recheck] WARNING: gave up waiting", flush=True)
        LOGF.parent.mkdir(parents=True, exist_ok=True)
        LOGF.write_bytes(subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/lnsr.log"],
                                        capture_output=True).stdout)
        print(f"[nearstate-recheck] wrote {LOGF}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
