#!/usr/bin/env python3
r"""Which two Pawn floats does `ULevel::SetActorZone` use for `FootRegion`/`HeadRegion`?

NOTE on addresses: `rdis.py` prints Engine.dll's PREFERRED VAs, but the live editor loads Engine.dll
relocated by `-0xE9E0000` (`0x101ae190` -> `0x17ce190`, the shadow-ray walker; `0x102dbbb4` ->
`0x18fbbb4`, its per-call flag). Editor.dll is NOT relocated. Breakpoints below are live addresses.

`Engine 0x10161e10` (live `0x1781e10`, `ULevel::SetActorZone`) recomputes, for an actor IsA `APawn`:

    FootRegion = Model->PointRegion(LevelInfo, Location - FVector(0, 0, *(float*)(pawn+0x194)))
    HeadRegion = Model->PointRegion(LevelInfo, Location + FVector(0, 0, *(float*)(pawn+0x2ec)))

`+0x194` is plainly the collision half-height, but `+0x2ec` is a Pawn-only float and UnrealScript
does not serialize property OFFSETS, so it cannot be named from the `.u`. This probe reads both
floats live (plus the actor's Location, which identifies WHICH pawn) at `0x10162008` — the
instruction that loads the first of them — so each can be matched against that class's decoded
defaults (`ClassDefaults`): e.g. `SandraRenton` has CollisionHeight 43, BaseEyeHeight 36,
EyeHeight 0, so the captured pair names both fields unambiguously.

Runs the real golden recipe (MAP IMPORT -> MAP REBUILD -> LIGHT APPLY) with gdb attached first,
because `SetActorZone` is called during the rebuild.

Usage: setactorzone_pawn_offsets.py --trunk <subset-trunk-dir> [--hits N] [--out log]
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

CONTAINER = "uned-setactorzone-offsets"

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

set $n = 0

break *0x1782008
commands
silent
set $n = $n + 1
printf "PAWN %d loc=(%.7g,%.7g,%.7g) f194=%.7g f2ec=%.7g\n", $n, *(float*)($edi+0xd0), *(float*)($edi+0xd4), *(float*)($edi+0xd8), *(float*)($edi+0x194), *(float*)($edi+0x2ec)
if $n >= __HITS__
  printf "TARGET_DONE\n"
  detach
  quit
end
continue
end

printf "ORACLE_ATTACHED\n"
continue
"""


def main() -> int:
    trunk_dir = None
    hits = 40
    out = HERE.parent / "logs" / "setactorzone-pawn-offsets.log"
    for i, a in enumerate(sys.argv):
        if a == "--trunk":
            trunk_dir = Path(sys.argv[i + 1]).resolve()
        if a == "--hits":
            hits = int(sys.argv[i + 1])
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
    print(f"[setzone] {trunk_dir.name}; starting {CONTAINER}", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        t3d_path = drv.write_work_file(emit_map(actors), ext="t3d")
        pid = O._editor_pid(CONTAINER)
        script = GDB.replace("__PID__", str(pid)).replace("__HITS__", str(hits))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/sz.gdb"],
                       input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/sz.gdb > /tmp/sz.log 2>&1"], check=True)
        for _ in range(120):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/sz.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[setzone] attached; running the golden EXEC batch ...", flush=True)
        saved = "/work/probe_setzone.dx"
        drv.begin_script()
        ensure_load(drv, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        drv.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        drv.exec("MAP REBUILD")
        drv.light_apply()
        drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
        try:
            drv.run_script(produces=saved, timeout=2400.0)
        except Exception as ex:
            print(f"[setzone] batch wait ended: {ex}", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/sz.log"],
                                       capture_output=True).stdout)
        print(f"[setzone] wrote {out}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
