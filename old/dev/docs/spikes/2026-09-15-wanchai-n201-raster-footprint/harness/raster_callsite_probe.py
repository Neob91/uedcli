#!/usr/bin/env python3
r"""Capture the real editor's scanline-setup INPUT/OUTPUT (`render.dll 0x1001b470`) for a WHOLE
`LIGHT APPLY` run, WITHOUT ever breakpointing that hot routine's own body -- which
`2026-09-06-raster-clipbspsurf-port/spike.md` documents as crashing the debug container (shared with
real-time viewport rendering, hit continuously even at editor idle).

The fix: `URender::OccludeBsp` calls the scanline setup from ONE call site, `render.dll 0x10019a6c`
(confirmed live, `disasm_callsite.py`/`logs/disasm-callsite.log`: `call 0x1001b470` there, cdecl args
`push Frame->Y; push (span or 0); push NumPts; push Pts`). OccludeBsp ITSELF is gather-exclusive --
`raster_order_probe.py`'s 0x10019c1c breakpoint (deeper in the same function) already ran a FULL
LIGHT APPLY pass with ~10,000 hits with no crash. Breakpointing the CALL SITE (before the call, and
at its return, call+5) sees the same inputs/outputs raster_setup's own entry/exit would, but the trap
only ever fires from OccludeBsp's own gather path -- never from whatever OTHER call site the viewport
renderer uses to reach the same low-level routine.

Gated by (Frame->Coords.Origin, Frame->Coords.ZAxis) matching one light+face exactly (same 0.5uu
convention as `raster_order_probe.py`/`box_verdict_n153.py`), to keep the hit count low and the log
readable -- one light's one face, not the whole run.

Per hit this dumps:
  PRECALL: isurf, numpts, span(0 or nonzero), framey
  POSTCALL: return eax (0 = no rows), MinY/MaxY, and every row's Start/End in [MinY,MaxY)

Usage: raster_callsite_probe.py --trunk <subset-trunk-dir> --origin x,y,z --zaxis x,y,z [--out log]
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
HERE = Path(__file__).resolve().parent
for p in (ROOT, OLD_HARNESS, OLD_ORACLE, LADDER, UNBUILT):
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

CONTAINER = "uned-n201-raster-callsite"
RENDER_PREF = 0x10000000

PRECALL = 0x10019A6C   # OccludeBsp's own call site to the scanline setup (before `call`)
POSTCALL = 0x10019A71  # right after it (`add $0x10,%esp` already executed by the time we land here
                        # -- gdb breaks BEFORE the instruction at this address, so esp is already
                        # restored; we read eax/ecx and the globals, not the stack)

G_MINY = 0x1005FA3C
G_MAXY = 0x1005FA40
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
set $ox = __OX__
set $oy = __OY__
set $oz = __OZ__
set $zx = __ZX__
set $zy = __ZY__
set $zz = __ZZ__

break *__PRECALL__
commands
silent
set $fr = *(unsigned int*)($ebp-0x8b4)
set $forigx = *(float*)($fr+0x34)
set $forigy = *(float*)($fr+0x38)
set $forigz = *(float*)($fr+0x3c)
set $fzx = *(float*)($fr+0x4c)
set $fzy = *(float*)($fr+0x50)
set $fzz = *(float*)($fr+0x54)
set $dox = $forigx - $ox
set $doy = $forigy - $oy
set $doz = $forigz - $oz
set $dzx = $fzx - $zx
set $dzy = $fzy - $zy
set $dzz = $fzz - $zz
set $match = 1
if $dox <= -0.5 || $dox >= 0.5
  set $match = 0
end
if $doy <= -0.5 || $doy >= 0.5
  set $match = 0
end
if $doz <= -0.5 || $doz >= 0.5
  set $match = 0
end
if $dzx <= -0.01 || $dzx >= 0.01
  set $match = 0
end
if $dzy <= -0.01 || $dzy >= 0.01
  set $match = 0
end
if $dzz <= -0.01 || $dzz >= 0.01
  set $match = 0
end
set $active = $match
if $match == 1
  set $hits = $hits + 1
  set $node = *(unsigned int*)($ebp-0x8bc)
  set $isurf = *(int*)($node+0x1c)
  set $pts = *(unsigned int*)($esp+0)
  set $npts = *(int*)($esp+4)
  set $span = *(unsigned int*)($esp+8)
  set $fy = *(int*)($esp+12)
  printf "PRECALL hit=%d isurf=%d numpts=%d span=%#x framey=%d\n", $hits, $isurf, $npts, $span, $fy
end
continue
end

break *__POSTCALL__
commands
silent
if $active == 1
  set $y = *(int*)(__GMINY__)
  set $ye = *(int*)(__GMAXY__)
  printf "POSTCALL hit=%d ret=%d miny=%d maxy=%d\n", $hits, $eax, $y, $ye
  set $ra = *(unsigned int*)(__GRASTER__)
  if $eax != 0 && $ra > 0x10000 && $ye > $y && ($ye - $y) < 2000
    while $y < $ye
      printf "ROW hit=%d y=%d s=%d e=%d\n", $hits, $y, *(int*)($ra + $y*8), *(int*)($ra + $y*8 + 4)
      set $y = $y + 1
    end
  end
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
    origin = None
    zaxis = None
    out = HERE.parent / "logs" / "raster-callsite.log"
    for i, a in enumerate(sys.argv):
        if a == "--trunk":
            trunk_dir = Path(sys.argv[i + 1]).resolve()
        if a == "--origin":
            origin = [float(x) for x in sys.argv[i + 1].split(",")]
        if a == "--zaxis":
            zaxis = [float(x) for x in sys.argv[i + 1].split(",")]
        if a == "--out":
            out = Path(sys.argv[i + 1]).resolve()
    if trunk_dir is None or origin is None or zaxis is None:
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
    print(f"[raster-cs] {trunk_dir.name}; starting {CONTAINER}", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        t3d_path = drv.write_work_file(emit_map(actors), ext="t3d")
        pid = O._editor_pid(CONTAINER)
        render_base = None
        for _ in range(60):
            try:
                render_base = _find_render_base(CONTAINER, pid)
                break
            except RuntimeError:
                time.sleep(1.0)
        if render_base is None:
            raise RuntimeError("render.dll never appeared")
        print(f"[raster-cs] render.dll live base = {render_base:#x}", flush=True)
        rep = {
            "__PID__": str(pid),
            "__PRECALL__": hex(remap(PRECALL, render_base)),
            "__POSTCALL__": hex(remap(POSTCALL, render_base)),
            "__GMINY__": hex(remap(G_MINY, render_base)),
            "__GMAXY__": hex(remap(G_MAXY, render_base)),
            "__GRASTER__": hex(remap(G_RASTER, render_base)),
            "__OX__": repr(origin[0]), "__OY__": repr(origin[1]), "__OZ__": repr(origin[2]),
            "__ZX__": repr(zaxis[0]), "__ZY__": repr(zaxis[1]), "__ZZ__": repr(zaxis[2]),
        }
        script = GDB_TEMPLATE
        for k, v in rep.items():
            script = script.replace(k, v)
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/rcs.gdb"],
                       input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/rcs.gdb > /tmp/rcs.log 2>&1"], check=True)
        for _ in range(240):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/rcs.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[raster-cs] attached; running the golden EXEC batch ...", flush=True)
        saved = "/work/probe_rcs.dx"
        drv.begin_script()
        ensure_load(drv, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        drv.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        drv.exec("MAP REBUILD")
        drv.light_apply()
        drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
        try:
            drv.run_script(produces=saved, timeout=1800.0)
        except Exception as ex:
            print(f"[raster-cs] batch wait ended: {ex}", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        log_bytes = subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/rcs.log"],
                                   capture_output=True).stdout
        out.write_bytes(f"render.dll live base = {render_base:#x}\n\n".encode() + log_bytes)
        print(f"[raster-cs] wrote {out} ({len(log_bytes)} bytes)", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
