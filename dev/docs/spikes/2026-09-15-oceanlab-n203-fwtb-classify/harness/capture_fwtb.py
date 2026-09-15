#!/usr/bin/env python3
r"""Live-capture UED22's real `FilterWorldThroughBrush` (Editor.dll `0x33250`, `uned/UED22/Editor.dll`
-- ImageBase `0x10000000`, matching this campaign's `EDITOR_PREF` convention) CONSUME-vs-GRAZE verdict
for the OceanLab N=203 wall face, during `Brush482`'s (`CSG_Add`, world-CSG index `bi=166`) own
`bspBrushCSG`.

Continues `dev/docs/board/to-spike/oceanlab-n-203-world-model2-split-vertex-ulp/` and
`dev/docs/spikes/2026-09-15-oceanlab-n203-bspoptgeom-points/`. That session proved UED22 keeps the
wall face (native node 5154, plane bits `0x3f800000,0x80000000,0x80000000,0xc3800002`) ALIVE all the
way to `bspOptGeom` -- not a dead-node ghost -- and pinned the exact CSG step where native's own
`FilterWorldThroughBrush` (`bspcsg.rs`) kills it: `Brush482` (CSG_Add, bi=166), one brush before
`Brush483` itself. Native's `filter_one_world_node` decides `g_discarded != 0` (CONSUME) for this face
against `Brush482`'s temp BSP; the prior session's framing was that UED22's real answer must be the
opposite (GRAZE), since the face survives. This script reads UED22's own `GDiscarded` global directly,
at the exact reconciliation point, for the exact node/plane in question, to test that directly.

**RESULT (see `../spike.md`): the GRAZE hypothesis is REFUTED.** UED22's own `GDiscarded` is CONSUME
here too — the prior session's "keeps it ALIVE" read of the `bspOptGeom`-entry Points/Surfs dump only
checked presence in the `Surfs` array, not node liveness; the wall's surf is a dead-node surf on both
sides. The true divergence is elsewhere (see `spike.md` §3-4) — not in `FilterWorldThroughBrush`.

Method: same gdb-attach recipe as `2026-09-14-oceanlab-n203-addpoint-capture/harness/capture_addpoint.py`
and `2026-09-13-crossing-vertex-live-capture/harness/crossing_probe.py` (ptrace inside `dx-lum-uned-dbg`,
DLL bases read live and remapped from the `EDITOR_PREF=0x10000000` nominal addresses used throughout
this campaign's RE docs).

**No brush-ordinal counting needed.** Instead of trying to count `FilterWorldThroughBrush` top-level
calls to find "the 166th", this stages the SAME OceanLab N=203 subset truncated to N=202 -- verified
offline (`/tmp/dump_actors.py` this session) to place `Brush482` as the LAST actor (`Brush483` is
actor #203, excluded). Since `Brush482` is then the LAST CSG-participating brush processed by `MAP
REBUILD`, ANY breakpoint hit matching the wall's exact plane bits during this build is unambiguously
part of `Brush482`'s own `FilterWorthThroughBrush` recursion (no other brush's CSG step runs after it
to produce a same-plane hit). All matching hits are logged (there may be an earlier hit from `Brush481`,
bi=165, if the face also straddled that brush's sphere) -- the LAST one is `Brush482`'s own verdict.

Breakpoint: Editor.dll (nominal VA, `EDITOR_PREF=0x10000000`) `0x1003348b` -- inside
`FilterWorldThroughBrush`, the `cmp DWORD PTR ds:GDiscarded,0` instruction immediately after the
`bspFilterFPoly` call returns (call at `0x10033483`, return at `0x10033488`), confirmed by objdump
disassembly of `uned/UED22/Editor.dll` this session (byte-exact match to the campaign's prior decode
in `dev/docs/spikes/2026-07-15-native-materialize/re-raw-zones/bspbrushcsg-filter-decode.md` §5). At
that address, the engine globals hold this reconciliation's final state:

  GNode      @ 0x101491bc  (int)    -- the world node index being reconciled (unclobbered since entry)
  GModel     @ 0x101491c8  (ptr)    -- the world UModel* (== the reconciliation's own Model arg)
  GDiscarded @ 0x101491b8  (int)    -- >0 == CONSUME (kept re-adds, deleted original);
                                        ==0 == GRAZE (rolled re-adds back, kept original)

The node's own plane is read via `*(Model+0x58)` (`UModel::Nodes.Data`, stride `0x40`/`FBspNode`,
`Plane`@+0x00 -- 4 floats X,Y,Z,W) `+ GNode*0x40`, reusing the `Model*`/`UModel` layout RE'd by the
`2026-09-15-oceanlab-n203-bspoptgeom-points` session (cross-verified against `zones.rs`'s own
disassembly comment and this session's own objdump pass).

Usage: capture_fwtb.py [--out logs/capture.log]
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
NATIVE_MAT_HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
ORACLE_DIR = NATIVE_MAT_HARNESS / "editor-tree-oracle"
ACTOR_PARITY_HARNESS = ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness"
UNBUILT_HARNESS = ROOT / "dev/docs/spikes/2026-09-02-unbuilt-structure-parity/harness"
HERE = Path(__file__).resolve().parent
for p in (ROOT, NATIVE_MAT_HARNESS, ORACLE_DIR, ACTOR_PARITY_HARNESS, UNBUILT_HARNESS):
    sys.path.insert(0, str(p))

import editor_tree_oracle as O  # noqa: E402
import actor_parity as ap  # noqa: E402
from uedcli import config, trunk  # noqa: E402
from uedcli.apply import _level_referenced_packages  # noqa: E402
from uedcli.classindex import ClassIndex  # noqa: E402
from uedcli.container_assets import resource_mounts  # noqa: E402
from uedcli.driver import Driver, to_z_path  # noqa: E402
from uedcli.emit import emit_map  # noqa: E402
from uedcli.materialize import levelinfo_first_order  # noqa: E402
from uedcli.movers import set_base_pose  # noqa: E402
from uedcli.packages import editor_search_dirs, ensure_load  # noqa: E402
from build_ued_import_built_golden import _dummy_builder_actor  # noqa: E402
from build_ued_import_golden import _quote_str_props  # noqa: E402
from build_ued_golden import _scratch_project  # noqa: E402

CONTAINER = "uned-oceanlab-n203-fwtb"
EDITOR_PREF = 0x10000000

# `FilterWorldThroughBrush`'s reconciliation `cmp GDiscarded,0` (Editor.dll nominal VA; confirmed by
# objdump of `uned/UED22/Editor.dll` this session -- byte-exact to the campaign's 2026-07-15 decode).
FWTB_RECONCILE_VA = 0x1003348B

G_NODE = 0x101491BC
G_MODEL = 0x101491C8
G_DISCARDED = 0x101491B8

# The wall face's exact plane bits (x=1.0, y=-0.0, z=-0.0, w=-256.00006103515625), pinned by the prior
# `2026-09-15-oceanlab-n203-bspoptgeom-points` session's offline `UEDCLI_BSPCSG_BRUSH_STATE` trace.
WALL_PLANE_X = 0x3F800000
WALL_PLANE_Y = 0x80000000
WALL_PLANE_Z = 0x80000000
WALL_PLANE_W = 0xC3800002

DX_PATH = Path("/workspace/uedcli/dev/games/substrate-deusex/Maps/14_OceanLab_Lab.dx")
# N=202: Brush482 (bi=166) is the LAST actor -- Brush483 (bi=167, N=203) deliberately excluded, per
# this spike's own docstring (verified offline this session: actors 177..202 are consecutive brushes
# Brush453.. through Brush482, Brush483 is actor #203).
N = 202


def remap(addr: int, live_base: int, pref: int) -> int:
    return live_base + (addr - pref)


def _find_dll_base(container: str, pid: int, dll: str) -> int:
    maps = subprocess.run(["docker", "exec", container, "cat", f"/proc/{pid}/maps"],
                          capture_output=True, text=True, check=True).stdout
    for line in maps.splitlines():
        if dll.lower() in line.lower():
            return int(line.split("-", 1)[0], 16)
    raise RuntimeError(f"{dll} not found")


GDB_SCRIPT = f"""
set pagination off
set confirm off
set height 0
set width 0
attach {{pid}}
handle SIGSEGV nostop noprint pass
handle SIGUSR1 nostop noprint pass
handle SIGUSR2 nostop noprint pass
handle SIGPIPE nostop noprint pass
set $hits = 0

