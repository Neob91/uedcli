#!/usr/bin/env python3
r"""Observe `LIGHT APPLY` INSIDE the golden pipeline itself (MAP IMPORT -> MAP REBUILD -> LIGHT
APPLY -> MAP SAVE, one `EXEC` batch), with gdb attached from before the batch starts.

`ray_results_at_lightapply.py` can only observe a `MAP LOAD` of an already-built package, and that
run reproduces NATIVE's answer, not the golden's — so whatever makes the golden's rays differ is
state that only exists inside the original build. This probe runs the real recipe under gdb and
reports, at the first shadow ray of `--isurf`: the live node COUNT (`Model->Nodes.Num`, `Model+0x5c`),
every node's live `NodeFlags`/`NumVertices`, and then each ray's endpoints and result.

Same driving code as `build_ued_import_built_golden.py` (dummy builder at `Actors[1]`, `OBJ LOAD` of
the referenced packages, one `EXEC` batch), but on the gdb-capable editor image.

Usage: golden_pipeline_probe.py --trunk <subset-trunk-dir> --isurf N [--rays N] [--out log]
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

CONTAINER = "uned-golden-pipeline-probe"

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
set $n = 0

break *0x100a5043
commands
silent
set $hit = *(int*)($ebp+0xc)
if $armed == 0 && $hit == __ISURF__
  set $armed = 1
  printf "SURF_ENTER isurf=%d\n", $hit

  break *0x17ce193
  commands
  silent
  if $dumped == 0
    set $dumped = 1
    set $model = *(unsigned int*)($ebp+0x0c)
    set $nodes = *(unsigned int*)($model+0x58)
    set $num = *(int*)($model+0x5c)
    printf "NODECOUNT %d\n", $num
    set $i = 0
    while $i < $num
      printf "NODE %d flags=0x%02x nv=%d\n", $i, *(unsigned char*)($nodes+$i*64+0x37), *(unsigned char*)($nodes+$i*64+0x36)
      set $i = $i + 1
    end
  end
  continue
  end

  break *0x100a5a04
  commands
  silent
  set $n = $n + 1
  printf "ARGS %d light=(%.7g,%.7g,%.7g) lumel=(%.7g,%.7g,%.7g)\n", $n, *(float*)($esp+0x08), *(float*)($esp+0x0c), *(float*)($esp+0x10), *(float*)($esp+0x14), *(float*)($esp+0x18), *(float*)($esp+0x1c)
  continue
  end

  break *0x100a5a07
  commands
  silent
  printf "RESULT %d clear=%d\n", $n, $eax
  if $n >= __RAYS__
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
    trunk_dir = isurf = None
    rays = 2000
    out = HERE.parent / "logs" / "golden-pipeline-probe.log"
    for i, a in enumerate(sys.argv):
        if a == "--trunk":
            trunk_dir = Path(sys.argv[i + 1]).resolve()
        if a == "--isurf":
            isurf = int(sys.argv[i + 1])
        if a == "--rays":
            rays = int(sys.argv[i + 1])
        if a == "--out":
            out = Path(sys.argv[i + 1]).resolve()
    if trunk_dir is None or isurf is None:
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
    print(f"[golden-probe] {trunk_dir.name} isurf={isurf}; starting {CONTAINER}", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        t3d_path = drv.write_work_file(emit_map(actors), ext="t3d")
        pid = O._editor_pid(CONTAINER)
        script = (GDB.replace("__PID__", str(pid)).replace("__ISURF__", str(isurf))
                  .replace("__RAYS__", str(rays)))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/gp.gdb"],
                       input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/gp.gdb > /tmp/gp.log 2>&1"], check=True)
        for _ in range(120):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/gp.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[golden-probe] attached; running the golden EXEC batch ...", flush=True)
        saved = "/work/probe_golden.dx"
        drv.begin_script()
        ensure_load(drv, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        drv.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        drv.exec("MAP REBUILD")
        drv.light_apply()
        drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
        try:
            drv.run_script(produces=saved, timeout=2400.0)
        except Exception as ex:                       # gdb may detach mid-batch; the log still has it
            print(f"[golden-probe] batch wait ended: {ex}", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/gp.log"],
                                       capture_output=True).stdout)
        print(f"[golden-probe] wrote {out}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
