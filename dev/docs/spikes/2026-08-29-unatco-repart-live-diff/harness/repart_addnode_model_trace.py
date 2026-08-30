#!/usr/bin/env python3
r"""Live GDB capture: does `bspAddNode`'s own `Model` argument (esp+4) ever differ from
`bspRepartition`'s `Model` argument (esp+4) for calls made WHILE that one repartition call is on
the stack?

WHY. `unatco-verts-points-residual-after-the-zone` / `native-materialize-findings.md` (2026-08-30):
full disassembly of `bspRepartition`'s 4 sub-calls (`bspBuildFPolys`/`bspMergeCoplanars`/`bspBuild`/
`bspRefresh`) found every one of them passed an explicit scratch-model CTX distinct from the
persistent Model `this` -- and `bspBuild`'s Flag=2 path (every subtree call) appends straight into
that scratch's own, uncleared Nodes array via a `SplitPolyList`-equivalent (0x10034530), never
touching the persistent Model's Nodes. But the actual scratch->persistent COMMIT step was not
located despite disassembling all 4 sub-calls plus the 2 calls csgRebuild makes after both frontier
loops finish. Coordinator's proposed direct test: `bspAddNode` (0x10034e80, `esp+4=Model`) is called
UNDERNEATH `SplitPolyList` for every leaf/split node -- if its `Model` argument ever resolves to the
scratch address rather than the persistent one (or vice versa, or SWITCHES mid-call), that is direct,
unambiguous proof of which object nodes really land in, and when a swap (if any) happens.

MECHANISM (see `repart_child_trace.py`, same addresses, re-used verbatim):
  bspRepartition entry (Editor.dll 0x10049fc0): esp+4=Model, esp+8=iChild, esp+0xc=2.
  bspAddNode        (Editor.dll 0x10034e80): esp+4=Model, esp+8=iParent, esp+0xc=ENodePlace.

Usage:  repart_addnode_model_trace.py <child_node_index> [golden.dx]
  -> logs/repart-addnode-model-<N>.log
     CALL lines: every bspRepartition entry, with its own Model arg.
     ADD  lines (only while TARGET_CHILD is the active repartition): bspAddNode's own Model arg,
     parent, place -- so each ADD's Model can be diffed against the enclosing CALL's Model directly,
     in the SAME live capture, no separate scratch-constant reference needed.
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
set $callidx = 0
set $active = 0
break *0x10049fc0
commands
silent
set $callidx = $callidx + 1
set $callmodel = *(unsigned int *)($esp + 4)
set $child = *(int *)($esp + 8)
printf "CALL idx=%d model=%#x child=%d third=%d nodesnum=%d\n", $callidx, $callmodel, $child, *(int *)($esp + 0xc), *(int *)($callmodel + 0x5c)
if $child == $target
  printf "TARGET_BEGIN idx=%d model=%#x nodesnum=%d\n", $callidx, $callmodel, *(int *)($callmodel + 0x5c)
  set $active = 1
  set $target_model = $callmodel
end
continue
end
break *0x1004a05f
commands
silent
if $active == 1 && $child == $target
  printf "TARGET_END nodesnum=%d\n", *(int *)($target_model + 0x5c)
  set $active = 0
  detach
  quit
end
continue
end
break *0x10034e80
commands
silent
if $active == 1
  set $m = *(unsigned int *)($esp + 4)
  printf "ADD model=%#x match=%d parent=%d place=%d\n", $m, ($m == $target_model), *(int *)($esp + 8), *(int *)($esp + 0xc)
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

    container = f"uned-addnode-model-{TARGET_CHILD}"
    O.stop_dbg_editor(container, state_dir)
    print(f"[trace] target child={TARGET_CHILD} golden={GOLDEN}", flush=True)
    print(f"[trace] starting {container} ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        print(f"[trace] editor pid {pid}; attaching gdb ...", flush=True)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/ramt.gdb"],
                       input=GDB.format(pid=pid, target=TARGET_CHILD), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/ramt.gdb > /tmp/ramt.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/ramt.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[trace] attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        deadline = time.monotonic() + DEADLINE
        prev = 0
        while time.monotonic() < deadline:
            n = subprocess.run(["docker", "exec", container, "bash", "-c",
                                "grep -c '^CALL ' /tmp/ramt.log 2>/dev/null || true"],
                               capture_output=True, text=True).stdout.strip()
            prev = int(n or 0)
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c '^TARGET_END' /tmp/ramt.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                print(f"[trace] TARGET_END seen after {prev} bspRepartition calls", flush=True)
                break
            time.sleep(POLL)
        else:
            print(f"[trace] WARNING: gave up after {DEADLINE:.0f}s, {prev} CALL lines seen "
                  "(target child never hit)", flush=True)
        out = HERE.parent / "logs" / f"repart-addnode-model-{TARGET_CHILD}.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/ramt.log"],
                                       capture_output=True).stdout)
        print(f"[trace] wrote {out} ({prev} bspRepartition calls seen)", flush=True)
        text = out.read_text(errors="replace")
        n_add = text.count("\nADD ")
        n_mismatch = text.count("match=0")
        n_target = text.count("TARGET_BEGIN")
        print(f"[trace] target hit {n_target} time(s); {n_add} ADD lines, {n_mismatch} model MISMATCH",
              flush=True)
    finally:
        O.stop_dbg_editor(container, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
