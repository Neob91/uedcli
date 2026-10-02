#!/usr/bin/env python3
r"""Capture `URender::BoundVisible`'s real inputs and outputs, live, at its call site.

Breaks at `render.dll 0x100193d5` (the `call eax` in `URender::OccludeBsp`'s box-occlusion step,
`eax = [Frame_vtable + 0x80]`) and at `0x100193d7` (right after it). Per hit it dumps:

  - every `FSceneNode` field `BoundVisible` reads: `Coords` (0x34 Origin / 0x40 XAxis / 0x4c YAxis /
    0x58 ZAxis), `X`/`Y` (0xa8/0xac), `FX`/`FY` (0xb8/0xbc), `FX15`/`FY15` (0xc8/0xcc), `Proj`
    (0xd4/0xd8/0xdc) and the four clip slopes (0xec/0xf0/0xf4/0xf8),
  - the `FBox` argument, the `FSpanBuffer*` argument (NULL whenever `bUseZones`),
  - the return value, the five `FScreenBounds` floats the callee wrote, and WHICH exit path it took
    (each exit bumps its own stat counter, so a breakpoint on that `inc` tags the path): `inside` =
    the view origin is in the box, `depth` = every corner behind the camera, `outcode` = every
    corner outside one frustum plane, `span` = `FSpanBuffer::BoxIsVisible` said no.

That pins the frame constants the native port hard-codes (1024x1024, FOV 90) instead of guessing
them, and gives a real input/output fixture set to cross-check the Rust port against.

Usage: boundvisible_frame_probe.py --trunk <subset-trunk-dir> [--out log] [--hits N]

Derived from `2026-09-05-lightapply-node-flags-verification/harness/boundvisible_target_probe.py`
(same relocation handling: `render.dll` does NOT load at its preferred base under Wine -- Editor.dll
wins 0x10000000 -- so every address is remapped through /proc/<pid>/maps).
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

CONTAINER = "uned-boundvisible-frame-probe"
RENDER_PREF = 0x10000000
CALL_SITE = 0x100193D5   # `call eax`
AFTER_CALL = 0x100193D7  # `test eax, eax`
# `BoundVisible`'s four exits, each identified by the stat counter it bumps.
EXITS = {"inside": 0x10012315, "depth": 0x10012439, "outcode": 0x1001375F, "span": 0x100139E8}


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
set $sb = 0
break *__CALL__
commands
silent
set $hits = $hits + 1
set $fr = *(unsigned int*)($esp)
set $box = *(unsigned int*)($esp+4)
set $span = *(unsigned int*)($esp+8)
set $sb = *(unsigned int*)($esp+12)
printf "IN hit=%d frame=%#x span=%#x node_esi=%d\n", $hits, $fr, $span, $esi
printf "IN box=[%.9g,%.9g,%.9g]-[%.9g,%.9g,%.9g] valid=%d\n", *(float*)$box, *(float*)($box+4), *(float*)($box+8), *(float*)($box+12), *(float*)($box+16), *(float*)($box+20), *(int*)($box+24)
printf "FRAME origin=[%.9g,%.9g,%.9g] xaxis=[%.9g,%.9g,%.9g] yaxis=[%.9g,%.9g,%.9g] zaxis=[%.9g,%.9g,%.9g]\n", *(float*)($fr+0x34), *(float*)($fr+0x38), *(float*)($fr+0x3c), *(float*)($fr+0x40), *(float*)($fr+0x44), *(float*)($fr+0x48), *(float*)($fr+0x4c), *(float*)($fr+0x50), *(float*)($fr+0x54), *(float*)($fr+0x58), *(float*)($fr+0x5c), *(float*)($fr+0x60)
printf "FRAME X=%d Y=%d XB=%d YB=%d FX=%.9g FY=%.9g F_c0=%.9g F_c4=%.9g FX15=%.9g FY15=%.9g F_d0=%.9g proj=[%.9g,%.9g,%.9g] rproj=%.9g clip=[%.9g,%.9g,%.9g,%.9g] zone=%d\n", *(int*)($fr+0xa8), *(int*)($fr+0xac), *(int*)($fr+0xb0), *(int*)($fr+0xb4), *(float*)($fr+0xb8), *(float*)($fr+0xbc), *(float*)($fr+0xc0), *(float*)($fr+0xc4), *(float*)($fr+0xc8), *(float*)($fr+0xcc), *(float*)($fr+0xd0), *(float*)($fr+0xd4), *(float*)($fr+0xd8), *(float*)($fr+0xdc), *(float*)($fr+0xe0), *(float*)($fr+0xec), *(float*)($fr+0xf0), *(float*)($fr+0xf4), *(float*)($fr+0xf8), *(unsigned char*)($fr+0x18)
continue
end

__EXITBPS__
break *__AFTER__
commands
silent
printf "OUT hit=%d ret=%d sb=[%.9g,%.9g,%.9g,%.9g,%.9g]\n", $hits, $eax, *(float*)$sb, *(float*)($sb+4), *(float*)($sb+8), *(float*)($sb+12), *(float*)($sb+16)
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
    hits = 400
    out = HERE.parent / "logs" / "boundvisible-frame-probe.log"
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
    print(f"[bv-frame] {trunk_dir.name}; starting {CONTAINER}", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        t3d_path = drv.write_work_file(emit_map(actors), ext="t3d")
        pid = O._editor_pid(CONTAINER)
        render_base = _find_render_base(CONTAINER, pid)
        print(f"[bv-frame] render.dll live base = {render_base:#x}", flush=True)
        script = (GDB_TEMPLATE
                  .replace("__PID__", str(pid))
                  .replace("__CALL__", hex(remap(CALL_SITE, render_base)))
                  .replace("__AFTER__", hex(remap(AFTER_CALL, render_base)))
                  .replace("__EXITBPS__", "\n".join(
                      f'break *{remap(a, render_base):#x}\ncommands\nsilent\n'
                      f'printf "EXIT hit=%d path={tag}\\n", $hits\ncontinue\nend'
                      for tag, a in EXITS.items()))
                  .replace("__HITS__", str(hits)))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/bvf.gdb"],
                       input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/bvf.gdb > /tmp/bvf.log 2>&1"], check=True)
        for _ in range(240):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/bvf.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[bv-frame] attached; running the golden EXEC batch ...", flush=True)
        saved = "/work/probe_bvf.dx"
        drv.begin_script()
        ensure_load(drv, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        drv.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        drv.exec("MAP REBUILD")
        drv.light_apply()
        drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
        try:
            drv.run_script(produces=saved, timeout=900.0)
        except Exception as ex:
            print(f"[bv-frame] batch wait ended: {ex}", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        log_bytes = subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/bvf.log"],
                                   capture_output=True).stdout
        out.write_bytes(f"render.dll live base = {render_base:#x}\n\n".encode() + log_bytes)
        print(f"[bv-frame] wrote {out}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
