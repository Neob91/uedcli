#!/usr/bin/env python3
r"""Live-capture UED22's `bspAddPoint`/`FindNearestVertex` HIT-vs-MISS verdict at the exact query
that produces OceanLab N=203's divergent world `Model2.points` pair.

Continues `dev/docs/board/to-spike/oceanlab-n-203-world-model2-split-vertex-ulp/` and
`dev/docs/spikes/2026-09-13-oceanlab-n203-pbase-provenance/`. Those sessions pinned the divergence to
one call: `bsp_add_point_tol(model, Brush483 poly 2's transformed Origin)` inside `bsp_brush_csg`
(`bspcsg.rs`), query bits `(0xc3800004, 0x44160004, 0xc4e10000)` == `(-256.0001220703125,
600.000244140625, -1800.0)`. Native's faithful FNV descent MISSES an existing pool point only
`6.1e-5` away (well inside the `0.002` add threshold). Unresolved question: does UED22's own
`bspAddPoint`/`FindNearestVertex` at the SAME query also MISS (native is faithfully reproducing an
earlier divergence) or does it HIT (native's descent genuinely differs)?

Method: same recipe as `2026-09-13-crossing-vertex-live-capture/harness/crossing_probe.py` (gdb
`ptrace` attach inside the `dx-lum-uned-dbg` container, DLL bases read live and remapped) and
`2026-09-05-faithful-dedup-fix-attempt/stage2b/probe_editor_fnv.py` (the ORIGINAL N=8 probe this one
extends to gdb — that one used winedbg, this environment uses gdb; same breakpoint semantics).

Breakpoint: Editor.dll (preferred base `0x10000000`) `0x100354a1` -- inside `bspAddPoint`, right
after its call to `FindNearestVertex`. At that address (`stage2b`'s own stack-offset RE, confirmed
this session): `[ebp+0x0c]` = query `FVector*`, `[ebp+0x10]` = threshold (float), `[ebp+8]` = FNV
return distance (float, `-1.0` == MISS), `[ebp-0x14]` = returned vertex index (int, meaningless on a
miss). Conditioned on the query's raw x bits == `0xc3800004` (native's divergent value) -- narrow
enough to isolate this exact add without wedging the whole MAP REBUILD (bspAddPoint fires thousands
of times per rebuild; this x value is unique to Brush483's poly-2 Origin transform).

Usage: capture_addpoint.py [--out logs/capture.log]
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
NATIVE_MAT_HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
ORACLE_DIR = NATIVE_MAT_HARNESS / "editor-tree-oracle"
ACTOR_PARITY_HARNESS = ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness"
UNBUILT_HARNESS = ROOT / "dev/docs/spikes/2026-09-02-unbuilt-structure-parity/harness"
HERE = Path(__file__).resolve().parent
for p in (ROOT, NATIVE_MAT_HARNESS, ORACLE_DIR, ACTOR_PARITY_HARNESS, UNBUILT_HARNESS):
    sys.path.insert(0, str(p))

import editor_tree_oracle as O  # noqa: E402
import actor_parity as ap  # noqa: E402
from uedcli import config, trunk  # noqa: E402
from uedcli.apply import _level_referenced_packages  # noqa: E402
from uedcli.classindex import ClassIndex  # noqa: E402
from uedcli.container_assets import resource_mounts  # noqa: E402
from uedcli.driver import Driver, to_z_path  # noqa: E402
from uedcli.emit import emit_map  # noqa: E402
from uedcli.materialize import levelinfo_first_order  # noqa: E402
from uedcli.movers import set_base_pose  # noqa: E402
from uedcli.packages import editor_search_dirs, ensure_load  # noqa: E402
from build_ued_import_built_golden import _dummy_builder_actor  # noqa: E402
from build_ued_import_golden import _quote_str_props  # noqa: E402
from build_ued_golden import _scratch_project  # noqa: E402

CONTAINER = "uned-oceanlab-n203-addpoint"
EDITOR_PREF = 0x10000000

# bspAddPoint, right after `call FindNearestVertex` (Editor.dll preferred-base offset, RE'd
# `2026-09-05-faithful-dedup-fix-attempt/stage2b/probe_editor_fnv.py`, reused verbatim by the board
# item's own brief).
ADDPOINT_VA = 0x100354A1

# Native's divergent point (f32 bit patterns), `Brush483` poly 2's transformed `Origin`:
# (-256.0001220703125, 600.000244140625, -1800.0). The SECOND divergent point
# (-256.0001220703125, 504.000244140625, -1704.0, poly 5's Origin) shares the same x -- both hit the
# x-only condition below, distinguished afterward by y/z in the parsed log.
QUERY_X_BITS = 0xC3800004

DX_PATH = Path("/workspace/uedcli/dev/games/substrate-deusex/Maps/14_OceanLab_Lab.dx")
N = 203


def remap(addr: int, live_base: int, pref: int) -> int:
    return live_base + (addr - pref)


def _find_dll_base(container: str, pid: int, dll: str) -> int:
    maps = subprocess.run(["docker", "exec", container, "cat", f"/proc/{pid}/maps"],
                          capture_output=True, text=True, check=True).stdout
    for line in maps.splitlines():
        if dll.lower() in line.lower():
            return int(line.split("-", 1)[0], 16)
    raise RuntimeError(f"{dll} not found")


GDB_SCRIPT = f"""
set pagination off
set confirm off
set height 0
set width 0
attach {{pid}}
handle SIGSEGV nostop noprint pass
handle SIGUSR1 nostop noprint pass
handle SIGUSR2 nostop noprint pass
handle SIGPIPE nostop noprint pass
set $hits = 0

