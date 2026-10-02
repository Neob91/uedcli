#!/usr/bin/env python3
r"""Round 8 (2026-09-15): DIRECT read of the light origin (and target-array identity) at every
`TArray<INT>::AddUniqueItem` call reached from `URender::GetVisibleSurfs`'s per-face draw-list walk,
settling round 7's leftover question for `nyc-bar-n-153-world-model2-lightmap-runs-ued22` -- whether
the `ADD seq=8245..8248 isurf=67/95/97` entries round 7 found near Light5's own `NODE` sequence window
(in the EXISTING `../2026-09-13-nycbar-n153-mover-occlusion/logs/mover-occlusion.log`) really belong to
Light5's own gather, by reading the call's own arguments instead of trusting sequence-number proximity.

**Static disassembly this round (`disasm_wide_probe.py`, `../logs/disasm-wide.log`) fully identifies
the caller and its frame**, closing the exact gap round 7 flagged ("the callee-entry breakpoint... fires
before the callee's own `push %ebp`, so it inherits the CALLER's frame, not OccludeBsp's... needs first
identifying which caller-frame slot holds it"):

  - The caller is `URender::GetVisibleSurfs` ITSELF (RVA 0x100187b0), not OccludeBsp. Live disasm of
    its body (0x100187b0-0x100189b0) shows a DIRECT `call 0x100120b0` at RVA 0x100189da, inside a
    per-face post-`OccludeBsp` walk: for i in 0..2, `list_head = *(draw_result+0x98+i*4)`; while
    `list_head` (a singly-linked node, `next` at `+0x38`): `AddUniqueItem(iSurfs, &list_head->field4)`.
    `draw_result` is the return value of the FIRST per-face vtable call (`call *0x64(%eax)`, right
    before `OccludeBsp` itself is called) -- i.e. the accepted/committed node list `OccludeBsp` (or its
    caller) hands back per face, bucketed into (at least) 3 sub-lists.
  - `GetVisibleSurfs`'s OWN prologue (`0x100187de: mov %ecx,%edi; ...; 0x1001883... : mov 0xc(%ebp),
    %ebx`, live `0x015c87ef`) shows **`0x8(%ebp)` = arg1 = the `FSceneNode* Frame` (the SAME struct/
    offsets `box_verdict_n153.py`/`raster_order_probe.py`/`mover_occlusion_probe.py` already read
    Origin from, `+0x34/+0x38/+0x3c`), and `0xc(%ebp)` = arg2 = `%ebx`, held in that register for the
    WHOLE function body -- the output `TArray<INT>* iSurfs` GetVisibleSurfs exists to fill.** Both are
    stable across the entire per-face loop, so they are readable at the CALL SITE `0x100189da` (still
    inside `GetVisibleSurfs`'s own frame, before `AddUniqueItem`'s `push %ebp` executes).
  - Consequence: `AddUniqueItem`'s callee-entry breakpoint (`0x100120b0`, `mover_occlusion_probe.py`'s
    existing `ADD_ENTRY`) sits at `push %ebp` itself -- `$ebp` there IS STILL `GetVisibleSurfs`'s own
    frame (unchanged since `GetVisibleSurfs` never moves `%ebp` around the call). So `$ebp+0x8`/
    `$ebp+0xc` are valid THERE too, with no new call-site breakpoint needed: this probe reuses
    `ADD_ENTRY` exactly as `mover_occlusion_probe.py` already breaks it, and additionally reads the
    Frame origin off `$ebp+0x8` and the `iSurfs` array identity off `$ebp+0xc` (`%ebx`'s stack home).

This settles, by direct read (not inference): (1) which light's `Frame` a given `AddUniqueItem` hit
belongs to (its `Origin`, comparable against Light5's exact `Location`), and (2) that the target array
really is `iSurfs` -- `GetVisibleSurfs`'s own 2nd argument, the function's whole reason for existing --
not some unrelated rendering list, closing round 6's original "shared template, could be anything"
dismissal for good.

Usage: adduniqueitem_origin_probe.py --trunk <subset-trunk-dir> [--out log]
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

CONTAINER = "uned-n153-adduniqueitem-origin"
RENDER_PREF = 0x10000000
ADD_ENTRY = 0x100120B0  # TArray<INT>::AddUniqueItem entry, BEFORE its own `push %ebp` -- caller frame


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

break *__ADD_ENTRY__
commands
silent
set $hits = $hits + 1
set $argp = *(unsigned int*)($esp+4)
set $isurf = *(int*)($argp)
set $frame = *(unsigned int*)($ebp+0x8)
set $coords = *(unsigned int*)($frame+0x30)
set $isurfs_arr = *(unsigned int*)($ebp+0xc)
printf "ADD hit=%d isurf=%d iSurfsArr=%#x frame=%#x coords=%#x origin_d0=%.9g,%.9g,%.9g origin_34=%.9g,%.9g,%.9g\n", $hits, $isurf, $isurfs_arr, $frame, $coords, *(float*)($coords+0xd0), *(float*)($coords+0xd4), *(float*)($coords+0xd8), *(float*)($frame+0x34), *(float*)($frame+0x38), *(float*)($frame+0x3c)
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
    out = HERE.parent / "logs" / "adduniqueitem-origin-n153.log"
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
    print(f"[add-origin] {trunk_dir.name}; starting {CONTAINER}", flush=True)
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
        print(f"[add-origin] render.dll live base = {render_base:#x}", flush=True)
        script = GDB_TEMPLATE.replace("__PID__", str(pid)).replace(
            "__ADD_ENTRY__", hex(remap(ADD_ENTRY, render_base)))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/addorigin.gdb"],
                       input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/addorigin.gdb > /tmp/addorigin.log 2>&1"], check=True)
        for _ in range(240):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/addorigin.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[add-origin] attached; running the golden EXEC batch ...", flush=True)
        saved = "/work/probe_addorigin.dx"
        drv.begin_script()
        ensure_load(drv, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        drv.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        drv.exec("MAP REBUILD")
        drv.light_apply()
        drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
        try:
            drv.run_script(produces=saved, timeout=1800.0)
        except Exception as ex:
            print(f"[add-origin] batch wait ended: {ex}", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        log_bytes = subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/addorigin.log"],
                                   capture_output=True).stdout
        out.write_bytes(f"render.dll live base = {render_base:#x}\n\n".encode() + log_bytes)
        print(f"[add-origin] wrote {out} ({len(log_bytes)} bytes)", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
