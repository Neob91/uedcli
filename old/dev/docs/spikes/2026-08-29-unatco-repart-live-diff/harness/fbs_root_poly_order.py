#!/usr/bin/env python3
r"""Live GDB capture: the editor's REAL poly-list ORDER at `FindBestSplit`'s root-level entry
(`Editor.dll 0x100338EE`) for ONE target `bspRepartition` call — to check whether native's
`make_ed_polys` tree-walk order matches the editor's real `bspBuildFPolys` order, specifically for
`child=6108`'s two `i_link=3513` duplicate-poly instances (native-side: `bspcsg.rs`'s
`UEDCLI_REPART_TRACE_LINK` diagnostic found native splits one of them at the tree ROOT, and
root-caused it to a stride-sampled scoring blind spot that is disassembly-verified faithful to the
editor's OWN heuristic (`findbestsplit-params-decode.md`) — so if native's output still diverges
from the editor's real 40-node/no-splits result, the poly ORDER itself must differ).

MECHANISM (reused verbatim from `repart_child_trace.py`, itself proven reliable):
  bspRepartition entry (Editor.dll 0x10049fc0): esp+4=Model, esp+8=iChild (node index), esp+0xc=2.
  bspRefresh post-state marker inside bspRepartition: 0x1004a05f.
  FindBestSplit entry  (Editor.dll 0x100338EE): ebp+8=NumPolys, ebp+0xc=PolyPtrArray (TArray<FPoly*>
    data pointer -- unconfirmed by this repo's prior notes, verified live by this script itself: each
    dereferenced entry's own NumVertices field, +0x1c0, must land in [3,40] to sanity-check the
    offset), ebp+0x10=Opt, ebp+0x14=Balance, ebp-0x18=stride (all from `repart_child_trace.py`'s own
    existing GDB script, already committed and proven).
  FPoly layout (from `repart_child_trace.py`'s own bspAddNode read): Base=+0x00, Normal=+0x0c,
    NumVertices=+0x1c0, iLink=+0x1c4.

Only fires ONCE per target (the FIRST FindBestSplit hit while the target child's bspRepartition call
is active -- i.e. the ROOT-level call, matching `repart_child_trace.py`'s own `$fbs_seen` gate).

Usage:  fbs_root_poly_order.py <child_node_index> [golden.dx]
  -> logs/fbs-root-poly-order-<N>.log
     FBSPOLY lines: k, i_link, normal, base.normal (plane distance) for every poly in the root's
     input list, in ORDER -- directly diffable against native's own FBSIN dump (bspcsg.rs
     UEDCLI_REPART_FBS_INPUT) for the same child.
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
attach __PID__
handle SIGSEGV nostop noprint pass
handle SIGUSR1 nostop noprint pass
handle SIGUSR2 nostop noprint pass
handle SIGPIPE nostop noprint pass
set $target = __TARGET__
set $child = -1
set $active = 0
set $fbs_seen = 0
break *0x10049fc0
commands
silent
set $child = *(int *)($esp + 8)
if $child == $target
  set $active = 1
  set $fbs_seen = 0
  printf "TARGET_BEGIN child=%d\n", $child
end
continue
end
break *0x1004a05f
commands
silent
if $active == 1 && $child == $target
  printf "TARGET_END\n"
  set $active = 0
  detach
  quit
end
continue
end
break *0x100338EE
commands
silent
if $active == 1 && $fbs_seen == 0
  set $fbs_seen = 1
  set $numpolys = *(int *)($ebp + 8)
  set $arr = *(unsigned int *)($ebp + 0xc)
  printf "FBSHEADER numpolys=%d arr=%#x\n", $numpolys, $arr
  set $k = 0
  while $k < $numpolys
    set $p = *(unsigned int *)($arr + $k * 4)
    set $nv = *(int *)($p + 0x1c0)
    set $ilink = *(int *)($p + 0x1c4)
    set $nx = *(float *)($p + 0xc)
    set $ny = *(float *)($p + 0x10)
    set $nz = *(float *)($p + 0x14)
    set $bx = *(float *)($p)
    set $by = *(float *)($p + 4)
    set $bz = *(float *)($p + 8)
    set $d = $nx * $bx + $ny * $by + $nz * $bz
    printf "FBSPOLY k=%d i_link=%d nv=%d normal=%.6f,%.6f,%.6f dist=%.6f\n", $k, $ilink, $nv, $nx, $ny, $nz, $d
    set $k = $k + 1
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

    container = f"uned-fbsroot-{TARGET_CHILD}"
    O.stop_dbg_editor(container, state_dir)
    print(f"[fbsroot] target child={TARGET_CHILD} golden={GOLDEN}", flush=True)
    print(f"[fbsroot] starting {container} ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        print(f"[fbsroot] editor pid {pid}; attaching gdb ...", flush=True)
        gdb_script = GDB.replace("__PID__", str(pid)).replace("__TARGET__", str(TARGET_CHILD))
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/fbr.gdb"],
                       input=gdb_script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/fbr.gdb > /tmp/fbr.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/fbr.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[fbsroot] attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        deadline = time.monotonic() + DEADLINE
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c '^TARGET_END' /tmp/fbr.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                print("[fbsroot] TARGET_END seen", flush=True)
                break
            time.sleep(POLL)
        else:
            print(f"[fbsroot] WARNING: gave up after {DEADLINE:.0f}s", flush=True)
        out = HERE.parent / "logs" / f"fbs-root-poly-order-{TARGET_CHILD}.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/fbr.log"],
                                       capture_output=True).stdout)
        print(f"[fbsroot] wrote {out}", flush=True)
        text = out.read_text(errors="replace")
        n = text.count("\nFBSPOLY ")
        print(f"[fbsroot] {n} FBSPOLY lines captured", flush=True)
    finally:
        O.stop_dbg_editor(container, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
