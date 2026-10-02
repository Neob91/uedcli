#!/usr/bin/env python3
r"""Live capture of `URender::GetVisibleSurfs`/`OccludeBsp` (render.dll) during NYC_Bar N=153's
`LIGHT APPLY`, to settle whether the "moving-brush filter" (`Level->BrushTracker->SurfIsDynamic`,
`render.dll 0x10019349`) is what makes UED22 exclude the world tread surfaces (95/97/67) from
`Light5`'s visible-surface list (`nyc-bar-n-153-world-model2-lightmap-runs-ued22`).

Register mapping confirmed by live disassembly this session (`disasm_probe.py` output,
`../logs/disasm.log`):
  - `%edi` = current `FBspNode*` throughout the per-node loop (node stride 0x40, `iSurf` at +0x1c).
  - `-0x8b4(%ebp)` = the `FSceneNode* Frame` local, valid for the whole `OccludeBsp` body (its own
    `+0x4` is `Frame->Level`, whose `+0xfc` is `ULevel::BrushTracker` -- matches the port-urender
    doc's "`ULevel+0xfc`").  `Frame->Coords.Origin` (the light's Location) is at `Frame+0x34/+0x38/+0x3c`
    (reused from `box_verdict_probe.py`, already validated there).
  - The moving-brush filter block, in order:
      0x015c9336  mov Frame->Level -> eax
      0x015c933f  mov Level->BrushTracker -> ecx      (breakpoint MB_TRACKER: log ecx null-ness)
      0x015c9349  mov (%ecx),%eax; push node->iSurf; call *0xc(%eax)   -- SurfIsDynamic(iSurf)
      0x015c9353  test %eax,%eax                      (breakpoint MB_RESULT: log iSurf + %eax)
  - Node visitation entry (after `%edi` = node pointer, before ANY filter runs):
      0x015c930b  (breakpoint NODE_ENTER: log iSurf + Frame origin XYZ)
  - `TArray<INT>::AddUniqueItem` callee entry (`render.dll 0x100120b0`): first stack arg (at
    entry, before `push %ebp`, this is `[esp+4]`) is a pointer to the INT being added -- this is
    `iSurfs.AddUniqueItem(D->iSurf)` from `GetVisibleSurfs`'s per-face Draw-list walk, called right
    after each face's `OccludeBsp` (breakpoint ADD_ENTRY: log the surf value).

Usage: mover_occlusion_probe.py --trunk <subset-trunk-dir> [--out log]
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

CONTAINER = "uned-n153-mover-occ"
RENDER_PREF = 0x10000000

NODE_ENTER = 0x1001930B
MB_TRACKER = 0x10019345   # right after `mov Level->BrushTracker -> ecx; test ecx,ecx`
MB_RESULT = 0x10019353    # right after `call SurfIsDynamic; test eax,eax`
ADD_ENTRY = 0x100120B0


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
set $seq = 0

break *__NODE_ENTER__
commands
silent
set $seq = $seq + 1
set $fr = *(unsigned int*)($ebp-0x8b4)
printf "NODE seq=%d isurf=%d origin=[%.9g,%.9g,%.9g]\n", $seq, *(int*)($edi+0x1c), *(float*)($fr+0x34), *(float*)($fr+0x38), *(float*)($fr+0x3c)
continue
end

break *__MB_TRACKER__
commands
silent
set $seq = $seq + 1
printf "MBTRACK seq=%d isurf=%d tracker=%#x\n", $seq, *(int*)($edi+0x1c), $ecx
continue
end

break *__MB_RESULT__
commands
silent
set $seq = $seq + 1
printf "MBRESULT seq=%d isurf=%d dynamic=%d\n", $seq, *(int*)($edi+0x1c), $eax
continue
end

break *__ADD_ENTRY__
commands
silent
set $seq = $seq + 1
set $argp = *(unsigned int*)($esp+4)
printf "ADD seq=%d isurf=%d\n", $seq, *(int*)($argp)
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
    out = HERE.parent / "logs" / "mover-occlusion.log"
    for i, a in enumerate(sys.argv):
        if a == "--trunk":
            trunk_dir = Path(sys.argv[i + 1]).resolve()
        if a == "--out":
            out = Path(sys.argv[i + 1]).resolve()
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
    print(f"[mover-occ] {trunk_dir.name}; starting {CONTAINER}", flush=True)
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
        print(f"[mover-occ] render.dll live base = {render_base:#x}", flush=True)
        script = (GDB_TEMPLATE
                  .replace("__PID__", str(pid))
                  .replace("__NODE_ENTER__", hex(remap(NODE_ENTER, render_base)))
                  .replace("__MB_TRACKER__", hex(remap(MB_TRACKER, render_base)))
                  .replace("__MB_RESULT__", hex(remap(MB_RESULT, render_base)))
                  .replace("__ADD_ENTRY__", hex(remap(ADD_ENTRY, render_base))))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/mo.gdb"],
                       input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/mo.gdb > /tmp/mo.log 2>&1"], check=True)
        for _ in range(240):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/mo.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[mover-occ] attached; running the golden EXEC batch ...", flush=True)
        saved = "/work/probe_mo.dx"
        drv.begin_script()
        ensure_load(drv, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        drv.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        drv.exec("MAP REBUILD")
        drv.light_apply()
        drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
        try:
            drv.run_script(produces=saved, timeout=900.0)
        except Exception as ex:
            print(f"[mover-occ] batch wait ended: {ex}", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        log_bytes = subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/mo.log"],
                                   capture_output=True).stdout
        out.write_bytes(f"render.dll live base = {render_base:#x}\n\n".encode() + log_bytes)
        print(f"[mover-occ] wrote {out} ({len(log_bytes)} bytes)", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