break *{{va:#x}}
commands
silent
set $hits = $hits + 1
set $gm = *(unsigned int*)({G_MODEL:#x})
set $gn = *(unsigned int*)({G_NODE:#x})
set $nodesdata = *(unsigned int*)($gm+0x58)
set $nd = $nodesdata + $gn*0x40
set $px = *(unsigned int*)($nd+0x0)
set $py = *(unsigned int*)($nd+0x4)
set $pz = *(unsigned int*)($nd+0x8)
set $pw = *(unsigned int*)($nd+0xc)
if $px == {WALL_PLANE_X:#x} && $py == {WALL_PLANE_Y:#x} && $pz == {WALL_PLANE_Z:#x} && $pw == {WALL_PLANE_W:#x}
set $gd = *(unsigned int*)({G_DISCARDED:#x})
printf "FWTB hit=%d gNode=%d gModel=%08x plane=(%08x,%08x,%08x,%08x) GDiscarded=%d verdict=%s\\n", \
  $hits, $gn, $gm, $px, $py, $pz, $pw, $gd, ($gd != 0 ? "CONSUME" : "GRAZE")
end
continue
end

printf "ORACLE_ATTACHED\\n"
continue
"""


def main() -> int:
    out = HERE.parent / "logs" / "capture.log"
    for i, a in enumerate(sys.argv):
        if a == "--out":
            out = Path(sys.argv[i + 1]).resolve()

    full_trunk, name = ap._resolve_trunk(DX_PATH, "deusex")
    subset = ap.make_subset(full_trunk, name, N)
    project = _scratch_project(subset, "deusex")
    user_config = config.load_user_config()
    search_dirs = config.composed_search_dirs(project, user_config)
    mounts = resource_mounts(search_dirs)
    host_search_dirs = editor_search_dirs(search_dirs)

    lvl, _ = trunk.read_level(subset)
    class_idx = ClassIndex.from_files([(f.stem, str(f)) for d in host_search_dirs
                                       for f in sorted(Path(d).glob("*.u"))])
    for an in lvl.order:
        set_base_pose(lvl.actors[an], class_idx)
    classes = {n: lvl.actors[n].cls for n in lvl.order}
    has_brush = {n: lvl.actors[n].brush is not None for n in lvl.order}
    imp_order = levelinfo_first_order(lvl.order, classes, has_brush)
    _quote_str_props(lvl, imp_order, project, user_config)
    actors = [lvl.actors[n] for n in imp_order]
    actors.insert(1, _dummy_builder_actor())
    ref_pkgs = _level_referenced_packages(
        type("L", (), {"actors": {n: lvl.actors[n] for n in imp_order}})())

    assert imp_order[-1] == "Brush482" or lvl.order[-1] == "Brush482", (
        f"expected Brush482 as the last actor at N={N}, got {lvl.order[-1]!r}")

    O._ensure_dbg_image()
    state_dir = config.state_dir(project.root, create=True)
    O.stop_dbg_editor(CONTAINER, state_dir)
    print(f"[capture] OceanLab N={N} (Brush482 last, bi=166); starting {CONTAINER}", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        t3d_path = drv.write_work_file(emit_map(actors), ext="t3d")
        pid = O._editor_pid(CONTAINER)
        editor_base = _find_dll_base(CONTAINER, pid, "editor.dll")
        print(f"[capture] editor pid={pid} Editor.dll live base={editor_base:#x}", flush=True)
        va = remap(FWTB_RECONCILE_VA, editor_base, EDITOR_PREF)
        script = GDB_SCRIPT.format(pid=pid, va=va)
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c",
                        "cat > /tmp/fwtb.gdb"], input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/fwtb.gdb > /tmp/fwtb.log 2>&1"], check=True)
        for _ in range(120):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/fwtb.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            diag = subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/fwtb.log"],
                                  capture_output=True, text=True).stdout
            raise RuntimeError(f"gdb did not attach. log:\n{diag[:3000]}")
        print("[capture] gdb attached; running MAP IMPORT + MAP REBUILD ...", flush=True)
        saved = "/work/probe_n202_fwtb.dx"
        drv.begin_script()
        ensure_load(drv, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        drv.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        drv.exec("MAP REBUILD")
        drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
        try:
            drv.run_script(produces=saved, timeout=1800.0)
        except Exception as ex:  # noqa: BLE001
            print(f"[capture] batch wait ended: {ex}", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        log_bytes = subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/fwtb.log"],
                                   capture_output=True).stdout
        out.write_bytes(
            f"Editor.dll live base = {editor_base:#x}  VA = {va:#x}\n\n".encode() + log_bytes)
        print(f"[capture] wrote {out}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
