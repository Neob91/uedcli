#!/usr/bin/env python3
r"""Capture the editor's polygon rasterizer (`render.dll 0x1001b470`) live, with real arguments.

The gather (`URender::GetVisibleSurfs` -> `OccludeBsp`) turns each BSP node into screen spans in two
steps: `URender::ClipBspSurf` (`0x10013cf0`) transforms + frustum-clips + projects the node's vertex
ring into `FTransform`s, and the static scanline setup at `0x1001b470` turns that point list into one
`FRasterSpan {INT Start, End;}` per scanline plus the screen bounding box, then hands it to
`FSpanBuffer::CopyFromRaster[Update]`.

Per rasterizer call this dumps:

  - `CIN`  - the `iNode` `ClipBspSurf` was called with (the immediately preceding call),
  - `RIN`  - `NumPts`, `Frame->Y`, the `FSpanBuffer*` pre-test argument, and the frame's `Coords`
             (origin + the three axes), `Mirror` (`+0x20`) and `NearClip.W` (`+0x30`),
  - `RPT`  - every input point's view-space `Point`, `ScreenX`, `ScreenY` and `IntY`,
  - `RBOX` - the four screen-bound globals (`MinY 0x1005fa3c`, `MaxY 0x40`, `MinX 0x44`, `MaxX 0x48`)
             after the clamp pass and after `BoxIsVisible` accepted,
  - `RROW` - the `Start`/`End` the edge walk wrote for every row in `[MinY, MaxY)`,
  - `RREJ` - the `BoxIsVisible` early reject.

`RIN`+`RPT` -> `RBOX`+`RROW` is a closed input/output fixture for the rasterizer; `CIN` plus the
frame `Coords` additionally pins `ClipBspSurf` itself against the built model's node vertex ring.

Usage: raster_probe.py --trunk <subset-trunk-dir> [--out log] [--hits N]

Same relocation handling as `2026-09-06-boundvisible-port/harness/boundvisible_frame_probe.py`:
`render.dll` does NOT load at its preferred base under Wine (Editor.dll wins 0x10000000), so every
address is remapped through /proc/<pid>/maps.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OLD_HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
OLD_ORACLE = OLD_HARNESS / "editor-tree-oracle"
LADDER = ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness"
UNBUILT = ROOT / "dev/docs/spikes/2026-09-02-unbuilt-structure-parity/harness"
PARENT_HARNESS = ROOT / "dev/docs/spikes/2026-09-05-lightapply-node-flags/harness"
HERE = Path(__file__).resolve().parent
for p in (ROOT, OLD_HARNESS, OLD_ORACLE, LADDER, UNBUILT, PARENT_HARNESS):
    sys.path.insert(0, str(p))

import editor_tree_oracle as O  # noqa: E402
from uedcli import config, trunk  # noqa: E402
from uedcli.apply import _level_referenced_packages  # noqa: E402
from uedcli.container_assets import resource_mounts  # noqa: E402
from uedcli.driver import Driver, to_z_path  # noqa: E402
from uedcli.emit import emit_map  # noqa: E402
from uedcli.materialize import levelinfo_first_order  # noqa: E402
from uedcli.packages import editor_search_dirs, ensure_load  # noqa: E402
from build_ued_import_built_golden import _dummy_builder_actor  # noqa: E402
from build_ued_import_golden import _quote_str_props  # noqa: E402
from build_ued_golden import _scratch_project  # noqa: E402

CONTAINER = "uned-raster-probe"
RENDER_PREF = 0x10000000

CLIP_ENTRY = 0x10013CF0   # URender::ClipBspSurf
RASTER_ENTRY = 0x1001B470  # the scanline setup
RASTER_BOXOK = 0x1001B641  # `inc [0x1005fab8]` - BoxIsVisible accepted (or no span buffer)
RASTER_REJECT = 0x1001B628  # `inc [0x1005fabc]` - BoxIsVisible rejected
RASTER_DONE = 0x1001B79D   # `mov eax, 1` - the edge walk finished

G_FRAME = 0x1005FA28   # FSceneNode* the current gather frame
G_MINY = 0x1005FA3C
G_MAXY = 0x1005FA40
G_MINX = 0x1005FA44
G_MAXX = 0x1005FA48
G_RASTER = 0x1006080C  # FArray of FRasterSpan{Start,End}: Data ptr


def remap(addr: int, live_base: int) -> int:
    return live_base + (addr - RENDER_PREF)


GDB_TEMPLATE = r"""
set pagination off
set confirm off
set height 0
set width 0
attach __PID__
handle SIGSEGV nostop noprint pass
handle SIGUSR1 nostop noprint pass
handle SIGUSR2 nostop noprint pass
handle SIGPIPE nostop noprint pass

set $hits = 0
set $node = -1
set $npts = 0

break *__RASTER__
commands
silent
set $hits = $hits + 1
set $pts = *(unsigned int*)($esp+4)
set $npts = *(int*)($esp+8)
set $sp = *(unsigned int*)($esp+12)
set $fy = *(int*)($esp+16)
set $ok = 0
if $pts > 0x10000 && $npts > 0 && $npts < 64
  set $ok = 1
end
if $ok == 1
  printf "RIN hit=%d npts=%d framey=%d span=%#x\n", $hits, $npts, $fy, $sp
  set $i = 0
  while $i < $npts
    set $p = *(unsigned int*)($pts + $i*4)
    if $p > 0x10000
      printf "RPT hit=%d i=%d pt=[%.9g,%.9g,%.9g] sx=%.9g sy=%.9g iy=%d\n", $hits, $i, *(float*)$p, *(float*)($p+4), *(float*)($p+8), *(float*)($p+16), *(float*)($p+20), *(int*)($p+24)
    end
    if $p <= 0x10000
      printf "RPT hit=%d i=%d BADPTR=%#x\n", $hits, $i, $p
    end
    set $i = $i + 1
  end
