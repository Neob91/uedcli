#!/usr/bin/env python3
r"""Live-capture the DECISIVE crossing for `island-n-332-leaf-273-permeating-light-vertex-tie` /
`unatco-n-226-leaf-12-gets-a-permeating-light157`, in HEX (not decimal), at two points:

1. `FPlane::FPlane(A,B,C)` (`core.dll 0x1000b440`, `__thiscall`, `ret 0x24`) -- the plane
   `clip_beam` builds as `FPlane(Light, clip[j], clip[jPrev])`. Args on the stack (12 bytes each):
   A.xyz @ [ebp+8,+0xc,+0x10], B.xyz @ [ebp+0x14,+0x18,+0x1c], C.xyz @ [ebp+0x20,+0x24,+0x28].
   `ecx` = `this` (the FPlane being built: Normal.xyz @ +0,+4,+8, W @ +0xc), unclobbered until
   `mov esi,ecx` well after the args are read, so it's safe to read at entry too. Disassembled
   fresh this session (pefile+capstone, `dev/docs/unrealed/extracting-from-dll.md` method) --
   confirms the args/output layout matches `permeating_lights.rs`'s `plane_w`/cross-product port
   instruction for instruction (same finding as the two board items' prior disassembly, now with
   the calling convention pinned well enough to breakpoint on identity).

2. `FLinePlaneIntersection(out, P1, P2, Plane)` (`Engine.dll 0x101507c0`, real call site
   `0x1015214b` inside `SplitWithPlaneFast`, plain stack args, `ret` with no cleanup (caller
   cleans)): [ebp+8]=out ptr, [ebp+0xc]=P1 ptr, [ebp+0x10]=P2 ptr, [ebp+0x14]=Plane ptr
   (Normal.xyz @ +0/+4/+8, W @ +0xc). Disassembled fresh this session; confirms
   `permeating_lights.rs::line_plane_intersection`'s numerator/denominator grouping instruction
   for instruction (same finding the board items already report, re-derived independently here).

Both breakpoints are CONDITIONAL on the exact hex bit patterns native's own
`UEDCLI_PERM_TRACE_EDGE` trace recorded for the decisive Island N=332 crossing (light=Light124,
edge 162->275, `clip_beam` edge j=1) -- see `--case island` below for the literal values, captured
via `actor_parity.py ... native 332` with `UEDCLI_PERM_TRACE=34 UEDCLI_PERM_TRACE_EDGE=162-275`.
This narrows likely-thousands of FPlane/FLinePlaneIntersection calls across a whole MAP REBUILD
down to (ideally) the one call that matters, filtered purely on VALUE identity, not call site
(FLinePlaneIntersection is also called from ordinary CSG BSP splitting through the same address).

Usage: crossing_probe.py --trunk <subset-trunk-dir> --case island|unatco [--out log] [--hits N]
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

CONTAINER = "uned-crossing-probe"
CORE_PREF = 0x10000000
ENGINE_PREF = 0x10000000
EDITOR_PREF = 0x10000000

# `FEditorVisibility::ActorVisibility` convergence point (Editor.dll 0x100a6edd, see
# `actor_visibility_probe.py`) -- fires for EVERY recursive AND seed entry, always with the SAME
# `Actor*` (the light) for the whole depth-first flood of one light. This is the cheap, LOW-volume
# gate breakpoint 1-4 below arm/disarm on: v1 of this probe conditioned FPlane/FLinePlaneIntersection
# directly on their own argument VALUES and it wedged the editor -- those two functions are also the
# CSG BSP splitter's own primitives (confirmed: only 2 static callers of FLinePlaneIntersection in
# Engine.dll, one of them SplitWithPlaneFast, which itself has 3 in-DLL callers besides the
# ActorVisibility beam clip -- raw E8-scan, `_scratch/find_callers.py`), so an always-armed
# conditional breakpoint on them pays a ptrace stop for every CSG split in the whole subset, not just
# the permeating flood. Gating on ActorVisibility's own entry (armed only while the CURRENT actor is
# Light124) bounds the live window to that one light's flood.
AV_ENTRY = 0x100A6EDD

# FPlane::FPlane(A,B,C) -- core.dll. Entry: right after `mov ebp,esp`, before esp is adjusted (arg
# offsets are ebp-relative positive, unaffected). Exit: `pop esi`, not yet executed -- Normal/W
# already stored at [esi..esi+0xc], esi == the FPlane* (== the ctor's `this`, read at entry).
FPLANE_ENTRY = 0x1000B443
FPLANE_EXIT = 0x1000B514

# FLinePlaneIntersection(out,P1,P2,Plane) -- Engine.dll. Entry: right after `mov ebp,esp`. Exit:
# `pop ebp`, not yet executed -- the crossing's x/y/z already stored at [eax..eax+8] (eax == the
# out ptr, reloaded from [ebp+8] just before the stores).
LPI_ENTRY = 0x101507C3
LPI_EXIT = 0x10150871

# Literal hex bit patterns from native's own UEDCLI_PERM_TRACE_EDGE trace (this session, Island
# N=332, li=34 "Light124", edge 162->275, clip_beam edge j=1):
#   PERM_PLANE j=1 light=(c58d82c6,45890d69,4280bdc9) a=(c58c7fff,457f0000,c30c0001)
#     b=(c58c7fff,457f0000,43400000) normal=(3f7e941b,3dd784f6,00000000) w=c57c9ae2
#   PERM_CROSS prev=(c55ec000,4562c000,43400000) cur=(c58c7fff,457f0000,43400000)
#     -> crossing=(c58c7fff,457efffb,43400000)  [== y=4079.998779296875]
ISLAND_CASE = dict(
    light=(0xC58D82C6, 0x45890D69, 0x4280BDC9),
    b=(0xC58C7FFF, 0x457F0000, 0x43400000),   # clip[j]     == FPlane ctor's B
    a=(0xC58C7FFF, 0x457F0000, 0xC30C0001),   # clip[jPrev] == FPlane ctor's C
    p1=(0xC55EC000, 0x4562C000, 0x43400000),  # line_plane_intersection's prev/P1
    p2=(0xC58C7FFF, 0x457F0000, 0x43400000),  # line_plane_intersection's cur/P2 (== B, the tie)
)

# UNATCO N=226, li=6 "Light157", edge 102->13 (per the board item's own trace); values TBD -- fill
# in with a `UEDCLI_PERM_TRACE=6 UEDCLI_PERM_TRACE_EDGE=102-13` capture before using --case unatco.
UNATCO_CASE = None

CASES = {"island": ISLAND_CASE, "unatco": UNATCO_CASE}


def remap(addr: int, live_base: int, pref: int) -> int:
    return live_base + (addr - pref)


def _find_dll_base(container: str, pid: int, dll: str) -> int:
    maps = subprocess.run(["docker", "exec", container, "cat", f"/proc/{pid}/maps"],
                          capture_output=True, text=True, check=True).stdout
    for line in maps.splitlines():
        if dll.lower() in line.lower():
            return int(line.split("-", 1)[0], 16)
    raise RuntimeError(f"{dll} not found")


def _cond_vec3(base_expr: str, bits: tuple[int, int, int]) -> str:
    x, y, z = bits
    return (f"*(unsigned int*)({base_expr}+0)=={x:#x} && "
            f"*(unsigned int*)({base_expr}+4)=={y:#x} && "
            f"*(unsigned int*)({base_expr}+8)=={z:#x}")


def _dump_vec3(label: str, base_expr: str) -> str:
    return (f'printf "{label}=(%08x,%08x,%08x) [%.9g,%.9g,%.9g]", '
            f'*(unsigned int*)({base_expr}+0), *(unsigned int*)({base_expr}+4), '
            f'*(unsigned int*)({base_expr}+8), *(float*)({base_expr}+0), '
            f'*(float*)({base_expr}+4), *(float*)({base_expr}+8)')


def build_gdb_script(case: dict, max_hits: int) -> str:
    fplane_cond = " && ".join([
        _cond_vec3("$ebp+8", case["light"]),
        _cond_vec3("$ebp+0x14", case["b"]),
        _cond_vec3("$ebp+0x20", case["a"]),
    ])
    lpi_cond = " && ".join([
        f"*(unsigned int*)(*(unsigned int*)($ebp+0xc)+0)=={case['p1'][0]:#x}",
        f"*(unsigned int*)(*(unsigned int*)($ebp+0xc)+4)=={case['p1'][1]:#x}",
        f"*(unsigned int*)(*(unsigned int*)($ebp+0xc)+8)=={case['p1'][2]:#x}",
        f"*(unsigned int*)(*(unsigned int*)($ebp+0x10)+0)=={case['p2'][0]:#x}",
        f"*(unsigned int*)(*(unsigned int*)($ebp+0x10)+4)=={case['p2'][1]:#x}",
        f"*(unsigned int*)(*(unsigned int*)($ebp+0x10)+8)=={case['p2'][2]:#x}",
    ])
    light = case["light"]
    av_match = (f"*(unsigned int*)($act+0xd0)=={light[0]:#x} && "
                f"*(unsigned int*)($act+0xd4)=={light[1]:#x} && "
                f"*(unsigned int*)($act+0xd8)=={light[2]:#x}")
    return f"""
