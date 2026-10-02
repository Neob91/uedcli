#!/usr/bin/env python3
r"""Live-confirm (or refute) the amortization-counter hypothesis from spike.md.

Runs the REAL golden pipeline (MAP IMPORT -> MAP REBUILD -> [optional forced redraws] ->
LIGHT APPLY -> MAP SAVE), gdb attached from before the batch starts. At the FIRST
`illuminateSurf` (`0x100a5043`) entry (any `iSurf` -- no gate, unlike the parent spike's
per-surf probes, since we only need one snapshot) and the walker's first entry
(`0x17ce193`) right after, dumps:

  - the proposed global counter `*(int*)0x1005fa24`
  - `Model->Nodes.Num` and every live node's `NodeFlags` byte (`+0x37`, stride 64)

then detaches. Same driving code as `build_ued_import_built_golden.py` (dummy builder at
`Actors[1]`, `OBJ LOAD` of referenced packages, one `EXEC` batch) reused from the parent
spike's `golden_pipeline_probe.py`.

Options to force paint events between `MAP REBUILD` and `LIGHT APPLY` (to test whether that
advances the counter / changes which nodes get a real box test):
  --open-camera        one `CAMERA OPEN` (one initial-creation paint)
  --redraws N           N `REDRAWALLVIEWPORTS` calls after --open-camera (no new paint expected)
  --new-cameras N       N distinct new `CAMERA OPEN`s (N initial-creation paints)

Usage: counter_and_flags_probe.py --trunk <subset-trunk-dir> [--open-camera] [--redraws N]
                                   [--new-cameras N] [--out log]
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

CONTAINER = "uned-counter-flags-probe"
COUNTER_ADDR = "0x1005fa24"

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

set $armed = 0
set $dumped = 0

break *0x100a5043
commands
silent
if $armed == 0
  set $armed = 1
  printf "SURF_ENTER isurf=%d counter=%d\n", *(int*)($ebp+0xc), *(int*)__COUNTER__

  break *0x17ce193
  commands
  silent
  if $dumped == 0
    set $dumped = 1
    set $model = *(unsigned int*)($ebp+0x0c)
    set $nodes = *(unsigned int*)($model+0x58)
    set $num = *(int*)($model+0x5c)
    printf "COUNTER %d\n", *(int*)__COUNTER__
    printf "NODECOUNT %d\n", $num
    set $i = 0
    while $i < $num
      printf "NODE %d flags=0x%02x nv=%d\n", $i, *(unsigned char*)($nodes+$i*64+0x37), *(unsigned char*)($nodes+$i*64+0x36)
      set $i = $i + 1
    end
    printf "TARGET_DONE\n"
    detach
    quit
  end
  continue
  end
  continue
end
continue
end

printf "ORACLE_ATTACHED\n"
continue
"""


def main() -> int:
    trunk_dir = None
    redraws = 0
    open_camera = False
    new_cameras = 0
    out = HERE.parent / "logs" / "counter-and-flags-probe.log"
    for i, a in enumerate(sys.argv):
        if a == "--trunk":
            trunk_dir = Path(sys.argv[i + 1]).resolve()
        if a == "--redraws":
            redraws = int(sys.argv[i + 1])
        if a == "--open-camera":
            open_camera = True
        if a == "--new-cameras":
            new_cameras = int(sys.argv[i + 1])
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
    print(f"[counter-probe] {trunk_dir.name} redraws={redraws}; starting {CONTAINER}", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        t3d_path = drv.write_work_file(emit_map(actors), ext="t3d")
        pid = O._editor_pid(CONTAINER)
        script = GDB.replace("__PID__", str(pid)).replace("__COUNTER__", COUNTER_ADDR)
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/cp.gdb"],
                       input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/cp.gdb > /tmp/cp.log 2>&1"], check=True)
        for _ in range(120):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/cp.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[counter-probe] attached; running the golden EXEC batch ...", flush=True)
        saved = "/work/probe_counter.dx"
        drv.begin_script()
        ensure_load(drv, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        drv.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        drv.exec("MAP REBUILD")
        if open_camera:
            drv.exec("CAMERA OPEN NAME=ProbeCam XR=64 YR=64 REN=6")
        for _ in range(redraws):
            drv.exec("REDRAWALLVIEWPORTS")
        for i in range(new_cameras):
            drv.exec(f"CAMERA OPEN NAME=ProbeCam{i} XR=64 YR=64 REN=6")
        drv.light_apply()
        drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
        try:
            drv.run_script(produces=saved, timeout=2400.0)
        except Exception as ex:                       # gdb may detach mid-batch; the log still has it
            print(f"[counter-probe] batch wait ended: {ex}", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/cp.log"],
                                       capture_output=True).stdout)
        print(f"[counter-probe] wrote {out}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
