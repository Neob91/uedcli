#!/usr/bin/env python3
r"""Live GDB capture, round 2: trace the known-mismatching ray (`rec=14 light=Light42 v=3 u=0` on
the Wanchai golden) through the editor's real recursive shadow-ray walker, gated behind a much
RARER checkpoint than the previous round's per-ray call site.

Round 1 (`linecheck_singlestep_rec14.py`) put a conditional breakpoint directly on the shared
`LineCheck` call site (`0x100a5a04`), hit once per shadow-ray BIT computed across the WHOLE level
(order 10^5-10^6 for Wanchai) -- 25 minutes in, zero matches, killed. This round instead breaks at
`illuminateSurf`'s own per-surface entry (`Editor.dll 0x100a5010`, located fresh this session via a
backward int3-padding scan, NOT trusted from the pre-2026-08-14 `sections/20-lighting-bake.md` doc
though it happens to agree with it), confirmed live to take `iSurf` at `[ebp+0xc]` (traced
`Surfs_base + iSurf*64` at `0x100a5053`-`0x100a505f`). `illuminateSurf` is called ONCE per surface
(~4530 times total for Wanchai) -- three orders of magnitude fewer hits than the per-ray site.

The target ray's LightMap record (k=14) maps to `iSurf=4556` in the golden (computed offline via
`lightparity.level_model`, this session). The gdb script:
  1. Breaks at `illuminateSurf`+0x33 (`0x100a5043`, past the prologue, `[ebp+0xc]` still the raw
     caller-pushed `iSurf`), conditioned on `iSurf==4556`.
  2. On match (should fire ONCE for the whole run): dynamically creates the ray-level breakpoint at
     the fixed `LineCheck` call site (`0x100a5a04`), now live ONLY from this point on -- so it only
     ever fires for surf 4556's own lumel x light grid, not the other ~4529 surfaces already
     processed or yet to come.
  3. On a ray-level match (pushed lumel position within a tight float band of the target): resolves
     the recursive walker's live address (`target+0x5b0`, same method as round 1) and arms the two
     node-level breakpoints (`+0x92` for ds/de/flags per node, `+0xd5` for the computed `mid`),
     scoped by `$active` to just that one ray's call tree.
  4. Detaches and quits as soon as the target ray's outer call returns.

Usage: linecheck_singlestep_rec14_v2.py [golden.dx] [--isurf N]
  -> logs/linecheck-singlestep-rec14-v2.log
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
for i, a in enumerate(sys.argv):
    if a == "--isurf":
        ISURF = int(sys.argv[i + 1])

PROJECT_DIR = ROOT / "_scratch/oracle-project"
CONTAINER = "uned-linecheck-singlestep-v2"
LOGF = HERE.parent / "logs" / "linecheck-singlestep-rec14-v2.log"

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
set $armed_surf = 0
set $armed_ray = 0

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
  set $px = *(float*)($esp+0x14)
  set $py = *(float*)($esp+0x18)
  set $pz = *(float*)($esp+0x1c)
  if $px > 1759.999 && $px < 1760.001 && $py > 1148.10 && $py < 1148.15 && $pz > 191.8 && $pz < 191.95
    set $active = 1
    printf "TARGET_ENTER px=%.9g py=%.9g pz=%.9g\n", $px, $py, $pz
    if $armed_ray == 0
      set $model = $ecx
      set $vtbl = *(int *)$model
      set $target = *(int *)($vtbl + 0x58)
      set $inner = $target + 0x5b0
      printf "RESOLVED model=0x%x target=0x%x inner=0x%x\n", $model, $target, $inner

      break *0x17ce2ae
      commands
      silent
      if $active == 1
        set $A = *(float*)($ebp-0x8)
        set $B = *(float*)($ebp-0xc)
        set $p1x = *(float*)($ebp+0x1c)
        set $p1y = *(float*)($ebp+0x20)
        set $p1z = *(float*)($ebp+0x24)
        set $p2x = *(float*)($ebp+0x28)
        set $p2y = *(float*)($ebp+0x2c)
        set $p2z = *(float*)($ebp+0x30)
        printf "CROSS_ENTRY A=%.9g B=%.9g p1=(%.9g,%.9g,%.9g) p2=(%.9g,%.9g,%.9g)\n", $A, $B, $p1x, $p1y, $p1z, $p2x, $p2y, $p2z
      end
      continue
      end

      break *0x17ce2e6
      commands
      silent
      if $active == 1
        set $t = $xmm4.v4_float[0]
        printf "CROSS_T t=%.9g\n", $t
      end
      continue
      end

      break *0x17ce3b4
      commands
      silent
      if $active == 1
        printf "RECURSE_CALL (self-recursive into 0x17ce190)\n"
      end
      continue
      end

      break *$target+0x47
      commands
      silent
      if $active == 1
        printf "NODES_NUM_CHECK edi=0x%x nodes_num=%d\n", $edi, *(int*)($edi+0x5c)
      end
      continue
      end

      break *$target+0x559
      commands
      silent
      if $active == 1
        printf "TOOK_SHORT_PATH_0x17cea19\n"
      end
      continue
      end

      break *$inner
      commands
      silent
      if $active == 1
        printf "INNER_ENTRY node_arg=%d state_arg_byte=%d\n", *(int*)($esp+4), *(unsigned char*)($esp+8)
      end
      continue
      end

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

      set $armed_ray = 1
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
end
continue
end

printf "ORACLE_ATTACHED\n"
continue
"""


def main() -> int:
    if not GOLDEN.exists():
        print(f"[singlestep-v2] golden not found: {GOLDEN}", file=sys.stderr)
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
    print(f"[singlestep-v2] golden={GOLDEN} isurf={ISURF}", flush=True)
    print(f"[singlestep-v2] starting {CONTAINER} ...", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(CONTAINER)
        print(f"[singlestep-v2] editor pid {pid}; attaching gdb ...", flush=True)
        gdb_script = GDB.replace("__PID__", str(pid)).replace("__ISURF__", str(ISURF))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/ls2.gdb"],
                       input=gdb_script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/ls2.gdb > /tmp/ls2.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/ls2.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[singlestep-v2] attached; LIGHT APPLY ...", flush=True)
        drv.exec("LIGHT APPLY")
        deadline = time.monotonic() + 900.0
        last_size = -1
        stall_since = None
        while time.monotonic() < deadline:
            log = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "wc -c < /tmp/ls2.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            done = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                   "grep -c '^TARGET_DONE' /tmp/ls2.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                print("[singlestep-v2] TARGET_DONE seen", flush=True)
                break
            size = int(log) if log else 0
            print(f"[singlestep-v2] ... log size={size}", flush=True)
            time.sleep(5.0)
        else:
            print("[singlestep-v2] WARNING: gave up waiting (900s budget)", flush=True)
        LOGF.parent.mkdir(parents=True, exist_ok=True)
        LOGF.write_bytes(subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/ls2.log"],
                                        capture_output=True).stdout)
        print(f"[singlestep-v2] wrote {LOGF}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
