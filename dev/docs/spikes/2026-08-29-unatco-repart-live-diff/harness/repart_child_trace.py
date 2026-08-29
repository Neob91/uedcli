#!/usr/bin/env python3
r"""Live GDB capture: editor's exact `bspAddNode` sequence for ONE sub-BSP repartition call, to
diff against native's own reconstruction for the same subtree.

WHY. `unatco-verts-points-residual-after-the-zone` narrowed the remaining UNATCO node-exactness
gap (post `repartition-frontier` fix, `04986a2`) to exactly 3 of 209 `bspRepartition(Model,
iChild, 2)` calls, all `delta=+1/+2/+4` (editor produces more nodes than native for that one
subtree). The smallest, `child=6108` (parent=689, 40 polys, delta=+1), has a confirmed-clean root
split (not a near-tie) and matching per-brush surf counts, so the divergence is purely in the
RECURSIVE sub-splits below the root. Static disassembly and parameter tuning (`Opt::Lame`,
`bsp_merge_coplanars`) were exhausted without closing it (see that board item). This captures the
editor's actual node-by-node split sequence for that one call, live, to diff against native's.

MECHANISM (fresh-decoded 2026-08-29, see board item "mechanism INDEPENDENTLY re-confirmed"):
  csgRebuild (Editor.dll 0x1004a650) loop2 at 0x1004aa90: for n in list2 (iBack==-1 snapshot),
  if Nodes[n].iBack != -1: bspRepartition(Model, Nodes[n].iBack, 2)   # loop1 (iFront) at 0x1004aa3f
  bspRepartition entry (Editor.dll 0x10049fc0): esp+4=Model, esp+8=iChild (node index), esp+0xc=2.
  bspAddNode (Editor.dll 0x10034e80): esp+4=Model, esp+8=iParent, esp+0xc=ENodePlace,
  esp+0x10=NodeFlags, esp+0x14=FPoly* (Base=+0x00, Normal=+0x0c, NumVertices=+0x1c0, iLink=+0x1c4).
  bspRefresh post-state marker inside bspRepartition: 0x1004a05f (matches repart_stage_unatco.py).

Usage:  repart_child_trace.py <child_node_index> [golden.dx]
  -> logs/repart-child-<N>.log  (CALL lines for every bspRepartition entry, ADD lines for every
     bspAddNode call while the target child is the active repartition)
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
break *0x10049fc0
commands
silent
set $callidx = $callidx + 1
set $child = *(int *)($esp + 8)
printf "CALL idx=%d model=%#x child=%d third=%d\n", $callidx, *(unsigned int *)($esp + 4), $child, *(int *)($esp + 0xc)
if $child == $target
  printf "TARGET_BEGIN idx=%d\n", $callidx
  enable 3
  enable 4
  set $fbs_seen = 0
end
continue
end
break *0x1004a05f
commands
silent
printf "STAGEEND idx=%d\n", $callidx
if $callidx > 0 && $child == $target
  printf "TARGET_END\n"
  disable 3
  disable 4
  detach
  quit
end
continue
end
break *0x10034e80
commands
silent
set $e = *(unsigned int *)($esp + 0x14)
printf "ADD parent=%d place=%d flags=%#x ilink=%d nv=%d N=%.6f,%.6f,%.6f B=%.6f,%.6f,%.6f\n", *(int *)($esp + 8), *(int *)($esp + 0xc), *(unsigned int *)($esp + 0x10), *(int *)($e + 0x1c4), *(int *)($e + 0x1c0), *(float *)($e + 0xc), *(float *)($e + 0x10), *(float *)($e + 0x14), *(float *)($e), *(float *)($e + 4), *(float *)($e + 8)
continue
end
break *0x100338EE
commands
silent
if $fbs_seen == 0
  set $fbs_seen = 1
  set $w = $eax
  printf "FBS numpolys=%d opt=%d balance=%d stride=%d winN=%.6f,%.6f,%.6f winB=%.6f,%.6f,%.6f\n", *(int *)($ebp + 8), *(int *)($ebp + 0x10), *(int *)($ebp + 0x14), *(int *)($ebp - 0x18), *(float *)($w + 0xc), *(float *)($w + 0x10), *(float *)($w + 0x14), *(float *)($w), *(float *)($w + 4), *(float *)($w + 8)
end
continue
end
disable 3
disable 4
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

    container = f"uned-repartchild-{TARGET_CHILD}"
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
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/rct.gdb"],
                       input=GDB.format(pid=pid, target=TARGET_CHILD), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/rct.gdb > /tmp/rct.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/rct.log 2>/dev/null || true"],
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
                                "grep -c '^CALL ' /tmp/rct.log 2>/dev/null || true"],
                               capture_output=True, text=True).stdout.strip()
            prev = int(n or 0)
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c '^TARGET_END' /tmp/rct.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                print(f"[trace] TARGET_END seen after {prev} bspRepartition calls", flush=True)
                break
            time.sleep(POLL)
        else:
            print(f"[trace] WARNING: gave up after {DEADLINE:.0f}s, {prev} CALL lines seen "
                  "(target child never hit)", flush=True)
        out = HERE.parent / "logs" / f"repart-child-{TARGET_CHILD}.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/rct.log"],
                                       capture_output=True).stdout)
        print(f"[trace] wrote {out} ({prev} bspRepartition calls seen)", flush=True)
        text = out.read_text(errors="replace")
        n_add = text.count("\nADD ")
        n_target = text.count("TARGET_BEGIN")
        print(f"[trace] target hit {n_target} time(s); {n_add} ADD lines captured for it", flush=True)
    finally:
        O.stop_dbg_editor(container, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
