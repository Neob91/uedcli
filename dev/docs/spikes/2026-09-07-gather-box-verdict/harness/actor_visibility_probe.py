#!/usr/bin/env python3
r"""Capture `FEditorVisibility::ActorVisibility`'s recursion, live — the per-leaf permeating-light
flood that decides `Model.Lights` region 1.

`Editor.dll 0x100a6d00`, `__thiscall`, `ret 0xc` — three args, read out of the prologue:

  [ebp+0x08]  AActor* Actor      (Location at +0xd0)
  [ebp+0x0c]  INT     iLeaf      -1 = seed: descend the BSP from Actor->Location instead
  [ebp+0x10]  FPoly*  ClipPoly   NULL on the seed call; the beam remnant otherwise

`[ebp-0x5b0]` holds the RESOLVED leaf on both paths (`0x100a6d45` for a recursive entry,
`0x100a6dcc` after the seed descent). This probe breaks at `0x100a6edd`, on the shared path past
both, and dumps the actor's Location, the leaf, and the clip polygon (`NumVertices` at `FPoly+0x1c0`
in this build, `Vertex[]` at `+0x30`) — enough to diff hop for hop against native's
`UEDCLI_PERM_TRACE` log and find the crossing native keeps that the editor drops.

The flood runs during MAP REBUILD (`csgRebuild -> TestVisibility -> Portalize`), not LIGHT APPLY, so
the breakpoints are armed for the whole batch.

Usage: actor_visibility_probe.py --trunk <subset-trunk-dir> [--out log] [--verts N]

Same relocation handling as its siblings, except that `Editor.dll` DOES keep its preferred
`0x10000000` base under Wine — it is `render.dll` that gets relocated — so the addresses are used
as-is after a check.
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

CONTAINER = "uned-actorvis-probe"
EDITOR_PREF = 0x10000000
# `0x100a6edd` is the convergence point of the seed descent (`0x100a6dd5 jne`) and a recursive
# entry, with `esi` = the resolved leaf and `edx` = the Actor.
ENTRY = 0x100A6EDD
# `0x100a6f01` allocates the (Actor, next) mark node -- reached only when this leaf's list does not
# already carry this actor, i.e. exactly native's `seen.insert` branch.
MARK = 0x100A6F01
# The recursive call: args already pushed, so `[esp]` = Actor, `[esp+4]` = target leaf,
# `[esp+8]` = the clipped beam `FPoly*` (NumVertices at +0x1c0, Vertex[] at +0x30).
RECURSE = 0x100A71C3


def remap(addr: int, live_base: int) -> int:
    return live_base + (addr - EDITOR_PREF)


def _vertex_printf(base: str, n: int) -> str:
    """A gdb `printf` of the first `n` FPoly vertices — a fixed count keeps the command list flat
    (no `while`), and the parser truncates to NumVertices."""
    fmt = " ".join("[%.9g,%.9g,%.9g]" for _ in range(n))
    args = ", ".join(f"*(float*)({base}+0x30+{12 * i + 4 * k})"
                     for i in range(n) for k in range(3))
    return f'printf " v={fmt}\\n", {args}'


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

break *__ENTRY__
commands
silent
set $act = *(unsigned int*)($ebp+8)
printf "AV leaf=%d loc=[%.9g,%.9g,%.9g] clip=%#x\n", $esi, *(float*)($act+0xd0), *(float*)($act+0xd4), *(float*)($act+0xd8), *(unsigned int*)($ebp+0x10)
continue
end

break *__MARK__
commands
silent
printf "AV_MARK leaf=%d\n", $esi
continue
end

break *__RECURSE__
commands
silent
set $cp = *(unsigned int*)($esp+8)
printf "AV_REC from=%d to=%d nv=%d\n", *(int*)($ebp-0x5b0), *(int*)($esp+4), *(int*)($cp+0x1c0)
__RECVERTS__
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def _find_editor_base(container: str, pid: int) -> int:
    maps = subprocess.run(["docker", "exec", container, "cat", f"/proc/{pid}/maps"],
                          capture_output=True, text=True, check=True).stdout
    for line in maps.splitlines():
        if "editor.dll" in line.lower():
            return int(line.split("-", 1)[0], 16)
    raise RuntimeError("Editor.dll not found")


def main() -> int:
    trunk_dir = None
    verts = 8
    out = HERE.parent / "logs" / "actor-visibility.log"
    for i, a in enumerate(sys.argv):
        if a == "--trunk":
            trunk_dir = Path(sys.argv[i + 1]).resolve()
        if a == "--out":
            out = Path(sys.argv[i + 1]).resolve()
        if a == "--verts":
            verts = int(sys.argv[i + 1])
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
    print(f"[actorvis] {trunk_dir.name}; starting {CONTAINER}", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        t3d_path = drv.write_work_file(emit_map(actors), ext="t3d")
        pid = O._editor_pid(CONTAINER)
        editor_base = _find_editor_base(CONTAINER, pid)
        print(f"[actorvis] Editor.dll live base = {editor_base:#x}", flush=True)
        script = (GDB_TEMPLATE
                  .replace("__PID__", str(pid))
                  .replace("__ENTRY__", hex(remap(ENTRY, editor_base)))
                  .replace("__MARK__", hex(remap(MARK, editor_base)))
                  .replace("__RECURSE__", hex(remap(RECURSE, editor_base)))
                  .replace("__RECVERTS__", _vertex_printf("$cp", verts)))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/avp.gdb"],
                       input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/avp.gdb > /tmp/avp.log 2>&1"], check=True)
        for _ in range(240):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/avp.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[actorvis] attached; running the golden EXEC batch ...", flush=True)
        saved = "/work/probe_avp.dx"
        drv.begin_script()
        ensure_load(drv, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        drv.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        drv.exec("MAP REBUILD")
        drv.light_apply()
        drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
        try:
            drv.run_script(produces=saved, timeout=900.0)
        except Exception as ex:
            print(f"[actorvis] batch wait ended: {ex}", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        log_bytes = subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/avp.log"],
                                   capture_output=True).stdout
        out.write_bytes(f"Editor.dll live base = {editor_base:#x}\n\n".encode() + log_bytes)
        print(f"[actorvis] wrote {out}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
