#!/usr/bin/env python3
r"""Live GDB capture: the same before/after persistent-content no-op check as
`wanchai_descendant_slots.py`, but on UNATCO's `repartition_frontier` calls, and NOT pre-selected as
"interesting" — the next N subtree calls in sequence (`callidx` range, not specific child values),
to test whether the "10/10 no-op" finding (`unatco-verts-points-residual-after-the-zone`) holds for
"boring" calls too, or whether it was a sampling-bias artifact of only checking calls native's own
diagnostics had already flagged (all 9 Wanchai calls + UNATCO's `child=6108` were pre-selected
because something about them looked notable from native's side).

WHY. This item's open contradiction: 10/10 individually-checked `bspRepartition` calls (9 Wanchai +
UNATCO `child=6108`, ALL pre-selected as known-delta/notable) show ZERO persistent tree change, but
the long-established stage-count table shows UNATCO's verts growing +10462 in aggregate across the
SAME 209-call sequence. Candidate reconciliation (b): the 10 calls checked are unrepresentative, and
the real growth is spread across "boring" calls nobody had reason to check yet. This tests exactly
that, on calls chosen WITHOUT looking at what native's own reconstruction says about them first.

MECHANISM (reused verbatim from `wanchai_descendant_slots.py`/`repart_child_trace.py`): `iFront`=+0x20,
`iBack`=+0x24, `iPlane`=+0x28 (`FBspNode`, confirmed via `bspcsg.rs`'s own "ENGINE convention"
comment); node stride `0x40`; `bspRepartition` entry `Editor.dll 0x10049fc0`
(`esp+4=Model, esp+8=iChild, esp+0xc=Flag`); stage-end marker `0x1004a05f`.

Usage:  unatco_boring_calls_noop_check.py <first_callidx> <count> [golden.dx]
  e.g. `unatco_boring_calls_noop_check.py 10 8` captures callidx 10..17 inclusive (8 calls) --
  chosen to be right after the earliest few calls (which include the 3 pinned/known-delta ones,
  callidx unknown without a lookup, so starting past the first ~10 avoids ambiguity without needing
  to know which callidx values those 3 land on).
  -> logs/unatco-boring-noop-<first>-<count>.log
"""
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

FIRST_CALLIDX = int(sys.argv[1])
COUNT = int(sys.argv[2])
LAST_CALLIDX = FIRST_CALLIDX + COUNT - 1
GOLDEN = Path(sys.argv[3]) if len(sys.argv) > 3 else (
    ROOT / "_scratch/bsp-parity-proj/golden_unatco_control.dx")
PROJECT_DIR = ROOT / "_scratch/oracle-project"
POLL, DEADLINE = 2.0, 2400.0

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
set $callidx = 0
set $first = __FIRST__
set $last = __LAST__
set $active = 0
set $child = -1
set $nsaved = 0
set $idx = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0}
break *0x10049fc0
commands
silent
set $callidx = $callidx + 1
set $child = *(int *)($esp + 8)
if $callidx >= $first && $callidx <= $last && $child != 0
  set $m = *(unsigned int *)($esp + 4)
  set $base = *(unsigned int *)($m + 0x58)
  set $qhead = 0
  set $qtail = 1
  set $idx[0] = $child
  set $n = 1
  while $qhead < $qtail && $n < 64
    set $cur = $idx[$qhead]
    set $qhead = $qhead + 1
    set $node = $base + $cur * 0x40
    set $f = *(int *)($node + 0x20)
    set $b = *(int *)($node + 0x24)
    set $p = *(int *)($node + 0x28)
    if $f != -1 && $n < 64
      set $idx[$qtail] = $f
      set $qtail = $qtail + 1
      set $n = $n + 1
    end
    if $b != -1 && $n < 64
      set $idx[$qtail] = $b
      set $qtail = $qtail + 1
      set $n = $n + 1
    end
    if $p != -1 && $n < 64
      set $idx[$qtail] = $p
      set $qtail = $qtail + 1
      set $n = $n + 1
    end
  end
  set $nsaved = $n
  set $i = 0
  while $i < $nsaved
    set $ni = $idx[$i]
    set $node = $base + $ni * 0x40
    printf "BEFORE callidx=%d child=%d slot=%d bytes=", $callidx, $child, $ni
    set $j = 0
    while $j < 0x40
      printf "%02x", *(unsigned char *)($node + $j)
      set $j = $j + 1
    end
    printf "\n"
    set $i = $i + 1
  end
  set $active = 1
