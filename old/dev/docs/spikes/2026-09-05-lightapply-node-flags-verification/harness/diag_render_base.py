#!/usr/bin/env python3
"""Diagnostic: is render.dll really loaded at 0x10000000 (unrelocated) in the live golden
pipeline process, and does the code at 0x10019365 match the static disassembly?
Dumps /proc/<pid>/maps for render.dll and the raw bytes at a few candidate addresses.

Usage: diag_render_base.py --trunk <subset-trunk-dir> [--out log]
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

CONTAINER = "uned-diag-render-base"

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
printf "MAPS_BEGIN\n"
shell cat /proc/__PID__/maps
printf "MAPS_END\n"
printf "BYTES_AT_GETVISIBLESURFS_ENTRY (0x100187b0 remapped): "
x/12xb 0x015c87b0
printf "DWORD_AT_REMAPPED_COUNTER: "
x/1xw 0x0160fa24
set $lightnum = 0
break *0x015c87b0
commands
silent
set $lightnum = $lightnum + 1
printf "GETVISIBLESURFS_ENTRY light=%d counter_before=%d\n", $lightnum, *(int*)0x0160fa24
continue
end
break *0x100a5043
commands
silent
printf "ILLUMINATESURF_HIT light=%d esurf=%d counter=%d\n", $lightnum, *(int*)($ebp+0xc), *(int*)0x0160fa24
continue
end
break *0x15c773b
commands
silent
printf "DRAWWORLD_INC_HIT light=%d counter_before_inc=%d\n", $lightnum, *(int*)0x0160fa24
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def main() -> int:
    trunk_dir = None
    out = HERE.parent / "logs" / "diag-render-base.log"
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
    print(f"[diag] {trunk_dir.name}; starting {CONTAINER}", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        t3d_path = drv.write_work_file(emit_map(actors), ext="t3d")
        pid = O._editor_pid(CONTAINER)
        script = GDB.replace("__PID__", str(pid))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/dg.gdb"],
                       input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/dg.gdb > /tmp/dg.log 2>&1"], check=True)
        for _ in range(120):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/dg.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[diag] attached; running the golden EXEC batch ...", flush=True)
        saved = "/work/probe_diag.dx"
        drv.begin_script()
        ensure_load(drv, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        drv.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        drv.exec("MAP REBUILD")
        drv.light_apply()
        drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
        try:
            drv.run_script(produces=saved, timeout=300.0)
        except Exception as ex:
            print(f"[diag] batch wait ended: {ex}", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/dg.log"],
                                       capture_output=True).stdout)
        print(f"[diag] wrote {out}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
