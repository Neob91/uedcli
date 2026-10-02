#!/usr/bin/env python3
r"""Live GDB capture: `UModel::EmptyModel(int,int)`'s "this" object and args, plus the persistent
world Model's own pool sizes, bracketing the WORLD-level `bspRepartition(Model, 0)` call (the first
of the 209/119 `bspRepartition` calls in one `MAP REBUILD`).

WHY. `unatco-verts-points-residual-after-the-zone` / `wanchai-verts-points-residual-independently`
(2026-08-30, Points-residual entry) found the single biggest per-stage Points/Verts/Nodes/Surfs gap
on BOTH levels opens at the world-level `bsp_build` checkpoint, and flagged this as matching, IN
SHAPE, a pre-2026-08-14 (owner-invalidated) disassembly claim that `EmptyModel(0,0)` keeps
Points/Vectors/Surfs and only unconditionally clears Nodes/Verts. That claim was never re-derived
live. This script re-derives it from scratch:

1. Confirms the RVA of `UModel::EmptyModel` two ways, independent of the old doc: Engine.dll's own
   export table (`?EmptyModel@UModel@@QAEXHH@Z`, RVA 0x16ff10) AND Editor.dll's IMPORT table (IAT
   slot 0x100cee24 holds the resolved runtime address at load time) -- both read directly from the
   PE files on disk this session, not copied from any prior write-up.
2. Fresh disassembly of the function body (Engine.dll RVA 0x16ff10-0x170121, done this session, not
   copied from the old doc) confirms which fields are unconditionally cleared vs gated on the two
   int args: Nodes(+0x58)/Verts(+0x68) unconditional; Vectors(+0x78)/Points(+0x88)/Surfs(+0x98)
   gated as ONE block on arg1 (EmptySurfInfo) -- `EmptyModel(0,0)` skips that block, i.e. keeps
   them. Independently reproduces the old claim's shape from a fresh read of the binary.
3. THE PART NEVER LIVE-CHECKED BEFORE: `bspBuild` calls EmptyModel via `mov ecx, esi; call [IAT
   0x100cee24]`, where `esi` is a "CTX" pointer distinct from `ebx` (bspBuild's own arg1 = the
   persistent world Model that `bspAddNode` writes into directly, per
   `repart_addnode_model_trace.py`/`nodesnum_watch.py`, already confirmed this session in
   `native-materialize-findings.md`). If CTX != persistent Model at the WORLD-level call
   specifically, EmptyModel(0,0)'s keep/clear semantics apply to a SCRATCH object, not to the model
   whose Points/Vectors/Surfs `regression_gate.py` actually measures. This script captures `ecx`
   (EmptyModel's own "this") vs `ebx` (bspBuild's persistent-Model arg, still live in the
   callee-saved register at EmptyModel's own entry) AND both objects' Nodes/Verts/Points/Vectors/
   Surfs.Num before and after the EmptyModel call -- AND, independent of correctly identifying
   "this", the persistent Model's own pool sizes at `bspRepartition`(child=0) ENTRY vs its
   `bspRefresh`-completion return (the STAGEEND marker used throughout this investigation), which
   answers the real question (does the WORLD-level repartition call net-clear the persistent
   model's pools) even if EmptyModel itself never touches that object at all.

Scoped tightly to call #1 (world-level, child=0) only: breakpoints on EmptyModel's entry/return stay
disabled until the world-level `bspRepartition` entry fires, and the whole trace detaches at that
call's own `bspRefresh` completion -- avoids the noisy zone-pass/detail-brush-loop EmptyModel(1,1)
calls (per-brush TempModel resets) that happen between call #1 and call #2.

Usage:  emptymodel_worldlevel_trace.py [unatco|wanchai] [golden.dx]
  -> logs/emptymodel-worldlevel-<level>.log
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

LEVEL = sys.argv[1] if len(sys.argv) > 1 else "unatco"
DEFAULT_GOLDEN = {
    "unatco": ROOT / "_scratch/bsp-parity-proj/golden_unatco_control.dx",
    "wanchai": ROOT / "_scratch/golden_wanchai_world.dx",
}[LEVEL]
GOLDEN = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_GOLDEN
PROJECT_DIR = ROOT / "_scratch/oracle-project"
POLL, DEADLINE = 2.0, 1200.0

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
set $callidx = 0
set $child = -1
set $m = 0
set $saved_this = 0
set $in_world = 0
set $em_entry = *(unsigned int *)0x100cee24
set $em_ret = $em_entry + 0x211
printf "EM_ENTRY_VA=%#x EM_RET_VA=%#x\n", $em_entry, $em_ret
break *0x10049fc0
commands
silent
set $callidx = $callidx + 1
set $child = *(int *)($esp + 8)
set $m = *(unsigned int *)($esp + 4)
printf "REPART_CALL callidx=%d child=%d model=%#x m_nodes=%d m_verts=%d m_points=%d m_vectors=%d m_surfs=%d\n", $callidx, $child, $m, *(int*)($m+0x5c), *(int*)($m+0x6c), *(int*)($m+0x8c), *(int*)($m+0x7c), *(int*)($m+0x9c)
if $callidx == 1
  set $in_world = 1
  enable 3
  enable 4
end
continue
end
break *$em_entry
commands
silent
if $in_world == 1
  set $saved_this = $ecx
  printf "EM_ENTRY callidx=%d child=%d this=%#x bspbuild_ebx=%#x arg1=%d arg2=%d this_eq_ebx=%d this_eq_m=%d this_nodes=%d this_verts=%d this_points=%d this_vectors=%d this_surfs=%d ebx_nodes=%d ebx_verts=%d ebx_points=%d ebx_vectors=%d ebx_surfs=%d\n", $callidx, $child, $ecx, $ebx, *(int *)($esp+4), *(int *)($esp+8), ($ecx==$ebx), ($ecx==$m), *(int*)($ecx+0x5c), *(int*)($ecx+0x6c), *(int*)($ecx+0x8c), *(int*)($ecx+0x7c), *(int*)($ecx+0x9c), *(int*)($ebx+0x5c), *(int*)($ebx+0x6c), *(int*)($ebx+0x8c), *(int*)($ebx+0x7c), *(int*)($ebx+0x9c)
end
continue
end
break *$em_ret
commands
silent
if $in_world == 1
  printf "EM_RET callidx=%d child=%d this=%#x ebx=%#x this_nodes=%d this_verts=%d this_points=%d this_vectors=%d this_surfs=%d ebx_nodes=%d ebx_verts=%d ebx_points=%d ebx_vectors=%d ebx_surfs=%d\n", $callidx, $child, $saved_this, $ebx, *(int*)($saved_this+0x5c), *(int*)($saved_this+0x6c), *(int*)($saved_this+0x8c), *(int*)($saved_this+0x7c), *(int*)($saved_this+0x9c), *(int*)($ebx+0x5c), *(int*)($ebx+0x6c), *(int*)($ebx+0x8c), *(int*)($ebx+0x7c), *(int*)($ebx+0x9c)
end
continue
end
break *0x1004a05f
commands
silent
printf "STAGEEND callidx=%d child=%d model=%#x m_nodes=%d m_verts=%d m_points=%d m_vectors=%d m_surfs=%d\n", $callidx, $child, $m, *(int*)($m+0x5c), *(int*)($m+0x6c), *(int*)($m+0x8c), *(int*)($m+0x7c), *(int*)($m+0x9c)
if $callidx == 1
  printf "WORLD_END\n"
  disable 2
  disable 3
  disable 4
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

    container = f"uned-emptymodel-{LEVEL}"
    O.stop_dbg_editor(container, state_dir)
    print(f"[emptymodel] level={LEVEL} golden={GOLDEN}", flush=True)
    print(f"[emptymodel] starting {container} ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        print(f"[emptymodel] editor pid {pid}; attaching gdb ...", flush=True)
        gdb_script = GDB.format(pid=pid)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/emt.gdb"],
                       input=gdb_script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/emt.gdb > /tmp/emt.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/emt.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[emptymodel] attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        deadline = time.monotonic() + DEADLINE
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c '^WORLD_END' /tmp/emt.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                print("[emptymodel] WORLD_END seen", flush=True)
                break
            time.sleep(POLL)
        else:
            print(f"[emptymodel] WARNING: gave up after {DEADLINE:.0f}s, WORLD_END never seen",
                  flush=True)
        out = HERE.parent / "logs" / f"emptymodel-worldlevel-{LEVEL}.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/emt.log"],
                                       capture_output=True).stdout)
        print(f"[emptymodel] wrote {out}", flush=True)
    finally:
        O.stop_dbg_editor(container, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
