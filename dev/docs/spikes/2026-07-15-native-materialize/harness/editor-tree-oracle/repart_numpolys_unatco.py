#!/usr/bin/env python3
r"""EDITOR bspRepartition ROOT NumPolys ORACLE at FULL-UNATCO scale.

Answers the one open number in board item `editor-unatco-repartition-soup-size-unknown`: what
`NumPolys` does the editor's `bspRepartition` hand to `bspBuild`/`SplitPolyList` at the WORLD-TREE
repartition (not the per-brush temp-BSP calls `bspBrushCSG` also drives through `SplitPolyList`)?
Native's equivalent (the post-`bspMergeCoplanars` soup, before `bsp_build`'s own nv==0 filter) is
2504 (`UEDCLI_BSPCSG_SOUP_ORDER=1`, full 734-brush UNATCO).

WHERE.  `bspRepartition` (`Editor.dll 0x49fc0`) issues, in order, `bspBuildFPolys`,
`bspMergeCoplanars`, then `bspBuild` (`call [edx+0x1fc]` at VA `0x1004a041` — `editor_polys_oracle.py`'s
breakpoint, decoded and reused verbatim; that address is INSIDE `bspRepartition` specifically, so it
can only ever be the world-tree repartition call — the per-brush temp-BSP calls inside
`bspBrushCSG`/`bspBuildBounds` live at different call sites entirely, no Balance/PortalBias
disambiguation needed). At the call site `[esp]=Model` (args already pushed). `bspBuild` (`0x35ef0`)
reads `Model->Polys` (UModel+0x54, a UPolys*): `Element` TArray at `Data=UPolys+0x28`,
`Num=UPolys+0x2c`, `sizeof(FPoly)=0x1d8`, `NumVertices=FPoly+0x1c0`. This is the poly list AS OF the
merge, BEFORE `bspBuild`'s own internal filter (which drops `NumVertices==0` entries into a temp
pointer array before calling `SplitPolyList`) — the same "before its own finalize filter" cut native's
2504 is measured at.

HOW.  No re-ingested T3D trunk is needed: `/tmp/UEDGolden_unatco_full.dx` is already a built editor
golden (`build_ued_golden.py`, bare `MAP REBUILD` basis), and `MAP LOAD` demand-loads its content
packages via the same asset mounts as every other UNATCO oracle (`dev/docs/unrealed/quirks.md`:
"Content packages resolve via MAP LOAD/demand-load" — no explicit `OBJ LOAD` required for a
geometry-only capture, matching `editor_polys_oracle.py`'s castle-scale precedent). The project is a
throwaway `game = "deusex"` `uedcli.toml` (no trunk/maps key) purely to get `composed_search_dirs`
for the asset mounts from the user's `[games.deusex]` config.

Usage:  repart_numpolys_unatco.py [golden.dx]   ->  logs/repart-numpolys-unatco.log
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]      # editor-tree-oracle/ -> harness/ -> spike/ -> spikes/ -> docs/ -> dev/ -> root
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
HERE = HARNESS / "editor-tree-oracle"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HARNESS)); sys.path.insert(0, str(HERE))
import editor_tree_oracle as O
from uedcli import config
from uedcli.container_assets import resource_mounts
from uedcli.driver import Driver, to_z_path

GOLDEN = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/UEDGolden_unatco_full.dx")
VA = 0x1004A041
# Under ROOT (not /tmp): bind-mount sources for `docker compose run` are resolved by the OUTER
# docker daemon against the host filesystem, which only shares the checkout path with this agent
# sandbox -- a path under this container's private /tmp is invisible to the daemon.
PROJECT_DIR = ROOT / "_scratch/oracle-project"  # throwaway game=deusex project

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
break *{va:#x}
commands
silent
set $model = *(unsigned int *)($esp)
set $polys = *(unsigned int *)($model + 0x54)
set $data = *(unsigned int *)($polys + 0x28)
set $num = *(int *)($polys + 0x2c)
set $i = 0
set $nz = 0
while $i < $num
  set $fpol = $data + $i * 0x1d8
  set $nv = *(int *)($fpol + 0x1c0)
  if $nv > 0
    set $nz = $nz + 1
  end
  set $i = $i + 1
end
printf "REPART_BUILD model=%#x polys=%#x num=%d nonzero_nv=%d\n", $model, $polys, $num, $nz
printf "REPARTEND\n"
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
    user_config = config.load_user_config()
    search_dirs = config.composed_search_dirs(project, user_config)
    mounts = resource_mounts(search_dirs)
    state_dir = config.state_dir(project.root, create=True)

    container = "uned-repartnumpolys-unatco"
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
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/rnp.gdb"],
                       input=GDB.format(pid=pid, va=VA), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/rnp.gdb > /tmp/rnp.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/rnp.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        print("attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        for _ in range(1500):
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c REPARTEND /tmp/rnp.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                break
            time.sleep(1.0)
        out = HERE / "logs" / "repart-numpolys-unatco.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        data = subprocess.run(["docker", "exec", container, "cat", "/tmp/rnp.log"],
                              capture_output=True).stdout
        out.write_bytes(data)
        print(f"wrote {out}", flush=True)
        print(subprocess.run(["bash", "-c", f"grep REPART_BUILD {out}"],
                             capture_output=True, text=True).stdout)
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    main()
