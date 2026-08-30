#!/usr/bin/env python3
r"""Live GDB capture: for each of Wanchai's 9 known-delta `repartition_frontier` subtree calls
(`wanchai-verts-points-residual-independently`), BFS-walk the subtree from its root (via
`iFront`/`iBack`/`iPlane` — `Editor.dll` `FBspNode` offsets `+0x20`/`+0x24`/`+0x28`, `iFront`/`iBack`
confirmed in `bspcsg.rs`'s own "ENGINE convention" comment; `iPlane` chains the coplanar-duplicate
successors and MUST be walked too — an earlier version of this script omitted it and silently missed
12 of the 43 "descendant" nodes for the 4 coplanar-leaf targets, since those targets have
`iFront=iBack=-1` but a live `iPlane` chain), capture every visited node's full 64 raw bytes
(`FBspNode` stride `0x40`, matching the `FArray::Remove` call's own `ElementSize` argument found in
`node_content_before_after.py`) at `bspRepartition` entry, then re-read the SAME indices at
`bspRepartition`'s own `bspRefresh`-return marker (`0x1004a05f`) and diff.

WHY. `node_content_before_after.py` (2026-08-30) found UNATCO `child=6108`'s own ROOT node slot
byte-identical before/after its call, despite `nodesnum_watch.py` proving real `bspAddNode` writes
happen (then get discarded by a real `Core.dll!FArray::Remove`) during that same call. That check
only covered ONE node (the subtree root); this one covers the WHOLE subtree (root + all descendants
reachable via iFront/iBack at call entry, bounded to 64 nodes), on Wanchai's known-bad calls, which
give cleaner calibration (9 fully-accounted calls, not buried in 209 like UNATCO's 46-call table).

MECHANISM (reused verbatim): `bspRepartition` entry `Editor.dll 0x10049fc0` (`esp+4=Model,
esp+8=iChild, esp+0xc=2`); stage-end marker `0x1004a05f` (post `bspRefresh` inside `bspRepartition`).

Usage:  wanchai_descendant_slots.py [golden.dx]
  -> logs/wanchai-descendant-slots.log
     BEFORE/AFTER lines per (child, slot) pair; diff summarized on stdout.
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

TARGETS = [11633, 11295, 11291, 11287, 11283, 11206, 11211, 11216, 11201]
GOLDEN = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    ROOT / "_scratch/golden_wanchai_world.dx")
PROJECT_DIR = ROOT / "_scratch/oracle-project"
POLL, DEADLINE = 2.0, 2400.0

TARGET_INIT = "set $tg = {" + ", ".join(str(v) for v in TARGETS) + "}"

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
set $ntg = 9
""" + TARGET_INIT + r"""
set $active = 0
set $child = -1
set $nsaved = 0
set $idx = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0}
break *0x10049fc0
commands
silent
set $child = *(int *)($esp + 8)
set $ismatch = 0
set $k = 0
while $k < $ntg
  if $tg[$k] == $child
    set $ismatch = 1
  end
  set $k = $k + 1
end
if $ismatch == 1
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
    printf "BEFORE child=%d slot=%d bytes=", $child, $ni
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
    printf "AFTER child=%d slot=%d bytes=", $child, $ni
    set $j = 0
    while $j < 0x40
      printf "%02x", *(unsigned char *)($node + $j)
      set $j = $j + 1
    end
    printf "\n"
    set $i = $i + 1
  end
  printf "TARGET_DONE child=%d nslots=%d\n", $child, $nsaved
  set $active = 0
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

    container = "uned-wanchai-descslots"
    O.stop_dbg_editor(container, state_dir)
    print(f"[wds] targets={TARGETS} golden={GOLDEN}", flush=True)
    print(f"[wds] starting {container} ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        print(f"[wds] editor pid {pid}; attaching gdb ...", flush=True)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/wds.gdb"],
                       input=GDB.replace("__PID__", str(pid)), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/wds.gdb > /tmp/wds.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/wds.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[wds] attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        deadline = time.monotonic() + DEADLINE
        prev = 0
        while time.monotonic() < deadline:
            n = subprocess.run(["docker", "exec", container, "bash", "-c",
                                "grep -c '^TARGET_DONE ' /tmp/wds.log 2>/dev/null || true"],
                               capture_output=True, text=True).stdout.strip()
            prev = int(n or 0)
            if prev >= len(TARGETS):
                print(f"[wds] all {len(TARGETS)} targets seen", flush=True)
                break
            time.sleep(POLL)
        else:
            print(f"[wds] WARNING: gave up after {DEADLINE:.0f}s, {prev}/{len(TARGETS)} targets seen",
                  flush=True)
        out = HERE.parent / "logs" / "wanchai-descendant-slots.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/wds.log"],
                                       capture_output=True).stdout)
        print(f"[wds] wrote {out}", flush=True)
        text = out.read_text(errors="replace")
        before = {}
        after = {}
        for ln in text.splitlines():
            if ln.startswith("BEFORE "):
                parts = ln.split()
                child = int(parts[1].split("=")[1])
                slot = int(parts[2].split("=")[1])
                b = parts[3].split("=", 1)[1]
                before[(child, slot)] = b
            elif ln.startswith("AFTER "):
                parts = ln.split()
                child = int(parts[1].split("=")[1])
                slot = int(parts[2].split("=")[1])
                b = parts[3].split("=", 1)[1]
                after[(child, slot)] = b
        print(f"[wds] slots captured: before={len(before)} after={len(after)}", flush=True)
        changed = 0
        for key in sorted(before):
            if key not in after:
                print(f"[wds] MISSING AFTER for child={key[0]} slot={key[1]}", flush=True)
                continue
            if before[key] != after[key]:
                changed += 1
                print(f"[wds] CHANGED child={key[0]} slot={key[1]}", flush=True)
        print(f"[wds] TOTAL slots diffed={len(before)}  CHANGED={changed}", flush=True)
    finally:
        O.stop_dbg_editor(container, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
