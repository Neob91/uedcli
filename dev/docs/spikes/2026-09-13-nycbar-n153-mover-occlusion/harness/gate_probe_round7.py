#!/usr/bin/env python3
r"""7th-round NYC_Bar N=153 probe: read BOTH stack slots round 6 flagged as the next lead
(`-0x8ec(%ebp)`, `-0x918(%ebp)`) at the exact point they gate whether a raster-accepted node's surf
gets committed to the light's per-surf output record, keyed by `iSurf` -- the board item's own
recommended next probe (`nyc-bar-n-153-world-model2-lightmap-runs-ued22/overview.md`, "Sixth round").

Static disassembly this round (`disasm_probe.py`'s new combined `raster_commit_to_portal_emit` range,
RVA 0x10019a40-0x1001a8e0, filling a 928-byte gap the round-6 two-range capture never transcribed)
decoded the mechanism connecting the two slots:

  - `-0x8ec(%ebp)` is written (`0x1001a1fa` region, live-mapped `0x015c9ffa`: `mov %ecx,%eax; not %eax;
    and $1,%eax; mov %eax,-0x8ec(%ebp)`) as `NOT(PolyFlags & PF_Invisible)` -- but ONLY on the branch
    reached when the surf's PolyFlags has `PF_Portal` (0x4000000) set (`test $0x4000000,%ecx; je
    0x1001a324`, RVA). For a NON-portal surf (every ordinary opaque world surf, including the tread
    surfaces 95/97/67), that `je` is TAKEN and jumps straight past this write AND past the two reads
    at RVA 0x1001a2be/0x1001a30d, landing directly at RVA 0x1001a324 (`test $1,%cl; jne <reject>`,
    a PF_Invisible test read directly off PolyFlags' own low byte) -- so `-0x8ec(%ebp)` is IRRELEVANT
    for every surf this item cares about; it only gates PORTAL surfaces.

  - `-0x918(%ebp)` is the one that matters for a non-portal surf. It is computed ONCE per node visit,
    UNCONDITIONALLY, near the top of this whole block (RVA ~0x100199e9/live `0x015c9ad9`-`0x015c9b12`):
    a linked-list walk over `table[iSurf]` (`-0x948(%ebp)`, a per-surf head-pointer array) comparing
    each entry's field-at-`+0x34` against a key from a vtable call on `Frame->Level`
    (`mov Frame->Level,%ecx; call *[vtable+...]` -- the SAME vtable slot `0x15e438c` used at the
    moving-brush filter's own `SurfIsDynamic`-adjacent code and 3 other call sites in this function).
    Left in `-0x918(%ebp)`: the MATCHING list entry (nonzero) if found, or 0 if the list is empty/
    exhausted without a match.
    For a PORTAL surf that also passes the `-0x8ec` check, `-0x918(%ebp)` gets explicitly RESET to 0
    (RVA ~0x1001a31a: `xor %eax,%eax; mov %eax,-0x918(%ebp)`) before the light-list loop -- but for a
    NON-portal surf, that reset is skipped entirely (the `je 0x1001a324` bypass lands past it), so
    `-0x918(%ebp)` keeps whatever the early per-surf table lookup found.
    Tested at RVA 0x1001a436 (`test %edi,%edi`): zero falls through to RVA 0x1001a43e, which writes
    `iSurf` into an output record at `+0x4` off a pointer at `$ebp-0x8c8` (confirmed live below) --
    the "commit to output" path round 6 suspected but did not confirm live. Nonzero jumps to RVA
    0x1001a621, a DIFFERENT code path (prepends an entry to a list at `node-or-similar+0x44`, not the
    per-surf output record) -- i.e. DIVERTED, not committed.

This probe breaks at RVA 0x1001a436 itself (the `test %edi,%edi` testing `-0x918(%ebp)`) and reads,
per hit: `iSurf` (node ptr at `$ebp-0x8bc`, `+0x1c`), the tested value itself (`%edi`, i.e.
`-0x918(%ebp)`), `-0x8ec(%ebp)`'s current value (for completeness, even though it should be
irrelevant off the portal path), and the light Frame's origin/z-axis (same struct/offsets
`box_verdict_n153.py`/`raster_order_probe.py` already use) to key hits to Light5's own faces.

Usage: gate_probe_round7.py --trunk <subset-trunk-dir> [--out log]
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

CONTAINER = "uned-n153-gate7"
RENDER_PREF = 0x10000000
TEST_EDI_918 = 0x1001A436  # `test %edi,%edi` gating -0x918(%ebp)'s "commit vs divert" branch


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
break *__GATE918__
commands
silent
set $hits = $hits + 1
set $node = *(unsigned int*)($ebp-0x8bc)
set $isurf = *(int*)($node+0x1c)
set $fr = *(unsigned int*)($ebp-0x8b4)
set $s918 = $edi
set $s8ec = *(int*)($ebp-0x8ec)
printf "G hit=%d isurf=%d s918=%d s8ec=%d origin=%.9g,%.9g,%.9g zaxis=%.9g,%.9g,%.9g\n", $hits, $isurf, $s918, $s8ec, *(float*)($fr+0x34), *(float*)($fr+0x38), *(float*)($fr+0x3c), *(float*)($fr+0x4c), *(float*)($fr+0x50), *(float*)($fr+0x54)
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
    out = HERE.parent / "logs" / "gate-round7-n153.log"
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
    print(f"[gate7] {trunk_dir.name}; starting {CONTAINER}", flush=True)
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
        print(f"[gate7] render.dll live base = {render_base:#x}", flush=True)
        script = GDB_TEMPLATE.replace("__PID__", str(pid)).replace(
            "__GATE918__", hex(remap(TEST_EDI_918, render_base)))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/gate7.gdb"],
                       input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/gate7.gdb > /tmp/gate7.log 2>&1"], check=True)
        for _ in range(240):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/gate7.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[gate7] attached; running the golden EXEC batch ...", flush=True)
        saved = "/work/probe_gate7.dx"
        drv.begin_script()
        ensure_load(drv, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        drv.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        drv.exec("MAP REBUILD")
        drv.light_apply()
        drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
        try:
            drv.run_script(produces=saved, timeout=1800.0)
        except Exception as ex:
            print(f"[gate7] batch wait ended: {ex}", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        log_bytes = subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/gate7.log"],
                                   capture_output=True).stdout
        out.write_bytes(f"render.dll live base = {render_base:#x}\n\n".encode() + log_bytes)
        print(f"[gate7] wrote {out} ({len(log_bytes)} bytes)", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