set pagination off
set confirm off
set height 0
set width 0
attach __PID__
handle SIGSEGV nostop noprint pass
handle SIGUSR1 nostop noprint pass
handle SIGUSR2 nostop noprint pass
handle SIGPIPE nostop noprint pass
set $fp_hits = 0
set $lpi_hits = 0
set $armed = 0
set $av_hits = 0

break *__FPLANE_ENTRY__ if {fplane_cond}
commands
silent
set $fp_hits = $fp_hits + 1
set $fp_this = $ecx
printf "FPLANE_ENTRY hit=%d this=%#x ", $fp_hits, $fp_this
{_dump_vec3("A", "$ebp+8")}
{_dump_vec3(" B", "$ebp+0x14")}
{_dump_vec3(" C", "$ebp+0x20")}
printf "\\n"
if $fp_hits > __MAXHITS__
delete 1
end
continue
end
disable 1

break *__FPLANE_EXIT__
commands
silent
if $fp_hits > 0 && $fp_hits <= __MAXHITS__
printf "FPLANE_EXIT  this=%#x "
{_dump_vec3("Normal", "$esi+0")}
printf " W=(%08x) [%.9g]", *(unsigned int*)($esi+0xc), *(float*)($esi+0xc)
printf "\\n"
end
continue
end
disable 2

