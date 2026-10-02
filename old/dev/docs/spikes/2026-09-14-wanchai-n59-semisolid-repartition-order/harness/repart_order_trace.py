#!/usr/bin/env python3
r"""Live GDB capture: the TRUE call order of `bspRepartition(Model, iChild, 2)`
(`Editor.dll 0x10049fc0`) across a WHOLE `MAP REBUILD`, fingerprinting each call by its first
`bspAddNode` (`0x10034e80`) Base point + iLink -- to settle whether the editor's own per-child
repartition calls are interleaved with the detail-brush (`PF_Semisolid`) `bspBrushCSG` loop (one
call per detail brush, right after that brush's own CSG) or batched separately in some other order.

WHY (`wanchai-n59-mover-polys-model2-diverges`). Native's own `repartition_frontier`
(`uedcli-native/src/bspcsg.rs`) reconstructs every frontier subtree that grew during the Pass-2
detail-brush loop and sets `Model.Polys` to the LAST call's soup (matching the editor's OWN
established mechanism -- WanChai N35's fix). Its worklist order is a STATIC DFS position
(`collect_repartition_frontier`'s list_a-then-list_b), computed once before Pass 2 runs. WanChai
N=59 has THREE detail (`PF_Semisolid` `CSG_Add`) brushes in this subset -- `Brush323` (actor 35),
`Brush324` (actor 39), `Brush904` (actor 59, the new one) -- and native's static DFS order makes
the (unrelated, pre-existing) Brush323/324 call win over Brush904's, producing 16 polys where UED22
produces 1 (Brush904's own). This capture checks whether the REAL editor's call order is instead
CHRONOLOGICAL (per detail-brush, i.e. Brush904's own call — the last brush processed — fires last
and so wins), which would mean native's fix is to interleave repartition with Pass 2's own loop
instead of batching a static-order pass after it.

MECHANISM (already disassembly-established by `2026-08-29-unatco-repart-live-diff/harness/
repart_child_trace.py`): `bspRepartition(Model, iChild, 2)` entry is `Editor.dll 0x10049fc0`
(esp+4=Model, esp+8=iChild). `bspAddNode` entry is `Editor.dll 0x10034e80` (esp+4=Model,
esp+8=iParent, esp+0xc=ENodePlace, esp+0x14=FPoly* with Base@+0x00, iLink@+0x1c4, NumVertices@+0x1c0).
`bspBrushCSG` entry is `Editor.dll 0x100355e0` (esp+4=Actor, esp+8=Model).

Usage: repart_order_trace.py --trunk <N59-subset-dir> [--out log]
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OLD_HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
OLD_ORACLE = OLD_HARNESS / "editor-tree-oracle"
UNBUILT_HARNESS = ROOT / "dev/docs/spikes/2026-09-02-unbuilt-structure-parity/harness"
LADDER_HARNESS = ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness"
HERE = Path(__file__).resolve().parent
for p in (ROOT, OLD_HARNESS, OLD_ORACLE, UNBUILT_HARNESS, LADDER_HARNESS):
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

CONTAINER = "uned-repart-order-n59"
BASE_PREF = 0x10000000

REPART_ENTRY = 0x10049FC0
REPART_STAGEEND = 0x1004A05F
ADDNODE_ENTRY = 0x10034E80
BRUSHCSG_ENTRY = 0x100355E0

GDB_TMPL = r"""
set pagination off
set confirm off
set height 0
set width 0
attach {pid}
handle SIGSEGV nostop noprint pass
handle SIGUSR1 nostop noprint pass
handle SIGUSR2 nostop noprint pass
handle SIGPIPE nostop noprint pass
set $callidx = 0
set $first_add_done = 0
set $bcsg_idx = 0

break *{brushcsg}
commands
silent
set $bcsg_idx = $bcsg_idx + 1
printf "BRUSHCSG idx=%d actor=%#x model=%#x\n", $bcsg_idx, *(unsigned int *)($esp+4), *(unsigned int *)($esp+8)
continue
end

break *{repart}
commands
silent
set $callidx = $callidx + 1
set $first_add_done = 0
printf "CALL idx=%d model=%#x child=%d after_bcsg=%d\n", $callidx, *(unsigned int *)($esp+4), *(int *)($esp+8), $bcsg_idx
continue
end

break *{stageend}
commands
silent
printf "STAGEEND idx=%d\n", $callidx
continue
end

break *{addnode}
commands
silent
if $first_add_done == 0
  set $first_add_done = 1
  set $e = *(unsigned int *)($esp + 0x14)
  printf "ADD call=%d ilink=%d nv=%d base=%.4f,%.4f,%.4f\n", $callidx, *(int *)($e + 0x1c4), *(int *)($e + 0x1c0), *(float *)($e), *(float *)($e+4), *(float *)($e+8)
end
continue
end

printf "ORACLE_ATTACHED\n"
continue
"""


def main() -> int:
    trunk_dir = None
    out = HERE.parent / "logs" / "repart-order-n59.log"
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
    print(f"[repart-order] {trunk_dir.name}; starting {CONTAINER}", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        t3d_path = drv.write_work_file(emit_map(actors), ext="t3d")
        pid = O._editor_pid(CONTAINER)
        maps = subprocess.run(["docker", "exec", CONTAINER, "cat", f"/proc/{pid}/maps"],
                              capture_output=True, text=True, check=True).stdout
        editor_base = None
        for line in maps.splitlines():
            if "editor.dll" in line.lower():
                editor_base = int(line.split("-", 1)[0], 16)
                break
        if editor_base is None:
            raise RuntimeError("editor.dll not found in /proc/<pid>/maps")
        print(f"[repart-order] Editor.dll live base = {editor_base:#x}", flush=True)

        def remap(addr: int) -> int:
            return editor_base + (addr - BASE_PREF)

        script = GDB_TMPL.format(
            pid=pid,
            brushcsg=hex(remap(BRUSHCSG_ENTRY)),
            repart=hex(remap(REPART_ENTRY)),
            stageend=hex(remap(REPART_STAGEEND)),
            addnode=hex(remap(ADDNODE_ENTRY)),
        )
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/repartorder.gdb"],
                       input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/repartorder.gdb > /tmp/repartorder.log 2>&1"], check=True)
        for _ in range(240):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/repartorder.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[repart-order] attached; running the golden EXEC batch ...", flush=True)
        saved = "/work/repart_order_n59.dx"
        drv.begin_script()
        ensure_load(drv, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        drv.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        drv.exec("MAP REBUILD")
        drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
        try:
            drv.run_script(produces=saved, timeout=900.0)
        except Exception as ex:
            print(f"[repart-order] batch wait ended: {ex}", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        log_bytes = subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/repartorder.log"],
                                   capture_output=True).stdout
        out.write_bytes(log_bytes)
        print(f"[repart-order] wrote {out}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
