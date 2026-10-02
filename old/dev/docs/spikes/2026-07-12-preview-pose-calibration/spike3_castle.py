#!/usr/bin/env python3
"""Spike 3: validate the auto-frame fix on the REAL castle + settle the 'overview' target.

spike2 proved `CAMERA ALIGN NAME=<brush>` frames that brush (render reflects it), distance ∝ size.
This confirms it on the actual castle trunk and answers: what target gives a good WHOLE-CASTLE
overview? Candidates:
  A) World_* (the room SUBTRACT — solid is OUTSIDE, so framing it may land the camera in the void)
  B) a VISIBLE nonsolid marker cube spanning the castle bbox (may OCCLUDE the castle)
  C) an INVISIBLE marker (PolyFlags=PF_Invisible=0x1) spanning the bbox (best if it renders nothing)

Targets framed: Keep, TowerNE (core detail shots) + the three overview candidates.
Run: bash -c 'source bin/_dev-run.sh && dev_docker_run python3 <this>.py'
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # Tools/uedcli

from uedcli import builders, writes                           # noqa: E402
from uedcli.apply import _materialize, _materialized_order    # noqa: E402
from uedcli.cli.level_sources import TrunkLevelSource                  # noqa: E402
from uedcli.driver import Driver                              # noqa: E402
from uedcli.editor import ensure_editor, stop_editor          # noqa: E402
from uedcli.normalize import canonical_actor_t3d              # noqa: E402
from uedcli.preview_render import (CLICK, CROP, _WMCTRL_SWEEP,  # noqa: E402
                                   _ini_for_mode)
from uedcli.uuid7 import uuid7                                 # noqa: E402

LEVEL_DIR = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/castle/uedcli/maps/foobar")
OUT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/preview-castle-frame")
TEX = "LUM_CoreTex.grey_stone_tile"
PF_INVISIBLE = 0x00000001
# castle bbox (measured): center (0,0,168), size 435x435x336
MARK_AT = (0, 0, 168)
MARK_SIZE = (435, 435, 336)


def log(*a):
    print("[castle-frame]", *a, flush=True)


def shoot(drv, out_png: Path):
    from PIL import Image
    drv.exec("ACTOR SELECT NONE")
    drv.dexec_bash(_WMCTRL_SWEEP)
    drv.click(*CLICK)
    tmp = str(out_png) + ".full.png"
    drv.screenshot(tmp)
    Image.open(tmp).convert("RGB").crop(CROP).save(out_png)
    Path(tmp).unlink(missing_ok=True)


def frame_actor(drv, name, out_png: Path):
    drv.selectname(name)
    drv.camera_align(name=name)
    shoot(drv, out_png)


def frame_marker(drv, level, tag, poly_flags, out_png: Path):
    """Add a transient marker brush spanning the castle bbox, align to it, screenshot, delete."""
    name = writes.allocate_name(level, "FrameMark")
    brush = builders.cube(*MARK_SIZE, TEX, flags=poly_flags)
    marker = builders.make_brush_actor(name, brush, location=MARK_AT, csg="add",
                                       poly_flags=poly_flags)
    writes.add_actor(drv, marker, level)
    drv.selectname(name)
    drv.camera_align(name=name)
    shoot(drv, out_png)
    drv.selectname(name)
    drv.actor_delete()
    level.actors.pop(name, None)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    level = TrunkLevelSource(LEVEL_DIR).load()
    log(f"loaded castle: {len(level.actors)} actors")
    ed_id = uuid7()
    try:
        drv = Driver(container=ensure_editor(ed_id, ini_overrides=_ini_for_mode("shaded")))
        result = {n: canonical_actor_t3d(a) for n, a in level.actors.items()}
        mo = _materialized_order(result, level.order)
        log("materializing castle...")
        _materialize(drv, result=result, materialized_order=mo, packages=["Engine"])
        drv.dexec_bash(_WMCTRL_SWEEP)

        log("frame Keep_8ghqei"); frame_actor(drv, "Keep_8ghqei", OUT / "frame_keep.png")
        log("frame TowerNE_1f5drh"); frame_actor(drv, "TowerNE_1f5drh", OUT / "frame_tower.png")
        log("frame World_7e9y81 (overview A)"); frame_actor(drv, "World_7e9y81", OUT / "over_world.png")
        log("frame VISIBLE marker (overview B)")
        frame_marker(drv, level, "vis", 0, OUT / "over_marker_visible.png")
        log("frame INVISIBLE marker (overview C)")
        frame_marker(drv, level, "inv", PF_INVISIBLE, OUT / "over_marker_invisible.png")
        log("DONE ->", OUT)
        return 0
    finally:
        stop_editor(ed_id)


if __name__ == "__main__":
    sys.exit(main())