end
continue
end
break *0x1004a05f
commands
silent
if $active == 1
  set $i = 0
  while $i < $nsaved
    set $ni = $idx[$i]
    set $node = $base + $ni * 0x40
    printf "AFTER callidx=%d child=%d slot=%d bytes=", $callidx, $child, $ni
    set $j = 0
    while $j < 0x40
      printf "%02x", *(unsigned char *)($node + $j)
      set $j = $j + 1
    end
    printf "\n"
    set $i = $i + 1
  end
  printf "CALLDONE callidx=%d child=%d nslots=%d\n", $callidx, $child, $nsaved
  set $active = 0
  if $callidx >= $last
    printf "ALL_DONE\n"
    detach
    quit
  end
end
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def main() -> int:
    if not PROJECT_DIR.exists():
        PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        (PROJECT_DIR / "uedcli.toml").write_text('game = "deusex"\n')

    O._ensure_dbg_image()
    project = config.load_project(str(PROJECT_DIR))
    user_config = config.load_user_config()
    mounts = resource_mounts(config.composed_search_dirs(project, user_config))
    state_dir = config.state_dir(project.root, create=True)

    container = f"uned-unatco-boring-{FIRST_CALLIDX}-{COUNT}"
    O.stop_dbg_editor(container, state_dir)
    print(f"[boring] callidx {FIRST_CALLIDX}..{LAST_CALLIDX} golden={GOLDEN}", flush=True)
    print(f"[boring] starting {container} ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        print(f"[boring] editor pid {pid}; attaching gdb ...", flush=True)
        gdb_script = (GDB.replace("__PID__", str(pid))
                      .replace("__FIRST__", str(FIRST_CALLIDX))
                      .replace("__LAST__", str(LAST_CALLIDX)))
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/ubn.gdb"],
                       input=gdb_script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/ubn.gdb > /tmp/ubn.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/ubn.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[boring] attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        deadline = time.monotonic() + DEADLINE
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c '^ALL_DONE' /tmp/ubn.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                print("[boring] ALL_DONE seen", flush=True)
                break
            time.sleep(POLL)
        else:
            print(f"[boring] WARNING: gave up after {DEADLINE:.0f}s", flush=True)
        out = HERE.parent / "logs" / f"unatco-boring-noop-{FIRST_CALLIDX}-{COUNT}.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/ubn.log"],
                                       capture_output=True).stdout)
        print(f"[boring] wrote {out}", flush=True)
        text = out.read_text(errors="replace")
        before, after = {}, {}
        for ln in text.splitlines():
            if ln.startswith("BEFORE "):
                parts = ln.split()
                callidx = int(parts[1].split("=")[1])
                child = int(parts[2].split("=")[1])
                slot = int(parts[3].split("=")[1])
                b = parts[4].split("=", 1)[1]
                before[(callidx, child, slot)] = b
            elif ln.startswith("AFTER "):
                parts = ln.split()
                callidx = int(parts[1].split("=")[1])
                child = int(parts[2].split("=")[1])
                slot = int(parts[3].split("=")[1])
                b = parts[4].split("=", 1)[1]
                after[(callidx, child, slot)] = b
        calldone = sorted({int(l.split("callidx=")[1].split()[0]) for l in text.splitlines()
                           if l.startswith("CALLDONE ")})
        print(f"[boring] calls captured: {calldone}", flush=True)
        print(f"[boring] slots: before={len(before)} after={len(after)}", flush=True)
        changed = 0
        for key in sorted(before):
            if key not in after:
                print(f"[boring] MISSING AFTER {key}", flush=True)
                continue
            if before[key] != after[key]:
                changed += 1
                print(f"[boring] CHANGED callidx={key[0]} child={key[1]} slot={key[2]}", flush=True)
        print(f"[boring] TOTAL slots diffed={len(before)}  CHANGED={changed}", flush=True)
    finally:
        O.stop_dbg_editor(container, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
