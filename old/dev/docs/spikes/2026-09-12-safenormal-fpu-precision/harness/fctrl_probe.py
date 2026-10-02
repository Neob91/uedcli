#!/usr/bin/env python3
r"""Read the LIVE x87 FPU control word (Precision Control bits) at `FVector::SafeNormal`
(`core.dll 0x10051090`), the function `permeating_lights::safe_normal` models as an f64
sqrt+reciprocal (see `uedcli-native/src/fpoly.rs`).

Context (`unatco-n-226-leaf-12-gets-a-permeating-light157` /
`island-n-332-leaf-273-permeating-light-vertex-tie`): native's `FLinePlaneIntersection` port is
disassembly-verified bit-exact (`Engine.dll 0x101507c0`), and the plane-normal cross product in
`FPlane::FPlane(A,B,C)` (`core.dll 0x1000b440`) is bit-exact too (both re-verified fresh this
session). The one place left where native's model could genuinely diverge from the real compiled
code is `SafeNormal`'s sqrt+reciprocal chain, which disassembles to REAL x87 instructions (`call
sqrt; fstp dword; fld dword; fld1; fdivrp; fstp dword`) -- not SSE. A whole-`.text` census of
Engine.dll, Editor.dll, core.dll, AND D3D9Drv.dll finds ZERO `fldcw`/`fnstcw` anywhere, meaning
nothing in any of the four DLLs ever explicitly sets the FPU precision-control (PC) field. That
means the PC field is whatever the process/thread inherited at creation -- under Wine on Linux,
almost certainly PC=11 (64-bit EXTENDED mantissa, the x87 hardware-reset default), NOT PC=10
(53-bit, "double", what a naive `f64` port implicitly assumes when it computes sqrt/divide in Rust
`f64` and casts once to `f32`). This probe reads `$fctrl` directly at a live `SafeNormal` call to
settle it, with no need to single-step the whole crossing -- the PC field can't change mid-run
(nothing ever writes it), so ANY hit during a real MAP REBUILD is representative.

Breaks:
  ENTRY = core.dll 0x10051090  (`this`=$ecx: input vector x,y,z at +0,+4,+8)
  EXIT  = core.dll 0x1005112f  (`pop esi`, not yet executed: $esi=out ptr, all 3 output floats
          already stored at [esi],[esi+4],[esi+8]; $edi still holds `this` too)

Usage: fctrl_probe.py --trunk <subset-trunk-dir> [--out log] [--hits N]
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

CONTAINER = "uned-fctrl-probe"
CORE_PREF = 0x10000000
ENTRY = 0x10051090
EXIT = 0x1005112F

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

break *__ENTRY__
commands
silent
set $hits = $hits + 1
if $hits <= __MAXHITS__
printf "SN_IN  hit=%d fctrl=%#x this=[%.9g,%.9g,%.9g]\n", $hits, $fctrl, *(float*)($ecx), *(float*)($ecx+4), *(float*)($ecx+8)
end
if $hits > __MAXHITS__
delete 1
delete 2
end
continue
end

break *__EXIT__
commands
silent
if $hits <= __MAXHITS__
printf "SN_OUT hit=%d fctrl=%#x out=[%.9g,%.9g,%.9g]\n", $hits, $fctrl, *(float*)($esi), *(float*)($esi+4), *(float*)($esi+8)
end
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def remap(addr: int, live_base: int) -> int:
    return live_base + (addr - CORE_PREF)


def _find_dll_base(container: str, pid: int, dll: str) -> int:
    maps = subprocess.run(["docker", "exec", container, "cat", f"/proc/{pid}/maps"],
                          capture_output=True, text=True, check=True).stdout
    for line in maps.splitlines():
        if dll.lower() in line.lower():
            return int(line.split("-", 1)[0], 16)
    raise RuntimeError(f"{dll} not found")


def main() -> int:
    trunk_dir = None
    max_hits = 20
    out = HERE.parent / "logs" / "fctrl-probe.log"
    for i, a in enumerate(sys.argv):
        if a == "--trunk":
            trunk_dir = Path(sys.argv[i + 1]).resolve()
        if a == "--out":
            out = Path(sys.argv[i + 1]).resolve()
        if a == "--hits":
            max_hits = int(sys.argv[i + 1])
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
    print(f"[fctrl] {trunk_dir.name}; starting {CONTAINER}", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        t3d_path = drv.write_work_file(emit_map(actors), ext="t3d")
        pid = O._editor_pid(CONTAINER)
        core_base = _find_dll_base(CONTAINER, pid, "core.dll")
        print(f"[fctrl] core.dll live base = {core_base:#x}", flush=True)
        script = (GDB_TEMPLATE
                  .replace("__PID__", str(pid))
                  .replace("__ENTRY__", hex(remap(ENTRY, core_base)))
                  .replace("__EXIT__", hex(remap(EXIT, core_base)))
                  .replace("__MAXHITS__", str(max_hits)))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/fctrl.gdb"],
                       input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/fctrl.gdb > /tmp/fctrl.log 2>&1"], check=True)
        for _ in range(240):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/fctrl.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[fctrl] attached; running the golden EXEC batch ...", flush=True)
        saved = "/work/probe_fctrl.dx"
        drv.begin_script()
        ensure_load(drv, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        drv.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        drv.exec("MAP REBUILD")
        drv.light_apply()
        drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
        try:
            drv.run_script(produces=saved, timeout=900.0)
        except Exception as ex:
            print(f"[fctrl] batch wait ended: {ex}", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        log_bytes = subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/fctrl.log"],
                                   capture_output=True).stdout
        out.write_bytes(f"core.dll live base = {core_base:#x}\n\n".encode() + log_bytes)
        print(f"[fctrl] wrote {out}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
