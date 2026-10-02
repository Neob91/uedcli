#!/usr/bin/env python3
r"""Live GDB capture: the editor's REAL poly-list ORDER at `FindBestSplit`'s WORLD-LEVEL root entry
(`Editor.dll 0x100338EE`) -- the one-time `bspBuildFPolys`->`bspMergeCoplanars`->`bspBuild` call that
runs ONCE per `MAP REBUILD`, before any per-subtree `repartition_frontier` calls.

WHY. `freeclinic08-nsfhq04-1-surf-under-build-root` (2026-08-30 continuation) confirmed
freeclinic08's/nsfhq04's node/leaf deficit is fully present at `post-repartition` -- i.e. it comes
from THIS one-shot call, not `repartition_frontier` (already fixed for UNATCO, `bcc3693`, and
confirmed a no-op for these two levels). Offline analysis (this session, `fc08_fbs_dump.py`-style,
`UEDCLI_REPART_FBS_DUMP=1` on native's own `build_geometry_bspcsg`) found native's world-level
`split_poly_list` call for freeclinic08's 141-brush structural-only golden has `numpolys=1019`,
`Opt::Good` stride `inc=NumPolys/20=50`, so only candidates at slots 0,50,100,...,1000 (21 total) are
ever scored; native's own winner is slot 600 (`i=600`, plane (1,0,0,576), score=24.0). The editor's
REAL built golden (`_scratch/fc08-structural-only/golden_structural.dx`) has a DIFFERENT root split:
node[0].plane=(0,-1,0,896), i_surf=58 -- a plane that DOES exist in native's own 1019-poly soup (at
list index k=124, ilink=57), but k=124 is NEVER SAMPLED by native's own stride (window [100,150)'s
first-eligible candidate is index 100, not 124).

This script determines whether the SAME poly, in the EDITOR's real internal list order, lands on a
sampled slot (confirming a pure poly-ORDER divergence between native's `make_ed_polys`/
`bsp_merge_coplanars` reconstruction and the real `bspBuildFPolys`/`bspMergeCoplanars`) or not
(meaning the divergence is elsewhere -- a different NumPolys, a different stride, or a real scoring
difference).

MECHANISM (reused verbatim from `fbs_root_poly_order.py`'s FindBestSplit capture +
`emptymodel_worldlevel_trace.py`'s `callidx==1` world-level gating):
  bspRepartition entry (Editor.dll 0x10049fc0): esp+4=Model. The FIRST hit in a `MAP REBUILD` is the
    WORLD-level call (callidx==1) -- confirmed live in `emptymodel_worldlevel_trace.py` (STAGEEND
    node/vert/point counts at this call matched the pre-existing editor stage log exactly).
  bspRefresh post-state marker inside bspRepartition: 0x1004a05f (this call's own completion).
  FindBestSplit entry  (Editor.dll 0x100338EE): ebp+8=NumPolys, ebp+0xc=PolyPtrArray, ebp+0x10=Opt,
    ebp+0x14=Balance -- same offsets `fbs_root_poly_order.py` already proved live.
  FPoly layout: Base=+0x00, Normal=+0x0c, NumVertices=+0x1c0, iLink=+0x1c4 (from `bspAddNode`'s own
    live-verified layout).

Only fires ONCE (the first FindBestSplit hit while callidx==1's bspRepartition call is active -- the
world-level ROOT node, depth 0).

Usage:  fbs_world_poly_order.py <level-tag> <golden.dx>
  -> logs/fbs-world-poly-order-<level-tag>.log
     FBSHEADER: numpolys, arr pointer.
     FBSPOLY lines: k, i_link, normal, base.normal (plane distance) for every poly in the WORLD-level
     root's input list, in ORDER -- directly diffable against native's own `UEDCLI_REPART_FBS_DUMP`/
     `UEDCLI_BSPCSG_SOUP_ORDER` dump for the identical structural-only brush set.
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

TAG = sys.argv[1]
GOLDEN = Path(sys.argv[2])
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
set $active = 0
set $fbs_seen = 0
break *0x10049fc0
commands
silent
set $callidx = $callidx + 1
if $callidx == 1
  set $active = 1
  set $fbs_seen = 0
  printf "WORLD_BEGIN callidx=%d\n", $callidx
end
continue
end
break *0x1004a05f
commands
silent
if $active == 1 && $callidx == 1
  printf "WORLD_END\n"
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

    container = f"uned-fbsworld-{TAG}"
    O.stop_dbg_editor(container, state_dir)
    print(f"[fbsworld] tag={TAG} golden={GOLDEN}", flush=True)
    print(f"[fbsworld] starting {container} ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        print(f"[fbsworld] editor pid {pid}; attaching gdb ...", flush=True)
        gdb_script = GDB.replace("__PID__", str(pid))
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/fbw.gdb"],
                       input=gdb_script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/fbw.gdb > /tmp/fbw.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/fbw.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[fbsworld] attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        deadline = time.monotonic() + DEADLINE
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c '^WORLD_END' /tmp/fbw.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                print("[fbsworld] WORLD_END seen", flush=True)
                break
            time.sleep(POLL)
        else:
            print(f"[fbsworld] WARNING: gave up after {DEADLINE:.0f}s", flush=True)
        out = HERE.parent / "logs" / f"fbs-world-poly-order-{TAG}.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/fbw.log"],
                                       capture_output=True).stdout)
        print(f"[fbsworld] wrote {out}", flush=True)
        text = out.read_text(errors="replace")
        n = text.count("\nFBSPOLY ")
        print(f"[fbsworld] {n} FBSPOLY lines captured", flush=True)
    finally:
        O.stop_dbg_editor(container, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
