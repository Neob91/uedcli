#!/usr/bin/env python3
r"""5th-round NYC_Bar N=153 probe: capture EVERY live `URender::BoundVisible` box test
(`render.dll 0x100193d5`) during the golden `LIGHT APPLY` run on the N=153 subset, with full
geometry (light-frame origin, `FBox` min/max, verdict), so a specific native box test can be matched
by GEOMETRY (not raw node index -- this level's world `Model2` nodes are only a PERMUTATION match
between native and UED22, so index-based matching is unsound here; see the board item's "Fourth
round").

Round 4 found a native box-occlusion candidate at (native numbering) node 16, bound 0
(FBox min=(-3120,176,-16) max=(-3092,560,0)), rejected during Light5's -X face. Round 5's own
traversal-order analysis (log-only, no live capture) proved node 16 is NOT an ancestor of the three
divergent tread nodes (9/13/14/15/20/22/24 in native's numbering) -- it is an unrelated descendant
(the far child of node 13's coplanar chain), so its rejection cannot gate their acceptance. The real
common ancestor of all three divergent surfaces (95/97/67) in native's own tree is node 128
(iRenderBound=60, `FBox` min=(-3072,420,0) max=(-3068,512,132)), tested and ACCEPTED (`visible=true`)
by native's port for Light5's -X face. This probe checks whether the REAL editor's own BoundVisible
test for that SAME geometric box (light origin = Light5's, same view direction) says the opposite.

Usage: box_verdict_n153.py --trunk <subset-trunk-dir> [--out log]
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

CONTAINER = "uned-n153-box-verdict"
RENDER_PREF = 0x10000000
CALL_SITE = 0x100193D5   # `call eax` -- BoundVisible(Frame, &Box, &Span, &ScreenBounds)
AFTER_CALL = 0x100193D7  # `test eax, eax`
VERDICTS = {"geo": 0x100193DB, "zone": 0x10019526, "accept": 0x1001952F}


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
break *__CALL__
commands
silent
set $hits = $hits + 1
set $fr = *(unsigned int*)($esp)
set $box = *(unsigned int*)($esp+4)
printf "IN hit=%d frame=%#x\n", $hits, $fr
printf "BOX min=[%.9g,%.9g,%.9g] max=[%.9g,%.9g,%.9g] valid=%d\n", *(float*)$box, *(float*)($box+4), *(float*)($box+8), *(float*)($box+12), *(float*)($box+16), *(float*)($box+20), *(int*)($box+24)
printf "ORIGIN %.9g,%.9g,%.9g ZAXIS %.9g,%.9g,%.9g\n", *(float*)($fr+0x34), *(float*)($fr+0x38), *(float*)($fr+0x3c), *(float*)($fr+0x4c), *(float*)($fr+0x50), *(float*)($fr+0x54)
continue
end

__VERDICTBPS__
break *__AFTER__
commands
silent
printf "OUT hit=%d ret=%d\n", $hits, $eax
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
    out = HERE.parent / "logs" / "box-verdict-n153.log"
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
    print(f"[box-verdict-n153] {trunk_dir.name}; starting {CONTAINER}", flush=True)
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
        print(f"[box-verdict-n153] render.dll live base = {render_base:#x}", flush=True)
        script = (GDB_TEMPLATE
                  .replace("__PID__", str(pid))
                  .replace("__CALL__", hex(remap(CALL_SITE, render_base)))
                  .replace("__AFTER__", hex(remap(AFTER_CALL, render_base)))
                  .replace("__VERDICTBPS__", "\n".join(
                      f'break *{remap(a, render_base):#x}\ncommands\nsilent\n'
                      f'printf "VERDICT hit=%d path={tag}\\n", $hits\ncontinue\nend'
                      for tag, a in VERDICTS.items())))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/bvn153.gdb"],
                       input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/bvn153.gdb > /tmp/bvn153.log 2>&1"], check=True)
        for _ in range(240):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/bvn153.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[box-verdict-n153] attached; running the golden EXEC batch ...", flush=True)
        saved = "/work/probe_bvn153.dx"
        drv.begin_script()
        ensure_load(drv, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        drv.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        drv.exec("MAP REBUILD")
        drv.light_apply()
        drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
        try:
            drv.run_script(produces=saved, timeout=900.0)
        except Exception as ex:
            print(f"[box-verdict-n153] batch wait ended: {ex}", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        log_bytes = subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/bvn153.log"],
                                   capture_output=True).stdout
        out.write_bytes(f"render.dll live base = {render_base:#x}\n\n".encode() + log_bytes)
        print(f"[box-verdict-n153] wrote {out} ({len(log_bytes)} bytes)", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
