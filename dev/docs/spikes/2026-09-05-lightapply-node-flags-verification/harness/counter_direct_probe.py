#!/usr/bin/env python3
r"""Directly confirm the amortization counter (`render.dll`'s `*(int*)0x1005fa24`, read by
`URender::GetVisibleSurfs`'s box-occlusion test) at its REAL live address, per light, across
a full golden-build `LIGHT APPLY` run.

CORRECTION (2026-09-05, this worktree): `render.dll` is NOT always loaded at its preferred
base 0x10000000 -- in this worktree's sessions, `Editor.dll` wins that address (confirmed:
`illuminateSurf`/the walker hit correctly there) and `render.dll` gets relocated by Wine's
loader to a DIFFERENT base (observed: 0x015b0000). A literal read of file-address 0x1005fa24
in that case silently reads INSIDE EDITOR.DLL's own memory, not the counter -- explaining the
`counter_and_flags_probe.py` "0x100f100c, invariant, refuted" result. This probe reads
`/proc/<pid>/maps` live to find render.dll's REAL base and remaps every render.dll address
before setting breakpoints. Confirmed via the PE export table (`GetVisibleSurfs@URender`,
`DrawWorld@URender`) and byte-pattern checks (function prologues) -- not just offset guessing.

Breaks at:
  - `URender::GetVisibleSurfs` entry (once per light): logs the light index and the counter's
    value AT ENTRY.
  - `URender::DrawWorld`'s `inc dword ptr [counter]` (the only write site in the whole .text
    section, confirmed by full-module disassembly grep): logs which light was executing when it
    fired.

Usage: counter_direct_probe.py --trunk <subset-trunk-dir> [--out log] [--timeout SEC]
"""
from __future__ import annotations

import re
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

CONTAINER = "uned-counter-direct-probe"
RENDER_PREF = 0x10000000
# file-relative (preferred-base) addresses, per the disassembly + PE export table
GETVISIBLESURFS_ENTRY = 0x100187b0   # URender::GetVisibleSurfs prologue (`push ebp`)
DRAWWORLD_INC = 0x1001773b            # `inc dword ptr [counter]` inside URender::DrawWorld
COUNTER_ADDR = 0x1005fa24


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

set $lightnum = 0
break *__GVS__
commands
silent
set $lightnum = $lightnum + 1
printf "GETVISIBLESURFS_ENTRY light=%d counter=%d\n", $lightnum, *(int*)__COUNTER__
continue
end
break *__DW__
commands
silent
printf "DRAWWORLD_INC_HIT after_light=%d counter_before_inc=%d\n", $lightnum, *(int*)__COUNTER__
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
            addr = line.split("-", 1)[0]
            return int(addr, 16)
    raise RuntimeError("render.dll not found in /proc/pid/maps")


def main() -> int:
    trunk_dir = None
    out = HERE.parent / "logs" / "counter-direct-probe.log"
    timeout = 1200.0
    for i, a in enumerate(sys.argv):
        if a == "--trunk":
            trunk_dir = Path(sys.argv[i + 1]).resolve()
        if a == "--out":
            out = Path(sys.argv[i + 1]).resolve()
        if a == "--timeout":
            timeout = float(sys.argv[i + 1])
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
    print(f"[direct-probe] {trunk_dir.name}; starting {CONTAINER}", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        t3d_path = drv.write_work_file(emit_map(actors), ext="t3d")
        pid = O._editor_pid(CONTAINER)
        render_base = _find_render_base(CONTAINER, pid)
        print(f"[direct-probe] render.dll live base = {render_base:#x} "
              f"(preferred {RENDER_PREF:#x})", flush=True)
        gvs = remap(GETVISIBLESURFS_ENTRY, render_base)
        dw = remap(DRAWWORLD_INC, render_base)
        counter = remap(COUNTER_ADDR, render_base)
        script = (GDB_TEMPLATE.replace("__PID__", str(pid))
                  .replace("__GVS__", hex(gvs)).replace("__DW__", hex(dw))
                  .replace("__COUNTER__", hex(counter)))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/cdp.gdb"],
                       input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/cdp.gdb > /tmp/cdp.log 2>&1"], check=True)
        for _ in range(120):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/cdp.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[direct-probe] attached; running the golden EXEC batch ...", flush=True)
        saved = "/work/probe_direct.dx"
        drv.begin_script()
        ensure_load(drv, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        drv.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        drv.exec("MAP REBUILD")
        drv.light_apply()
        drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
        try:
            drv.run_script(produces=saved, timeout=timeout)
        except Exception as ex:
            print(f"[direct-probe] batch wait ended: {ex}", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        log_bytes = subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/cdp.log"],
                                   capture_output=True).stdout
        header = (f"render.dll live base = {render_base:#x}; GetVisibleSurfs @ {gvs:#x}; "
                  f"DrawWorld-inc @ {dw:#x}; counter @ {counter:#x}\n\n").encode()
        out.write_bytes(header + log_bytes)
        print(f"[direct-probe] wrote {out}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
