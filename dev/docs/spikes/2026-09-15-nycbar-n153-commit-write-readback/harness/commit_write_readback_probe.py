#!/usr/bin/env python3
r"""Round 9 (2026-09-15): live-capture the WRITE side of Editor.dll's gather commit loop
(`0x100a4ba0`-`0x100a5010`, already fully disassembled for its two GATES in round 6/8 -- both confirmed
to pass for Light5 x world surf 67/95/97) and the READ side `illuminateSurf` (`0x100a5010`-...) uses to
decide whether to run its per-light raytrace loop for a surf at all -- settling round 8's own flagged
next step ("what does a surf that passes both known gates get committed INTO").

**Static finding this round** (`gather_commit_disasm.txt`/`illuminatesurf_full.txt`, plain `objdump -d`
against the extracted `Editor.dll` -- no docker/gdb needed for this half, since Editor.dll does not
relocate under Wine, RVA == live VA):

- The commit call at RVA `0x100a4f10` (`call 0x100123e0`, a thiscall) is reached only after BOTH known
  gates pass. Its `ecx` ("this") = `*(GatherCtx+0x1c) + iSurf*12` -- i.e. a PER-SURF `TArray<AActor*>`
  living in an array at `GatherCtx+0x1c`, one 12-byte TArray slot per surf (`CandidateLights[iSurf]`).
  Its pushed arg = `&LightActorLocal` (the current light's own pointer, on the stack). This matches
  `TArray<AActor*>::AddItem(Light)` -- `0x100123e0` is a generic template instantiation, but the
  computed target address is unambiguous: `CandidateLights[iSurf]`.
- `illuminateSurf` (RVA `0x100a5010`) reads the SAME array through the SAME offset off ITS OWN `this`
  (`ebx`, RVA `0x100a557c`/`0x100a557f`): `eax = *(ebx+0x1c)`; `cmp [eax + iSurf*12 + 0x4], 0` (RVA
  `0x100a557f`) -- `CandidateLights[iSurf].ArrayNum`. **If this is ZERO, execution jumps straight to
  `0x100a5b33`, skipping the entire per-light raytrace loop for this surf.** This is EXACTLY consistent
  with round 3's `illuminate_ray_probe.py` finding (`illuminateSurf` entered once per surf, shadow-ray
  call site never reached) -- this is very likely the mechanism, PROVIDED the `this`/`CandidateLights`
  base illuminateSurf reads is the SAME live object the commit loop wrote into for Light5.

**Open question this probe settles live**: does the commit call at `0x100a4f10` actually execute (and
actually increment `CandidateLights[iSurf].ArrayNum`) for (Light5, iSurf) in {67, 95, 97}, and does
`illuminateSurf`'s read at `0x100a557f` see the SAME nonzero count for the same iSurf -- or does it see
zero (a different `GatherCtx`/`CandidateLights` array, or the count reset between the two), which would
directly explain the observed exclusion without inventing a new gate.

Two breakpoints, both in Editor.dll (no ASLR under Wine -- RVA == live VA, no remap needed, per
`gather_disasm_probe.py`'s own comment):

- `WRITE_SITE` = `0x100a4f10` (before the `call 0x100123e0`): reads iSurf (derived from `ecx`/`eax`),
  `GatherCtx` (`edi`), `CandidateLights` base (`eax`), the target slot's ArrayNum BEFORE the call, the
  Light pointer (`[ebp-0x38]`) and its Location (`+0xd0/0xd4/0xd8`). Stashes the target slot's address
  in a gdb convenience var (`$last_slot`) for the paired post-call read.
- `WRITE_SITE_RET` = `0x100a4f15` (the instruction right after the call returns): reads
  `*(int*)($last_slot+4)`, the SAME slot's ArrayNum AFTER the call, to confirm the write landed.
- `READ_SITE` = `0x100a557f` (before `cmp [eax+ecx+0x4],0` in `illuminateSurf`): reads iSurf (`ecx/12`),
  `this` (`ebx`), `CandidateLights` base (`eax`), and the ArrayNum being tested.

Usage: commit_write_readback_probe.py --trunk <subset-trunk-dir> [--out log]
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

CONTAINER = "uned-n153-commit-write-readback"

WRITE_SITE = 0x100A4F10       # `call 0x100123e0` -- the AddItem commit call (before it executes)
WRITE_SITE_RET = 0x100A4F15   # instruction right after the call returns
READ_SITE = 0x100A557F        # `cmp [eax+ecx*1+0x4],0` in illuminateSurf -- the ArrayNum test

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

set $whits = 0
set $rhits = 0
set $last_slot = 0

break *__WRITE_SITE__
commands
silent
set $whits = $whits + 1
set $base = *(unsigned int*)($edi+0x1c)
set $slot = $ecx
set $isurf = ($slot - $base) / 12
set $before = *(int*)($slot+4)
set $light = *(unsigned int*)($ebp-0x38)
set $last_slot = $slot
printf "W hit=%d isurf=%d gatherctx=%#x base=%#x slot=%#x before=%d light=%#x loc=%.9g,%.9g,%.9g\n", $whits, $isurf, $edi, $base, $slot, $before, $light, *(float*)($light+0xd0), *(float*)($light+0xd4), *(float*)($light+0xd8)
continue
end

break *__WRITE_SITE_RET__
commands
silent
set $rhits = $rhits + 1
set $after = *(int*)($last_slot+4)
printf "WR hit=%d slot=%#x after=%d\n", $rhits, $last_slot, $after
continue
end

set $ihits = 0
break *__READ_SITE__
commands
silent
set $ihits = $ihits + 1
set $rbase = $eax
set $roff = $ecx
set $risurf = $roff / 12
set $rcount = *(int*)($eax+$ecx+4)
printf "R hit=%d isurf=%d this=%#x base=%#x count=%d\n", $ihits, $risurf, $ebx, $rbase, $rcount
continue
end

printf "ORACLE_ATTACHED\n"
continue
"""


def main() -> int:
    trunk_dir = None
    out = HERE.parent / "logs" / "commit-write-readback-n153.log"
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
    print(f"[commit-rw] {trunk_dir.name}; starting {CONTAINER}", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        t3d_path = drv.write_work_file(emit_map(actors), ext="t3d")
        pid = O._editor_pid(CONTAINER)
        script = GDB_TEMPLATE.replace("__PID__", str(pid)).replace(
            "__WRITE_SITE__", hex(WRITE_SITE)).replace(
            "__WRITE_SITE_RET__", hex(WRITE_SITE_RET)).replace(
            "__READ_SITE__", hex(READ_SITE))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/commitrw.gdb"],
                       input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/commitrw.gdb > /tmp/commitrw.log 2>&1"], check=True)
        for _ in range(240):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/commitrw.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[commit-rw] attached; running the golden EXEC batch ...", flush=True)
        saved = "/work/probe_commitrw.dx"
        drv.begin_script()
        ensure_load(drv, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        drv.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        drv.exec("MAP REBUILD")
        drv.light_apply()
        drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
        try:
            drv.run_script(produces=saved, timeout=1800.0)
        except Exception as ex:
            print(f"[commit-rw] batch wait ended: {ex}", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        log_bytes = subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/commitrw.log"],
                                   capture_output=True).stdout
        out.write_bytes(log_bytes)
        print(f"[commit-rw] wrote {out} ({len(log_bytes)} bytes)", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