break *__LPI_ENTRY__ if {lpi_cond}
commands
silent
set $lpi_hits = $lpi_hits + 1
set $lpi_out = *(unsigned int*)($ebp+8)
printf "LPI_ENTRY hit=%d out=%#x ", $lpi_hits, $lpi_out
set $p1 = *(unsigned int*)($ebp+0xc)
set $p2 = *(unsigned int*)($ebp+0x10)
set $pl = *(unsigned int*)($ebp+0x14)
{_dump_vec3("P1", "$p1")}
{_dump_vec3(" P2", "$p2")}
{_dump_vec3(" Normal", "$pl")}
printf " W=(%08x) [%.9g]", *(unsigned int*)($pl+0xc), *(float*)($pl+0xc)
printf "\\n"
if $lpi_hits > __MAXHITS__
delete 3
end
continue
end
disable 3

break *__LPI_EXIT__
commands
silent
if $lpi_hits > 0 && $lpi_hits <= __MAXHITS__
printf "LPI_EXIT "
{_dump_vec3("crossing", "$eax")}
printf "\\n"
end
continue
end
disable 4

# Gate breakpoint: `FEditorVisibility::ActorVisibility`'s convergence point (Editor.dll), fires for
# every recursive AND seed entry with the light Actor* unchanged for the whole flood of one light.
# Cheap and unconditional (like `actor_visibility_probe.py`'s own ENTRY breakpoint) -- arms 1-4 only
# while the CURRENT flood's actor is Light124, so FPlane/FLinePlaneIntersection's (still per-hit
# costly) conditions are only paid during that one light's traversal, not the whole MAP REBUILD.
break *__AV_ENTRY__
commands
silent
set $av_hits = $av_hits + 1
set $act = *(unsigned int*)($ebp+8)
if {av_match}
if $armed == 0
printf "AV_ARM hit=%d\\n", $av_hits
end
set $armed = 1
enable 1
enable 2
enable 3
enable 4
else
if $armed == 1
printf "AV_DISARM hit=%d\\n", $av_hits
end
set $armed = 0
disable 1
disable 2
disable 3
disable 4
end
continue
end