end
if $ok == 0
  printf "RBAD hit=%d pts=%#x npts=%d\n", $hits, $pts, $npts
end
continue
end

break *__REJECT__
commands
silent
printf "RREJ hit=%d\n", $hits
continue
end

break *__BOXOK__
commands
silent
printf "RBOX hit=%d minx=%d miny=%d maxx=%d maxy=%d\n", $hits, *(int*)(__GMINX__), *(int*)(__GMINY__), *(int*)(__GMAXX__), *(int*)(__GMAXY__)
continue
end

break *__DONE__
commands
silent
set $ra = *(unsigned int*)(__GRASTER__)
set $y = *(int*)(__GMINY__)
set $ye = *(int*)(__GMAXY__)
if $ra > 0x10000 && $y >= 0 && $ye <= 1024
  while $y < $ye
    printf "RROW hit=%d y=%d s=%d e=%d\n", $hits, $y, *(int*)($ra + $y*8), *(int*)($ra + $y*8 + 4)
    set $y = $y + 1
  end
end
if $ra <= 0x10000
  printf "RNORASTER hit=%d ra=%#x y=%d ye=%d\n", $hits, $ra, $y, $ye
end
printf "REND hit=%d\n", $hits
if $hits >= __HITS__
  printf "TARGET_DONE\n"
  detach
  quit
end
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def _find_render_base(container: str, pid: int) -> int:
    maps = subprocess.run(["docker", "exec", container, "cat", f"/proc/{pid}/maps"],
                          capture_output=True, text=True, check=True).stdout
    for line in maps.splitlines():
        if "render.dll" in line.lower():
            return int(line.split("-", 1)[0], 16)
    raise RuntimeError("render.dll not found")


def main() -> int:
    trunk_dir = None
    hits = 250
    out = HERE.parent / "logs" / "raster-probe.log"
    for i, a in enumerate(sys.argv):
        if a == "--trunk":
            trunk_dir = Path(sys.argv[i + 1]).resolve()
        if a == "--out":
            out = Path(sys.argv[i + 1]).resolve()
        if a == "--hits":
            hits = int(sys.argv[i + 1])
    if trunk_dir is None:
        print(__doc__)
        return 2

    user_config = config.load_user_config()
    project = _scratch_project(trunk_dir, "deusex")
    search_dirs = config.composed_search_dirs(project, user_config)
    mounts = resource_mounts(search_dirs)
    host_search_dirs = editor_search_dirs(search_dirs)

    lvl, _ = trunk.read_level(trunk_dir)
    classes = {n: lvl.actors[n].cls for n in lvl.order}
    has_brush = {n: lvl.actors[n].brush is not None for n in lvl.order}
    imp_order = levelinfo_first_order(lvl.order, classes, has_brush)
    _quote_str_props(lvl, imp_order, project, user_config)
    actors = [lvl.actors[n] for n in imp_order]
    actors.insert(1, _dummy_builder_actor())
    ref_pkgs = _level_referenced_packages(
        type("L", (), {"actors": {n: lvl.actors[n] for n in imp_order}})())

    O._ensure_dbg_image()
    state_dir = config.state_dir(project.root, create=True)
    O.stop_dbg_editor(CONTAINER, state_dir)
    print(f"[raster] {trunk_dir.name}; starting {CONTAINER}", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        t3d_path = drv.write_work_file(emit_map(actors), ext="t3d")
        pid = O._editor_pid(CONTAINER)
        render_base = _find_render_base(CONTAINER, pid)
        print(f"[raster] render.dll live base = {render_base:#x}", flush=True)
        rep = {
            "__PID__": str(pid),
            "__RASTER__": hex(remap(RASTER_ENTRY, render_base)),
            "__BOXOK__": hex(remap(RASTER_BOXOK, render_base)),
            "__REJECT__": hex(remap(RASTER_REJECT, render_base)),
            "__DONE__": hex(remap(RASTER_DONE, render_base)),
            "__GFRAME__": hex(remap(G_FRAME, render_base)),
            "__GMINY__": hex(remap(G_MINY, render_base)),
            "__GMAXY__": hex(remap(G_MAXY, render_base)),
            "__GMINX__": hex(remap(G_MINX, render_base)),
            "__GMAXX__": hex(remap(G_MAXX, render_base)),
            "__GRASTER__": hex(remap(G_RASTER, render_base)),
            "__HITS__": str(hits),
        }
        script = GDB_TEMPLATE
        for k, v in rep.items():
            script = script.replace(k, v)
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/rast.gdb"],
                       input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/rast.gdb > /tmp/rast.log 2>&1"], check=True)
        for _ in range(240):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/rast.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[raster] attached; running the golden EXEC batch ...", flush=True)
        saved = "/work/probe_rast.dx"
        drv.begin_script()
        ensure_load(drv, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        drv.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        drv.exec("MAP REBUILD")
        drv.light_apply()
        drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
        try:
            drv.run_script(produces=saved, timeout=1800.0)
        except Exception as ex:
            print(f"[raster] batch wait ended: {ex}", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        log_bytes = subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/rast.log"],
                                   capture_output=True).stdout
        out.write_bytes(f"render.dll live base = {render_base:#x}\n\n".encode() + log_bytes)
        print(f"[raster] wrote {out}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
