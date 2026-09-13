#!/usr/bin/env python3
r"""Live-capture `FPoly::SplitWithPlaneFast`'s call site inside `ActorVisibility`'s beam-clip loop
(`Editor.dll 0x100a7152`, decoded in `dev/docs/spikes/2026-07-15-native-materialize/re-raw-zones/
lightflood-6d00.md`) -- for the WanChai N=58 leaf-51 investigation
(`dev/docs/board/inbox/wanchai-n58-leaf-51-permeating-light-over-included/`).

The board item's `perm_flood_diff.py`/`leaf_perm_diff.py` localised the divergence to one beam-clip
test: native's `clip_beam` accepts the `55->56` portal quad against the WIDE beam that entered leaf
55 via `45->55` (keeping the near-y=-512 half), while the live editor's own recursion shows NO
`55->56` crossing at all for that entry (`actor_visibility_probe.py`'s `AV_REC` never fires for it).
This probe reads the live editor's OWN `SplitWithPlaneFast` return value + the `Front` poly it
computes for every beam-clip edge test during the whole `MAP REBUILD`, to see directly whether the
editor's classification (`SP_Back`/`SP_Front`/`SP_Split`) differs from native's for this exact edge,
rather than inferring it from the absence of a recursive call.

Breaks at `0x100a7158` (right after `call [0x100cee30]`, before `cmp eax,2`) -- ActorVisibility's OWN
frame, so its locals are at FIXED ebp offsets (`lightflood-6d00.md`):
  Actor       = *(ebp+8)                         -- Location at Actor+0xd0/+0xd4/+0xd8
  Poly (IN)   = ebp-0x1ec                         -- NumVertices at +0x1c0 -> [ebp-0x2c]
  Front (OUT) = ebp-0x3c4  (only valid if eax==3) -- NumVertices at +0x1c0 -> [ebp-0x204]
  eax         = SplitWithPlaneFast's result (0/1 fall through, 2 = SP_Back, 3 = SP_Split->Front)

Usage: split_fast_probe.py --trunk <subset-trunk-dir> [--out log]
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

CONTAINER = "uned-splitfast-probe"
EDITOR_PREF = 0x10000000
SITE = 0x100A7158  # right after `call [0x100cee30]` (SplitWithPlaneFast), before `cmp eax,2`


def remap(addr: int, live_base: int) -> int:
    return live_base + (addr - EDITOR_PREF)


def _poly_printf(name: str, base: str, n: int) -> str:
    fmt = " ".join("[%.9g,%.9g,%.9g]" for _ in range(n))
    args = ", ".join(f"*(float*)({base}+0x30+{12 * i + 4 * k})" for i in range(n) for k in range(3))
    return f'printf " {name}_nv=%d {name}_v={fmt}\\n", *(int*)({base}+0x1c0), {args}'


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

break *__SITE__
commands
silent
set $act = *(unsigned int*)($ebp+8)
set $poly = $ebp-0x1ec
set $front = $ebp-0x3c4
printf "SPF act=[%.9g,%.9g,%.9g] eax=%d\n", *(float*)($act+0xd0), *(float*)($act+0xd4), *(float*)($act+0xd8), $eax
__POLYVERTS__
__FRONTVERTS__
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def main() -> int:
    trunk_dir = None
    out = HERE.parent / "logs" / "split-fast.log"
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
    print(f"[splitfast] {trunk_dir.name}; starting {CONTAINER}", flush=True)
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
            raise RuntimeError("Editor.dll not found")
        print(f"[splitfast] Editor.dll live base = {editor_base:#x}", flush=True)
        script = (GDB_TEMPLATE
                  .replace("__PID__", str(pid))
                  .replace("__SITE__", hex(remap(SITE, editor_base)))
                  .replace("__POLYVERTS__", _poly_printf("poly", "$poly", 5))
                  .replace("__FRONTVERTS__", _poly_printf("front", "$front", 5)))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/sfp.gdb"],
                       input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/sfp.gdb > /tmp/sfp.log 2>&1"], check=True)
        for _ in range(240):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/sfp.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[splitfast] attached; running the golden EXEC batch ...", flush=True)
        saved = "/work/probe_sfp.dx"
        drv.begin_script()
        ensure_load(drv, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        drv.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        drv.exec("MAP REBUILD")
        drv.light_apply()
        drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
        try:
            drv.run_script(produces=saved, timeout=900.0)
        except Exception as ex:
            print(f"[splitfast] batch wait ended: {ex}", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        log_bytes = subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/sfp.log"],
                                   capture_output=True).stdout
        out.write_bytes(f"Editor.dll live base = {editor_base:#x}\n\n".encode() + log_bytes)
        print(f"[splitfast] wrote {out}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
