#!/usr/bin/env python3
"""Spike 4: can the brush-auto-frame ANGLE be steered by pre-positioning the camera?

Follow-up to the finding that `CAMERA ALIGN NAME=<brush>` reframes the render (spike2/3) but from a
seemingly canonical angle. The untested lead (spike.md "Consequence"): **point-align to set the camera
POSITION, then brush-align to a target to set the AIM** — if the brush-align frames the target FROM the
camera's current position, we get arbitrary vantage back; if it snaps to a fixed world direction,
canonical-only stands.

Test: an asymmetric scene with a CENTER target pillar to brush-align to, and distinct directional
landmarks around it (East=1 pillar, North=2, West=3, South=a wide wall). Brush-align to Center from
several pre-positions; read which directional landmark sits BEHIND Center:
  pre-pos WEST  → if steerable, we look EAST → the 1 East pillar is behind Center
  pre-pos SOUTH → if steerable, we look NORTH → the 2 North pillars are behind Center
  pre-pos NORTH → if steerable, we look SOUTH → the wide South wall is behind Center
If all three are identical → NOT steerable (canonical only).

Run: bash -c 'source bin/_dev-run.sh && dev_docker_run python3 <this>.py'
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # Tools/uedctl

from uedctl import builders, writes                           # noqa: E402
from uedctl.apply import _materialize, _materialized_order    # noqa: E402
from uedctl.driver import Driver                              # noqa: E402
from uedctl.editor import ensure_editor, stop_editor          # noqa: E402
from uedctl.model import Actor, Level                         # noqa: E402
from uedctl.normalize import canonical_actor_t3d              # noqa: E402
from uedctl.preview_render import (CLICK, CROP, _WMCTRL_SWEEP,  # noqa: E402
                                   _ini_for_mode)
from uedctl.uuid7 import uuid7                                 # noqa: E402

OUT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/preview-steerable")
TEX = "Engine.DefaultTexture"


def log(*a):
    print("[steerable]", *a, flush=True)


def pillar(name, x, y, h=300):
    return builders.make_brush_actor(name, builders.cube(48, 48, h, TEX),
                                     location=(x, y, -256 + h / 2), csg="add")


def build_scene() -> Level:
    acts = [builders.make_brush_actor("Room", builders.cube(1600, 1600, 512, TEX),
                                      location=(0, 0, 0), csg="subtract"),
            pillar("Center", 0, 0, h=360),                     # brush-align target (taller, central)
            pillar("East", 620, 0),                            # +X : 1
            pillar("NorthA", -70, 620), pillar("NorthB", 70, 620),   # +Y : 2
            pillar("WestA", -620, -110), pillar("WestB", -620, 0), pillar("WestC", -620, 110),  # -X : 3
            builders.make_brush_actor("SouthWall", builders.cube(420, 48, 360, TEX),
                                      location=(0, -620, -76), csg="add")]      # -Y : wide wall
    return Level(actors={a.name: a for a in acts}, order=[a.name for a in acts])


def point_align(drv, level, loc):
    """Set camera POSITION to `loc` via a transient helper Light + CAMERA ALIGN, then delete it."""
    name = writes.allocate_name(level, "PosHelper")
    helper = Actor(name=name, cls="Light", location=loc)
    writes.add_actor(drv, helper, level)
    drv.selectname(name)
    drv.camera_align(name=name)
    drv.selectname(name)
    drv.actor_delete()
    level.actors.pop(name, None)


def brush_align(drv, name):
    drv.selectname(name)
    drv.camera_align(name=name)


def shoot(drv, out_png: Path):
    from PIL import Image
    drv.exec("ACTOR SELECT NONE")
    drv.dexec_bash(_WMCTRL_SWEEP)
    drv.click(*CLICK)
    tmp = str(out_png) + ".full.png"
    drv.screenshot(tmp)
    Image.open(tmp).convert("RGB").crop(CROP).save(out_png)
    Path(tmp).unlink(missing_ok=True)


# (pre-position or None, tag). Z=-80 = mid-height.
CASES = [
    (None,            "default_noprepos"),
    ((-700, 0, -80),  "prepos_west"),     # steerable → look east → 1 pillar behind Center
    ((0, -700, -80),  "prepos_south"),    # steerable → look north → 2 pillars behind Center
    ((0, 700, -80),   "prepos_north"),    # steerable → look south → wide wall behind Center
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    level = build_scene()
    ed_id = uuid7()
    try:
        drv = Driver(container=ensure_editor(ed_id, ini_overrides=_ini_for_mode("shaded")))
        result = {n: canonical_actor_t3d(a) for n, a in level.actors.items()}
        mo = _materialized_order(result, level.order)
        log("materializing...")
        _materialize(drv, result=result, materialized_order=mo, packages=["Engine"])
        drv.dexec_bash(_WMCTRL_SWEEP)
        for prepos, tag in CASES:
            if prepos is not None:
                point_align(drv, level, prepos)
            brush_align(drv, "Center")
            shoot(drv, OUT / f"{tag}.png")
            log(f"  wrote {tag}.png (prepos={prepos})")
        log("DONE ->", OUT)
        return 0
    finally:
        stop_editor(ed_id)


if __name__ == "__main__":
    sys.exit(main())