printf "ORACLE_ATTACHED\\n"
continue
"""


def main() -> int:
    trunk_dir = None
    case_name = None
    max_hits = 50
    out = HERE.parent / "logs" / "crossing-probe.log"
    for i, a in enumerate(sys.argv):
        if a == "--trunk":
            trunk_dir = Path(sys.argv[i + 1]).resolve()
        if a == "--case":
            case_name = sys.argv[i + 1]
        if a == "--out":
            out = Path(sys.argv[i + 1]).resolve()
        if a == "--hits":
            max_hits = int(sys.argv[i + 1])
    if trunk_dir is None or case_name not in CASES or CASES[case_name] is None:
        print(__doc__)
        return 2
    case = CASES[case_name]

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
    print(f"[crossing] {trunk_dir.name}; starting {CONTAINER}", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        t3d_path = drv.write_work_file(emit_map(actors), ext="t3d")
        pid = O._editor_pid(CONTAINER)
        core_base = _find_dll_base(CONTAINER, pid, "core.dll")
        engine_base = _find_dll_base(CONTAINER, pid, "engine.dll")
        editor_base = _find_dll_base(CONTAINER, pid, "editor.dll")
        print(f"[crossing] core.dll live base = {core_base:#x}  Engine.dll live base = {engine_base:#x} "
              f"Editor.dll live base = {editor_base:#x}", flush=True)
        script = (build_gdb_script(case, max_hits)
                  .replace("__PID__", str(pid))
                  .replace("__FPLANE_ENTRY__", hex(remap(FPLANE_ENTRY, core_base, CORE_PREF)))
                  .replace("__FPLANE_EXIT__", hex(remap(FPLANE_EXIT, core_base, CORE_PREF)))
                  .replace("__LPI_ENTRY__", hex(remap(LPI_ENTRY, engine_base, ENGINE_PREF)))
                  .replace("__LPI_EXIT__", hex(remap(LPI_EXIT, engine_base, ENGINE_PREF)))
                  .replace("__AV_ENTRY__", hex(remap(AV_ENTRY, editor_base, EDITOR_PREF)))
                  .replace("__MAXHITS__", str(max_hits)))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/crossing.gdb"],
                       input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/crossing.gdb > /tmp/crossing.log 2>&1"], check=True)
        for _ in range(240):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/crossing.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[crossing] attached; running the golden EXEC batch ...", flush=True)
        saved = "/work/probe_crossing.dx"
        drv.begin_script()
        ensure_load(drv, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        drv.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        drv.exec("MAP REBUILD")
        drv.light_apply()
        drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
        try:
            drv.run_script(produces=saved, timeout=900.0)
        except Exception as ex:
            print(f"[crossing] batch wait ended: {ex}", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        log_bytes = subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/crossing.log"],
                                   capture_output=True).stdout
        out.write_bytes(
            f"core.dll live base = {core_base:#x}  Engine.dll live base = {engine_base:#x}\n\n".encode()
            + log_bytes)
        print(f"[crossing] wrote {out}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
