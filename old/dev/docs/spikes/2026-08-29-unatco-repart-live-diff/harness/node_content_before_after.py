#!/usr/bin/env python3
r"""Live GDB capture: does `Nodes[iChild]`'s own raw content (persistent Model, FIXED index,
NEVER re-numbered) actually change across its own `bspRepartition` call, given `nodesnum_watch.py`
(2026-08-30) proved the array's `Num` field always resets back to the exact pre-call baseline
(net zero growth) -- even for `child=6108`, a subtree independently known to have a `+1` node
delta. If content at the fixed index doesn't change, the "temporary scratch beyond Num, discarded
every time" reading would mean subtree calls are pure no-ops, which cannot be right (the final
map reflects real, different splits). If content DOES change, that's the actual "commit": each
subtree call OVERWRITES ITS OWN PRE-EXISTING SLOT(S) in place, using indices beyond Num as pure
working scratch during SplitPolyList, all discarded by bspRefresh's FArray::Remove every time.

Reads NumVertices(+0x36), iPlane... actually iFront/iBack/iPlane are at various offsets; keep it
simple and diff the FULL 0x40-byte node (FBspNode stride, confirmed via the FArray::Remove
ElementSize=0x40 argument) as raw bytes, md5'd, before vs after.

Usage:  node_content_before_after.py <child_node_index> [golden.dx]
  -> logs/node-content-<N>.log
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

TARGET_CHILD = int(sys.argv[1])
GOLDEN = Path(sys.argv[2]) if len(sys.argv) > 2 else (
    ROOT / "_scratch/bsp-parity-proj/golden_unatco_control.dx")
PROJECT_DIR = ROOT / "_scratch/oracle-project"
POLL, DEADLINE = 2.0, 2400.0

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
set $target = {target}
set $child = -1
break *0x10049fc0
commands
silent
set $m = *(unsigned int *)($esp + 4)
set $child = *(int *)($esp + 8)
if $child == $target
  set $node = *(unsigned int *)($m + 0x58) + $target * 0x40
  printf "BEFORE child=%d node_addr=%#x nodesnum=%d bytes=", $target, $node, *(int *)($m + 0x5c)
  set $i = 0
  while $i < 0x40
    printf "%02x", *(unsigned char *)($node + $i)
    set $i = $i + 1
  end
  printf "\n"
end
continue
end
break *0x1004a05f
commands
silent
if $child == $target
  set $m2 = $m
  set $node2 = *(unsigned int *)($m2 + 0x58) + $target * 0x40
  printf "AFTER child=%d node_addr=%#x nodesnum=%d bytes=", $target, $node2, *(int *)($m2 + 0x5c)
  set $i = 0
  while $i < 0x40
    printf "%02x", *(unsigned char *)($node2 + $i)
    set $i = $i + 1
  end
  printf "\n"
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
    if not PROJECT_DIR.exists():
        PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        (PROJECT_DIR / "uedcli.toml").write_text('game = "deusex"\n')

    O._ensure_dbg_image()
    project = config.load_project(str(PROJECT_DIR))
    user_config = config.load_user_config()
    mounts = resource_mounts(config.composed_search_dirs(project, user_config))
    state_dir = config.state_dir(project.root, create=True)

    container = f"uned-nodecontent-{TARGET_CHILD}"
    O.stop_dbg_editor(container, state_dir)
    print(f"[nc] target child={TARGET_CHILD} golden={GOLDEN}", flush=True)
    print(f"[nc] starting {container} ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        print(f"[nc] editor pid {pid}; attaching gdb ...", flush=True)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/nc.gdb"],
                       input=GDB.format(pid=pid, target=TARGET_CHILD), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/nc.gdb > /tmp/nc.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/nc.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[nc] attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        deadline = time.monotonic() + DEADLINE
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c '^TARGET_DONE' /tmp/nc.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                print("[nc] TARGET_DONE seen", flush=True)
                break
            time.sleep(POLL)
        else:
            print(f"[nc] WARNING: gave up after {DEADLINE:.0f}s", flush=True)
        out = HERE.parent / "logs" / f"node-content-{TARGET_CHILD}.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/nc.log"],
                                       capture_output=True).stdout)
        print(f"[nc] wrote {out}", flush=True)
        text = out.read_text(errors="replace")
        before = [ln for ln in text.splitlines() if ln.startswith("BEFORE ")]
        after = [ln for ln in text.splitlines() if ln.startswith("AFTER ")]
        if before and after:
            b_bytes = before[-1].split("bytes=")[1]
            a_bytes = after[-1].split("bytes=")[1]
            print(f"[nc] BEFORE bytes: {b_bytes}", flush=True)
            print(f"[nc] AFTER  bytes: {a_bytes}", flush=True)
            print(f"[nc] IDENTICAL: {b_bytes == a_bytes}", flush=True)
        else:
            print(f"[nc] missing before/after lines (before={len(before)} after={len(after)})",
                  flush=True)
    finally:
        O.stop_dbg_editor(container, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
