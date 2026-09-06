#!/usr/bin/env python3
r"""Live GDB capture: every `bspAddVector` call UED22 makes while building a subset trunk.

Island N=6's world `Model2` Vectors pool puts `Brush1353`'s oblique-face normal at index 8, where
native (which rebuilds the pool by walking the canonical Surfs order) puts it at 16. `bspAddVector`
is `Editor.dll 0x10035530` and is VIRTUAL, so a static `E8` scan finds no callers; a runtime
breakpoint at its entry reads the caller off `[esp]` instead and settles the question directly.

Per `bspAddVector` hit it logs: the return address (the real call site), the `UModel*`, the
`FVector` argument, the `Exact` flag, and `Model->Vectors.Num()`/`Model->Surfs.Num()` before the
call; the `ret 0xc` at `0x100355a7` then logs the returned pool index. Phase/segment markers break
at `csgRebuild`, `bspBrushCSG`, `bspBuild`, `bspRepartition`, `bspRefresh`, `bspMergeCoplanars`,
`bspOptGeom`, `TestVisibility` and `bspAddNode`, so each vector proposal can be attributed to a
brush and a build stage.

Offsets decoded from `bspAddNode`'s surf-allocation block (`0x10034f06`-`0x10034f74`):
`UModel::Vectors` = `Model+0x78` (Num at `+0x7c`), `UModel::Surfs` = `Model+0x98` (Num at `+0x9c`),
`FPoly::Normal` = `+0x0c`, `TextureU` = `+0x18`, `TextureV` = `+0x24`.

Usage: addvector_call_trace.py --trunk <subset-trunk-dir> [--out log]
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

CONTAINER = "uned-addvector-trace"
EDITOR_PREF = 0x10000000
ADDVECTOR = 0x10035530
ADDVECTOR_RET = 0x100355A7
# Phase markers: one breakpoint each at the function entry, printed with no argument decoding.
MARKS = {
    "csgRebuild": 0x1004A650,
    "bspBrushCSG": 0x100355E0,
    "bspBuild": 0x10035EF0,
    "bspRepartition": 0x10049FC0,
    "bspRefresh": 0x10036CD0,
    "bspMergeCoplanars": 0x10036200,
    "bspCleanup": 0x10036160,
    "bspOptGeom": 0x10036870,
    "TestVisibility": 0x100AA940,
    "csgPrepMovingBrush": 0x1004A4F0,
}
ADDNODE = 0x10034E80

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

set $n = 0
break *__ADDVEC__
commands
silent
set $n = $n + 1
set $ret = *(unsigned int*)($esp)
set $m = *(unsigned int*)($esp+4)
set $v = *(unsigned int*)($esp+8)
set $ex = *(unsigned int*)($esp+0xc)
printf "AV n=%d ret=%#x model=%#x exact=%d v=(%.9g,%.9g,%.9g) nvec=%d nsurf=%d\n", $n, $ret, $m, $ex, *(float*)$v, *(float*)($v+4), *(float*)($v+8), *(int*)($m+0x7c), *(int*)($m+0x9c)
continue
end

break *__ADDVECRET__
commands
silent
printf "AVR n=%d idx=%d\n", $n, $eax
continue
end

break *__ADDNODE__
commands
silent
set $m2 = *(unsigned int*)($esp+4)
set $ep = *(unsigned int*)($esp+0x14)
printf "AN model=%#x iparent=%d place=%d nf=%#x edpoly=%#x N=(%.9g,%.9g,%.9g) nsurf=%d ilink=%d\n", $m2, *(int*)($esp+8), *(int*)($esp+0xc), *(unsigned int*)($esp+0x10), $ep, *(float*)($ep+0xc), *(float*)($ep+0x10), *(float*)($ep+0x14), *(int*)($m2+0x9c), 0
continue
end

__MARKBPS__
printf "ORACLE_ATTACHED\n"
continue
"""


def _find_editor_base(container: str, pid: int) -> int:
    maps = subprocess.run(["docker", "exec", container, "cat", f"/proc/{pid}/maps"],
                          capture_output=True, text=True, check=True).stdout
    bases = [int(line.split("-", 1)[0], 16) for line in maps.splitlines()
             if "editor.dll" in line.lower()]
    if not bases:
        raise RuntimeError("Editor.dll not found in /proc/<pid>/maps")
    return min(bases)


def main() -> int:
    trunk_dir = None
    out = HERE.parent / "logs" / "addvector-call-trace.log"
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
    print(f"[av] import order: {imp_order[:1] + ['<dummy builder>'] + imp_order[1:]}", flush=True)
    ref_pkgs = _level_referenced_packages(
        type("L", (), {"actors": {n: lvl.actors[n] for n in imp_order}})())

    O._ensure_dbg_image()
    state_dir = config.state_dir(project.root, create=True)
    O.stop_dbg_editor(CONTAINER, state_dir)
    print(f"[av] {trunk_dir.name}; starting {CONTAINER}", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        t3d_path = drv.write_work_file(emit_map(actors), ext="t3d")
        pid = O._editor_pid(CONTAINER)
        eb = _find_editor_base(CONTAINER, pid)
        print(f"[av] Editor.dll live base = {eb:#x}", flush=True)

        def rm(a: int) -> int:
            return eb + (a - EDITOR_PREF)

        marks = "\n".join(
            f'break *{rm(a):#x}\ncommands\nsilent\nprintf "MARK {tag}\\n"\ncontinue\nend'
            for tag, a in MARKS.items())
        script = (GDB_TEMPLATE
                  .replace("__PID__", str(pid))
                  .replace("__ADDVECRET__", hex(rm(ADDVECTOR_RET)))
                  .replace("__ADDVEC__", hex(rm(ADDVECTOR)))
                  .replace("__ADDNODE__", hex(rm(ADDNODE)))
                  .replace("__MARKBPS__", marks))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/av.gdb"],
                       input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/av.gdb > /tmp/av.log 2>&1"], check=True)
        for _ in range(240):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/av.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[av] attached; running the golden EXEC batch ...", flush=True)
        saved = "/work/probe_av.dx"
        drv.begin_script()
        ensure_load(drv, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        drv.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        drv.exec("MAP REBUILD")
        drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
        try:
            drv.run_script(produces=saved, timeout=1800.0)
        except Exception as ex:
            print(f"[av] batch wait ended: {ex}", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        log_bytes = subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/av.log"],
                                   capture_output=True).stdout
        out.write_bytes(f"Editor.dll live base = {eb:#x}\n\n".encode() + log_bytes)
        print(f"[av] wrote {out} ({len(log_bytes)} bytes)", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
