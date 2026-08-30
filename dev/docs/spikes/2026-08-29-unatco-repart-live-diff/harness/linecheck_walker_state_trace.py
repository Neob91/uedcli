#!/usr/bin/env python3
r"""Live GDB capture, round 6 continued: pin the remaining state-machine details of the real
recursive shadow-ray walker `0x17ce190` (found + structurally decoded via full static disassembly
in `linecheck_walker_full_disasm.py`, this same round).

The full static disasm resolved round 5's open question (loop/child-selection mechanics): the
function is a LOOP over whole-segment (no-crossing) nodes, with exactly ONE genuine recursive call
per crossing -- into the child containing POINT1 (using point1's own plane-dot sign to pick FRONT
vs BACK), replacing point1 with `mid` and leaving point2 UNCHANGED for that call; once the near
call returns clear, the loop continues into the OTHER child with point2 REPLACED by `mid` and
point1 left unchanged. Crossing formula (cross-validated against round 3's live-captured raw
register value and round 4's live-captured `mid` coordinates): t = D1/(D2-D1), mid = point2 +
t*(point2-point1), where D1=plane_dot(point1), D2=plane_dot(point2).

Two things the static read could not settle with confidence (SSE/state logic is dense and
error-prone to hand-trace, per this investigation's own prior-round lessons):
  1. The two "whole segment" classification constants (0x183761c, 0x182293c) are ASSUMED to both be
     0.0 -- not confirmed. This script reads them directly from live process memory.
  2. The `edi` "state" thread's exact semantics and a suspected asymmetry: the FAR-continuation code
     path (0x17ce3d5-0x17ce3da) tests `(extra_flags | 0x21)` against NodeFlags WITHOUT first
     stripping bit 0x10 (NF_BRIGHT_CORNERS) -- unlike every other CSG-classification site in this
     function (0x17ce238-244, 0x17ce27c-288), which all do `(extra_flags & ~0x10) | 0x21` first. If
     real, this is a genuine, non-obvious asymmetry that must be preserved in a port. This script
     captures `edi` before/after at every classification site, across several full rays, so the
     state machine can be reconstructed and cross-validated against the ray's own final boolean
     result (`eax` at return) and the golden's own stored bit for that same ray.

Usage: linecheck_walker_state_trace.py [golden.dx] [--rays N]
  -> logs/linecheck-walker-state-trace.log
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
CONTAINER = "uned-linecheck-walker-state"
LOGF = HERE.parent / "logs" / "linecheck-walker-state-trace.log"

# Addresses fixed relative to the confirmed-stable 0x17ce190 (round 3-5: stable across restarts).
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

printf "CONST1=%.9g\n", *(float*)0x183761c
printf "CONST2=%.9g\n", *(float*)0x182293c

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

  # top of per-node loop body: node pointer freshly computed into esi
  break *0x17ce1cd
  commands
  silent
  if $active == 1
    set $depth = $depth + 1
    printf "NODE ray=%d depth=%d inode=%d node=0x%x edi_in=%d\n", $ray, $depth, *(int*)($ebp+0x18), $esi, $edi
  end
  continue
  end

  # right after both D1(point1),D2(point2) dots are resolved and stored (0x17ce22c: xmm1 just
  # loaded from [ebp-0xc]=D2 -- both [ebp-8]=D1 and [ebp-0xc]=D2 are valid memory reads here)
  break *0x17ce231
  commands
  silent
  if $active == 1
    printf "DOTS ray=%d depth=%d D1=%.9g D2=%.9g\n", $ray, $depth, *(float*)($ebp-0x8), *(float*)($ebp-0xc)
  end
  continue
  end

  # whole-FRONT csg-solid branch taken
  break *0x17ce249
  commands
  silent
  if $active == 1
    printf "  BRANCH ray=%d depth=%d kind=FRONT_CSG edi_before=%d\n", $ray, $depth, $edi
  end
  continue
  end
  break *0x17ce25b
  commands
  silent
  if $active == 1
    printf "  BRANCH ray=%d depth=%d kind=FRONT_NONCSG edi_before=%d\n", $ray, $depth, $edi
  end
  continue
  end
  break *0x17ce28d
  commands
  silent
  if $active == 1
    printf "  BRANCH ray=%d depth=%d kind=BACK_CSG edi_before=%d\n", $ray, $depth, $edi
  end
  continue
  end
  break *0x17ce29c
  commands
  silent
  if $active == 1
    printf "  BRANCH ray=%d depth=%d kind=BACK_NONCSG edi_before=%d\n", $ray, $depth, $edi
  end
  continue
  end

  # after either whole-segment branch converges, right before writing back inode + looping
  break *0x17ce425
  commands
  silent
  if $active == 1
    printf "  TAIL ray=%d depth=%d next_inode=%d edi_after=%d\n", $ray, $depth, $ecx, $edi
  end
  continue
  end

  # D1 read for near-side selection (point1's own dot, used to pick which child to recurse into)
  break *0x17ce306
  commands
  silent
  if $active == 1
    set $d1_near = *(float*)($ebp-0x8)
    printf "  CROSS_D1 ray=%d depth=%d D1=%.9g\n", $ray, $depth, $d1_near
  end
  continue
  end

  # near-side-flag resolved (0=BACK/i_front, 1=FRONT/i_back), stored into [ebp-0xc]
  break *0x17ce31c
  commands
  silent
  if $active == 1
    printf "  NEARFLAG ray=%d depth=%d flag=%d\n", $ray, $depth, *(int*)($ebp-0xc)
  end
  continue
  end

  # right before the genuine recursive call -- log what child/state/points are being sent
  break *0x17ce3b4
  commands
  silent
  if $active == 1
    printf "  RECURSE_CALL ray=%d depth=%d child=%d state_out=%d\n", $ray, $depth, *(int*)($esp+0x10), *(int*)($esp+0xc)
  end
  continue
  end

  # right after the recursive call returns
  break *0x17ce3bc
  commands
  silent
  if $active == 1
    printf "  RECURSE_RETURN ray=%d depth=%d result=%d\n", $ray, $depth, $eax
  end
  continue
  end

  # far-continuation CSG-classification branches (the suspected asymmetric-mask sites)
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

  # terminal handling entry points
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
        print(f"[state-trace] golden not found: {GOLDEN}", file=sys.stderr)
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
    print(f"[state-trace] golden={GOLDEN} rays={RAYS}", flush=True)
    print(f"[state-trace] starting {CONTAINER} ...", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(CONTAINER)
        print(f"[state-trace] editor pid {pid}; attaching gdb ...", flush=True)
        isurf_gate = "1" if TARGET_ISURF is None else f"$hit_isurf == {TARGET_ISURF}"
        gdb_script = GDB.replace("__PID__", str(pid)).replace("__RAYS__", str(RAYS)).replace(
            "__ISURF_GATE__", isurf_gate)
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/lws.gdb"],
                       input=gdb_script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/lws.gdb > /tmp/lws.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/lws.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[state-trace] attached; LIGHT APPLY ...", flush=True)
        drv.exec("LIGHT APPLY")
        deadline = time.monotonic() + 600.0
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                   "grep -c '^TARGET_DONE' /tmp/lws.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                print("[state-trace] TARGET_DONE seen", flush=True)
                break
            time.sleep(3.0)
        else:
            print("[state-trace] WARNING: gave up waiting", flush=True)
        LOGF.parent.mkdir(parents=True, exist_ok=True)
        LOGF.write_bytes(subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/lws.log"],
                                        capture_output=True).stdout)
        print(f"[state-trace] wrote {LOGF}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
