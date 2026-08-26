#!/usr/bin/env python3
r"""EDITOR `bspRepartition` STAGE COUNTS at full-UNATCO scale.

`repart_stage_oracle.py` does this at castle scale against a hardcoded developer path; this is the
same five breakpoints run on the real 734-brush UNATCO golden.

Why it matters: the editor's node array carries no marker separating repartition-built nodes from
the ones the later semisolid/detail-brush CSG layer appends, so a node-count gap against a native
build cannot be attributed to a stage from the golden `.dx` alone. These counts split it.

READ THE LOG CAREFULLY — one `MAP REBUILD` produces MANY groups, not one. The FIRST group is the
world repartition (`csgRebuild 0x1004a89a`). Every group after it is one of `csgRebuild`'s ~209
per-node SUB-BSP repartitions (`0x1004aa3f`/`0x1004aa90`), which run AFTER the detail-brush loop and
before `bspOptGeom`; their `A_entry` is not "the finished tree" and their cumulative effect on
`Verts`/`Points`/`Surfs` is large.

bspRepartition (`Editor.dll 0x49fc0`) issues, in order:
  0x1004a00d  after bspBuildFPolys (MakeEdPolys -> Model->Polys)
  0x1004a027  after bspMergeCoplanars
  0x1004a047  after bspBuild (EmptyModel(0,0) + SplitPolyList)
  0x1004a05f  after bspRefresh(Model, NoRemapSurfs=1)
Model arg is `[esp+4]` at entry; fields Nodes.Num(+0x5c), Verts.Num(+0x6c), Points.Num(+0x8c),
Surfs.Num(+0x9c).

Usage:  repart_stage_unatco.py [golden.dx]   ->  logs/repart-stage-unatco.log
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
PROJECT_DIR = ROOT / "_scratch/oracle-project"
POLL, QUIET_FOR, DEADLINE = 2.0, 60.0, 2400.0


def dump(lbl):
    return (r'printf "%s nodes=%d verts=%d points=%d surfs=%d\n", "' + lbl + r'", '
            r'*(int *)($m + 0x5c), *(int *)($m + 0x6c), *(int *)($m + 0x8c), *(int *)($m + 0x9c)')


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
break *0x10049fc0
commands
silent
set $m = *(unsigned int *)($esp + 4)
""" + dump("A_entry") + r"""
continue
end
break *0x1004a00d
commands
silent
""" + dump("B_makeedpolys") + r"""
continue
end
break *0x1004a027
commands
silent
""" + dump("C_mergecoplanar") + r"""
continue
end
break *0x1004a047
commands
silent
""" + dump("D_bspbuild") + r"""
continue
end
break *0x1004a05f
commands
silent
""" + dump("E_bsprefresh") + r"""
printf "STAGEEND\n"
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def _wait(container, needle, tries, log="/tmp/rsu.log"):
    for _ in range(tries):
        out = subprocess.run(["docker", "exec", container, "bash", "-c",
                              f"grep -c {needle} {log} 2>/dev/null || true"],
                             capture_output=True, text=True).stdout.strip()
        if out and out != "0":
            return True
        time.sleep(1.0)
    return False


def main():
    if not PROJECT_DIR.exists():
        PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        (PROJECT_DIR / "uedcli.toml").write_text('game = "deusex"\n')

    O._ensure_dbg_image()
    project = config.load_project(str(PROJECT_DIR))
    user_config = config.load_user_config()
    mounts = resource_mounts(config.composed_search_dirs(project, user_config))
    state_dir = config.state_dir(project.root, create=True)

    container = "uned-repartstage-unatco"
    O.stop_dbg_editor(container, state_dir)
    print(f"starting {container} (golden={GOLDEN}) ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/rsu.gdb"],
                       input=GDB.format(pid=pid), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/rsu.gdb > /tmp/rsu.log 2>&1"], check=True)
        _wait(container, "ORACLE_ATTACHED", 120)
        print("attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        # One `MAP REBUILD` yields MANY groups (the world repartition then ~209 sub-BSP ones), so
        # wait for the group count to go QUIET rather than for a fixed number, with a hard cap so a
        # wedged editor cannot park the run (`rules/background-work.md`).
        prev, quiet, deadline = -1, 0.0, time.monotonic() + DEADLINE
        while quiet < QUIET_FOR:
            if time.monotonic() > deadline:
                print(f"WARNING: gave up after {DEADLINE:.0f}s with {max(prev, 0)} groups seen",
                      flush=True)
                break
            n = subprocess.run(["docker", "exec", container, "bash", "-c",
                                "grep -c STAGEEND /tmp/rsu.log 2>/dev/null || true"],
                               capture_output=True, text=True).stdout.strip()
            n = int(n or 0)
            quiet = quiet + POLL if (n == prev and n > 0) else 0.0
            prev = n
            time.sleep(POLL)
        out = HERE / "logs" / "repart-stage-unatco.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/rsu.log"],
                                       capture_output=True).stdout)
        print(f"wrote {out}", flush=True)
        for line in out.read_text(errors="replace").splitlines():
            if " nodes=" in line:
                print("  " + line)
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    main()
