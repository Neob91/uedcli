#!/usr/bin/env python3
r"""6th-round NYC_Bar N=153 probe: capture the real editor's per-node RASTER-COMMIT verdict (accept
vs fully-occluded) for the WHOLE `LIGHT APPLY` run, in VISIT ORDER, keyed by (light frame origin +
face z-axis, iSurf) -- not raw node index, since this level's world Model2 is only a PERMUTATION
match between native and UED22 (round 4/5).

Round 5 concluded box occlusion, zone crossing and the clip-formula bug class are all cleared, and
the last unexplored territory is rasterization/span-buffer ACCUMULATION ORDER: native's own trace
(`UEDCLI_VISGATE_TRACE_SURF=-1`) shows the three divergent tread surfaces (95/97/67) each get SOME
non-zero accepted pixels when native rasterizes them for Light5's -X face -- e.g. node 20 (surf 67)
accepts 51272 of 168895 raster px, a large, non-ULP-scale remainder. Since span-buffer subtraction
is a strict "first rasterizer to claim a pixel wins" race, an occluder visited BEFORE a target in one
build but AFTER it in the other changes whether the target's own raster attempt finds anything left
to accept -- this is the concrete mechanism this probe measures directly, not `0x1001b470`'s raw
per-pixel scanline setup (documented to crash the container under gdb, `2026-09-06-raster-clipbspsurf-
port/spike.md`, "What could NOT be obtained").

Breakpoint (found by extending `disasm_probe.py`'s ranges into `URender::OccludeBsp`'s raster-commit
tail, `harness/disasm_probe.py`'s new `raster_commit` range, RVA 0x10019a40-0x10019e40):

  `0x10019c1c`: `test %edi,%edi` -- `%edi` is freshly overwritten by the CopyFromRaster (no-subtract,
  RVA 0x1001dd10) / CopyFromRasterUpdate (subtract, RVA 0x1001df70) call's return value (`mov
  %eax,%edi` at RVA 0x10019bc6, matching the exact call sites `2026-09-06-raster-clipbspsurf-port`
  documented). Zero -> nothing left unclaimed -> the node is marked NF_PolyOccluded and skipped
  (jumps straight to the per-node loop-continue at 0x1001a7eb without ever reaching MergeWith/
  emission). Non-zero -> the node keeps going toward zone-crossing/emission. This is INSIDE
  `OccludeBsp`, the same function box_verdict_n153.py/mover_occlusion_probe.py already broke in
  (`BoundVisible` call site) for a FULL light-apply run without crashing -- unlike the raw scanline
  setup at 0x1001b470 (shared with real-time viewport rendering, hence the earlier crash), OccludeBsp
  itself is gather-exclusive.

  At that instruction, the node pointer is still available at a STABLE stack slot the function's own
  code reads from directly (`mov -0x8bc(%ebp),%eax; orb $0x8,0x37(%eax)` on the reject path) -- so
  `$ebp-0x8bc` is `FBspNode*`, and `+0x1c` off it is `iSurf` (confirmed against the moving-brush
  filter's own `push 0x1c(%edi)` argument to `SurfIsDynamic`). The `FSceneNode* Frame` argument is at
  `$ebp-0x8b4` throughout (`mov 0x8(%ebp),%edi; mov %edi,-0x8b4(%ebp)` at OccludeBsp's own entry) --
  same struct box_verdict_n153.py already reads ORIGIN (`+0x34/+0x38/+0x3c`) and Z axis (`+0x4c/+0x50/
  +0x54`, the face's view direction) from.

Usage: raster_order_probe.py --trunk <subset-trunk-dir> [--out log]
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

CONTAINER = "uned-n153-raster-order"
RENDER_PREF = 0x10000000
TEST_EDI = 0x10019C1C  # `test %edi,%edi` -- raster-commit accept/reject decision


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
break *__TESTEDI__
commands
silent
set $hits = $hits + 1
set $node = *(unsigned int*)($ebp-0x8bc)
set $isurf = *(int*)($node+0x1c)
set $fr = *(unsigned int*)($ebp-0x8b4)
printf "V hit=%d isurf=%d edi=%d origin=%.9g,%.9g,%.9g zaxis=%.9g,%.9g,%.9g\n", $hits, $isurf, $edi, *(float*)($fr+0x34), *(float*)($fr+0x38), *(float*)($fr+0x3c), *(float*)($fr+0x4c), *(float*)($fr+0x50), *(float*)($fr+0x54)
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
    out = HERE.parent / "logs" / "raster-order-n153.log"
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
    print(f"[raster-order] {trunk_dir.name}; starting {CONTAINER}", flush=True)
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
        print(f"[raster-order] render.dll live base = {render_base:#x}", flush=True)
        script = GDB_TEMPLATE.replace("__PID__", str(pid)).replace(
            "__TESTEDI__", hex(remap(TEST_EDI, render_base)))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/rorder.gdb"],
                       input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/rorder.gdb > /tmp/rorder.log 2>&1"], check=True)
        for _ in range(240):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/rorder.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[raster-order] attached; running the golden EXEC batch ...", flush=True)
        saved = "/work/probe_rorder.dx"
        drv.begin_script()
        ensure_load(drv, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        drv.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        drv.exec("MAP REBUILD")
        drv.light_apply()
        drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
        try:
            drv.run_script(produces=saved, timeout=1800.0)
        except Exception as ex:
            print(f"[raster-order] batch wait ended: {ex}", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        log_bytes = subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/rorder.log"],
                                   capture_output=True).stdout
        out.write_bytes(f"render.dll live base = {render_base:#x}\n\n".encode() + log_bytes)
        print(f"[raster-order] wrote {out} ({len(log_bytes)} bytes)", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
