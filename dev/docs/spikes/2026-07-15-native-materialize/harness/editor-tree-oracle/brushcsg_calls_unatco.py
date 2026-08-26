#!/usr/bin/env python3
r"""EDITOR per-brush `bspBrushCSG` call trace at full-UNATCO scale.

`csgRebuild` runs two brush loops — structural brushes, then (after `bspRepartition`) the detail
layer. This breaks on `UEditorEngine::bspBrushCSG` (`Editor.dll 0x355e0`) and, per call, prints the
`PolyFlags`/`CsgOper` arguments plus `Model->Nodes.Num` and the length of ONE named node's coplanar
(`iPlane`) chain — so a chain that grows during the detail loop can be attributed to the exact brush
that grew it.

`WATCH_NODE` defaults to 2168, the `(0,-1,0,32)` splitter whose chain is 10 entries long in the
post-repartition tree and 26 in the finished UNATCO golden.

Args (thiscall `UEditorEngine::bspBrushCSG`): `[esp+4]`=Actor, `+8`=Model, `+0xc`=PolyFlags,
`+0x10`=CsgOper.  Model: Nodes.Data +0x58 / Num +0x5c.  FBspNode stride 0x40, iPlane +0x28.

Usage:  brushcsg_calls_unatco.py [golden.dx] [watch_node]  ->  logs/brushcsg-calls-unatco.log
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
HERE = HARNESS / "editor-tree-oracle"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HARNESS)); sys.path.insert(0, str(HERE))
import editor_tree_oracle as O
from uedcli import config
from uedcli.container_assets import resource_mounts
from uedcli.driver import Driver, to_z_path

GOLDEN = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/UEDGolden_unatco_full.dx")
WATCH = int(sys.argv[2]) if len(sys.argv) > 2 else 2168
PROJECT_DIR = ROOT / "_scratch/oracle-project"
POLL, QUIET_FOR = 2.0, 60.0  # stop once no new bspBrushCSG call has appeared for QUIET_FOR seconds
DEADLINE = 1800.0            # hard cap, so a wedged editor cannot park the run (and leak the container)

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
set $seq = 0
break *0x100355e0
commands
silent
set $seq = $seq + 1
set $mm = *(unsigned int *)($esp + 8)
set $nn = *(int *)($mm + 0x5c)
set $nd = *(unsigned int *)($mm + 0x58)
set $chain = 0
if $nn > {watch}
  set $c = *(int *)($nd + {watch} * 0x40 + 0x28)
  while $c != -1
    set $chain = $chain + 1
    set $c = *(int *)($nd + $c * 0x40 + 0x28)
  end
end
printf "BCSG seq=%d actor=%#x polyflags=%#x oper=%d nodes=%d chain=%d verts=%d points=%d surfs=%d\n", $seq, *(unsigned int *)($esp + 4), *(unsigned int *)($esp + 0xc), *(int *)($esp + 0x10), $nn, $chain, *(int *)($mm + 0x6c), *(int *)($mm + 0x8c), *(int *)($mm + 0x9c)
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def main():
    if not PROJECT_DIR.exists():
        PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        (PROJECT_DIR / "uedcli.toml").write_text('game = "deusex"\n')

    O._ensure_dbg_image()
    project = config.load_project(str(PROJECT_DIR))
    mounts = resource_mounts(config.composed_search_dirs(project, config.load_user_config()))
    state_dir = config.state_dir(project.root, create=True)

    container = "uned-brushcsg-unatco"
    O.stop_dbg_editor(container, state_dir)
    print(f"starting {container} (golden={GOLDEN}, watch node {WATCH}) ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/bcs.gdb"],
                       input=GDB.format(pid=pid, watch=WATCH), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/bcs.gdb > /tmp/bcs.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/bcs.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        print("attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        # One `bspBrushCSG` per brush, and the brush count is a property of the golden — so stop on
        # the call count going QUIET (no new call for `QUIET_FOR` seconds) rather than on a number.
        # `DEADLINE` is the hang-detector `rules/background-work.md` requires: a wedged editor, a
        # failed `MAP LOAD` or a lost attach never produces a first line, so the quiet counter alone
        # would spin forever and never reach the `finally` that tears the container down.
        prev, quiet, deadline = -1, 0.0, time.monotonic() + DEADLINE
        while quiet < QUIET_FOR:
            if time.monotonic() > deadline:
                print(f"WARNING: gave up after {DEADLINE:.0f}s with {max(prev, 0)} calls seen — "
                      "writing whatever the log holds", flush=True)
                break
            n = subprocess.run(["docker", "exec", container, "bash", "-c",
                                "grep -c '^BCSG ' /tmp/bcs.log 2>/dev/null || true"],
                               capture_output=True, text=True).stdout.strip()
            n = int(n or 0)
            quiet = quiet + POLL if (n == prev and n > 0) else 0.0
            prev = n
            time.sleep(POLL)
        out = HERE / "logs" / "brushcsg-calls-unatco.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/bcs.log"],
                                       capture_output=True).stdout)
        print(f"wrote {out}", flush=True)
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    main()
