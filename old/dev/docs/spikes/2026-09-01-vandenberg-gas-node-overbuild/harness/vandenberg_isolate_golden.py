#!/usr/bin/env python3
"""Isolated live-editor golden for Brush54 of `12_Vandenberg_Gas.dx` -- same isolate-in-a-fresh-
MAP-NEW technique as `oceanlab_isolate_golden.py`, adapted for a SUBTRACT brush: the world is
solid by default (`dev/docs/unrealed/quirks.md` "CSG model"), so a lone CSG_Subtract brush needs
only an ADD shell around it (no separate SUBTRACT room) to have real solid space to carve out of.

Brush54 is the dominant outlier in the per-brush node/surf attribution for Vandenberg Gas's
residual (nodes native=11289 golden=10683 d=+606; surfs d=+2 but Brush54 alone is native=181
editor=71 d=+110, and node-plane-owner native=1373 editor=472 d=+901 -- both far larger than the
level's own net delta, meaning other brushes cancel). Brush54: CSG_Subtract, 412 polys,
MainScale=(1.243502,1.243502,1.243502) uniform, PostScale=(1.393913,1.149680,1.158020)
non-uniform, no Rotation (identity), no mirror (all-positive scale components) -- ruling out the
already-fixed `c7b8b0b` mirrored-brush determinant bug. World bbox extent ~7488x7663x2650uu,
center ~(-448,-474,-251).

Usage: .venv/bin/python vandenberg_isolate_golden.py
Run as a bounded background job -- the editor wedges silently (dev/docs/rules/background-work.md).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path("/workspace/uedcli/.claude/worktrees/vandenberg-gas-parity")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness"))

from uedcli import config, trunk, writes, xfer                     # noqa: E402
from uedcli.container_assets import resource_mounts                # noqa: E402
from uedcli.driver import Driver                                   # noqa: E402
from uedcli.editor import ensure_editor, stop_editor                # noqa: E402
from uedcli.uuid7 import uuid7                                     # noqa: E402
from uedcli import builders                                        # noqa: E402
import build_ued_golden as bg                                      # noqa: E402
from geo_golden_driver import _wait_idle                           # noqa: E402

TRUNK = (ROOT / "_scratch/uedcli-parity-cache/"
         "7d06dd6155e5daa7c78e76ed19a66068852973670d1c56dddd9628b2ca393c13/trunk/maps/12_vandenberg_gas")
OUT_DIR = ROOT / "_scratch/vandenberg-isolate"


def _context_shell(center, size=20000):
    """A single ADD shell around `center` -- the world is solid by default, so this alone gives a
    lone CSG_Subtract brush real solid space to carve out of (no separate SUBTRACT room needed,
    unlike the OceanLab additive-brush case)."""
    cx, cy, cz = center
    return [builders.make_brush_actor(
        "CtxShell", builders.cube(size, size, size), location=(cx, cy, cz), csg="add")]


def main() -> int:
    names = sys.argv[1:] or ["Brush54"]
    out = OUT_DIR / f"golden_{'_'.join(names)}.dx"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    lvl, _ranks = trunk.read_level(TRUNK)
    brush_actors = [lvl.actors[n] for n in names]
    lo, hi = writes.actor_bounds(brush_actors[0])
    center = (float((lo[0] + hi[0]) / 2), float((lo[1] + hi[1]) / 2), float((lo[2] + hi[2]) / 2))
    ctx = _context_shell(center)
    brush_actors = ctx + brush_actors

    user_config = config.load_user_config()
    project = bg._scratch_project(TRUNK, "deusex")
    search_dirs = config.composed_search_dirs(project, user_config)
    mounts = resource_mounts(search_dirs)
    state_dir = config.state_dir(project.root, create=True)

    ed_id = uuid7()
    container = ensure_editor(ed_id, mounts=mounts, state_dir=state_dir)
    ed = Driver(container=container)
    try:
        print(f"editor up: {container}", flush=True)
        ed.map_new()
        _wait_idle(container, label="map-new")
        ed.set_grid(1, 1, 1)
        t3d = writes.emit_map([writes._shift_for_paste(a) for a in brush_actors])
        ed.set_clipboard(t3d)
        ed.edit_paste()
        _wait_idle(container, label="paste")
        print("  pasted, MAP REBUILD ...", flush=True)
        ed.exec("MAP REBUILD")
        _wait_idle(container, label="rebuild", timeout=600, quiet_reads=8, min_seconds=5)
        work_out = xfer.work_path("dx")
        size = ed.map_save(work_out)
        xfer.cp_out(container, work_out, str(out))
        print(f"WROTE {out} ({size} bytes container-side, {out.stat().st_size} host-side)",
              flush=True)
    finally:
        try:
            stop_editor(ed_id, state_dir)
        except Exception as e:
            print(f"teardown note: {e}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
