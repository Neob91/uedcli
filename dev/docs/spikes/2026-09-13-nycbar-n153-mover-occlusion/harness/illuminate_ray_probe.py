#!/usr/bin/env python3
r"""Live capture of `illuminateSurf`'s per-lumel shadow ray (`Editor.dll`, `LineCheck` call site
`0x100a5a04`, per `2026-08-29-unatco-repart-live-diff/harness/linecheck_singlestep_rec14_v2.py`)
for NYC_Bar N=153's three world tread surfaces (95/97/67) that UED22 leaves dark for `Light5` while
native computes real lit bits (`nyc-bar-n-153-world-model2-lightmap-runs-ued22`).

Prior capture this session (`mover_occlusion_probe.py`) proved `Level->BrushTracker` is non-NULL
during `LIGHT APPLY` and that `URender::GetVisibleSurfs` DOES add surf 95/97/67 to `Light5`'s
visible set (all three surfs' `AddUniqueItem` calls fire during Light5's own 6-face gather pass) --
so the divergence is NOT a gather-stage exclusion. This probe checks the next stage: does UED22's
own per-lumel `UModel::LineCheck` (the shadow ray) come back CLEAR or BLOCKED for these surfaces'
lumels against Light5. `[ebp+0xc]` is `illuminateSurf`'s own `iSurf` stack arg and stays valid at
the `LineCheck` call site (no intervening call boundary changes `$ebp`), so both breakpoints read it
directly with no dynamic arming needed.

  0x100a5a04  `call [eax+0x58]`   -- the LineCheck call.  esp+0x14/0x18/0x1c = Start (lumel P).
  0x100a5a07  right after         -- $eax = return (UE LineCheck: nonzero = HIT/blocked, 0 = clear).

Usage: illuminate_ray_probe.py --trunk <subset-trunk-dir> [--out log] [--timeout SECS]
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

CONTAINER = "uned-n153-illumray"
EDITOR_PREF = 0x10000000
ENTRY_ISURF_CHECK = 0x100A5043
CALL_SITE = 0x100A5A04
AFTER_CALL = 0x100A5A07
TARGET_SURFS = (95, 97, 67)


def remap(addr: int, live_base: int) -> int:
    return live_base + (addr - EDITOR_PREF)


def _find_editor_base(container: str, pid: int) -> int:
    maps = subprocess.run(["docker", "exec", container, "cat", f"/proc/{pid}/maps"],
                          capture_output=True, text=True, check=True).stdout
    for line in maps.splitlines():
        if "editor.dll" in line.lower():
            return int(line.split("-", 1)[0], 16)
    raise RuntimeError("Editor.dll not found")


COND = " || ".join(f"*(int*)($ebp+0xc)=={s}" for s in TARGET_SURFS)

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
set $seen = 0

break *__ENTRY__ if __COND__
commands
silent
set $seen = $seen + 1
printf "SURF_ENTER hit=%d isurf=%d\n", $seen, *(int*)($ebp+0xc)
continue
end

break *__CALL__ if __COND__
commands
silent
printf "RAY_START isurf=%d p=[%.9g,%.9g,%.9g]\n", *(int*)($ebp+0xc), *(float*)($esp+0x14), *(float*)($esp+0x18), *(float*)($esp+0x1c)
continue
end

break *__AFTER__ if __COND__
commands
silent
printf "RAY_RESULT isurf=%d ret=%d\n", *(int*)($ebp+0xc), $eax
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def main() -> int:
    trunk_dir = None
    out = HERE.parent / "logs" / "illuminate-ray.log"
    timeout = 900.0
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
    print(f"[illumray] {trunk_dir.name}; starting {CONTAINER}", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        t3d_path = drv.write_work_file(emit_map(actors), ext="t3d")
        pid = O._editor_pid(CONTAINER)
        editor_base = _find_editor_base(CONTAINER, pid)
        print(f"[illumray] Editor.dll live base = {editor_base:#x}", flush=True)
        script = (GDB_TEMPLATE
                  .replace("__PID__", str(pid))
                  .replace("__ENTRY__", hex(remap(ENTRY_ISURF_CHECK, editor_base)))
                  .replace("__CALL__", hex(remap(CALL_SITE, editor_base)))
                  .replace("__AFTER__", hex(remap(AFTER_CALL, editor_base)))
                  .replace("__COND__", COND))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/ir.gdb"],
                       input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/ir.gdb > /tmp/ir.log 2>&1"], check=True)
        for _ in range(240):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/ir.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[illumray] attached; running the golden EXEC batch ...", flush=True)
        saved = "/work/probe_ir.dx"
        drv.begin_script()
        ensure_load(drv, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        drv.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        drv.exec("MAP REBUILD")
        drv.light_apply()
        drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
        try:
            drv.run_script(produces=saved, timeout=timeout)
        except Exception as ex:
            print(f"[illumray] batch wait ended: {ex}", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        log_bytes = subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/ir.log"],
                                   capture_output=True).stdout
        out.write_bytes(f"Editor.dll live base = {editor_base:#x}\n\n".encode() + log_bytes)
        print(f"[illumray] wrote {out} ({len(log_bytes)} bytes)", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