break *{{va:#x}}
commands
silent
set $hits = $hits + 1
set $q = *(unsigned int*)($ebp+0xc)
set $xbits = *(unsigned int*)($q+0)
if $xbits == {QUERY_X_BITS:#x}
printf "ADDPOINT hit=%d q=(%08x,%08x,%08x) [%.9g,%.9g,%.9g] thr=%.9g dist=%.9g vidx=%d\\n", \
  $hits, $xbits, *(unsigned int*)($q+4), *(unsigned int*)($q+8), \
  *(float*)($q+0), *(float*)($q+4), *(float*)($q+8), \
  *(float*)($ebp+0x10), *(float*)($ebp+8), *(int*)($ebp-0x14)
end
continue
end

printf "ORACLE_ATTACHED\\n"
continue
"""


def main() -> int:
    out = HERE.parent / "logs" / "capture.log"
    for i, a in enumerate(sys.argv):
        if a == "--out":
            out = Path(sys.argv[i + 1]).resolve()

    full_trunk, name = ap._resolve_trunk(DX_PATH, "deusex")
    subset = ap.make_subset(full_trunk, name, N)
    project = _scratch_project(subset, "deusex")
    user_config = config.load_user_config()
    search_dirs = config.composed_search_dirs(project, user_config)
    mounts = resource_mounts(search_dirs)
    host_search_dirs = editor_search_dirs(search_dirs)

    lvl, _ = trunk.read_level(subset)
    class_idx = ClassIndex.from_files([(f.stem, str(f)) for d in host_search_dirs
                                       for f in sorted(Path(d).glob("*.u"))])
    for an in lvl.order:
        set_base_pose(lvl.actors[an], class_idx)
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
    print(f"[capture] OceanLab N={N}; starting {CONTAINER}", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        t3d_path = drv.write_work_file(emit_map(actors), ext="t3d")
        pid = O._editor_pid(CONTAINER)
        editor_base = _find_dll_base(CONTAINER, pid, "editor.dll")
        print(f"[capture] editor pid={pid} Editor.dll live base={editor_base:#x}", flush=True)
        va = remap(ADDPOINT_VA, editor_base, EDITOR_PREF)
        script = GDB_SCRIPT.format(pid=pid, va=va)
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c",
                        "cat > /tmp/addpoint.gdb"], input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/addpoint.gdb > /tmp/addpoint.log 2>&1"], check=True)
        for _ in range(120):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/addpoint.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            diag = subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/addpoint.log"],
                                  capture_output=True, text=True).stdout
            raise RuntimeError(f"gdb did not attach. log:\n{diag[:3000]}")
        print("[capture] gdb attached; running MAP IMPORT + MAP REBUILD ...", flush=True)
        saved = "/work/probe_n203.dx"
        drv.begin_script()
        ensure_load(drv, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        drv.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        drv.exec("MAP REBUILD")
        drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
        try:
            drv.run_script(produces=saved, timeout=1800.0)
        except Exception as ex:  # noqa: BLE001
            print(f"[capture] batch wait ended: {ex}", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        log_bytes = subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/addpoint.log"],
                                   capture_output=True).stdout
        out.write_bytes(
            f"Editor.dll live base = {editor_base:#x}  VA = {va:#x}\n\n".encode() + log_bytes)
        print(f"[capture] wrote {out}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
