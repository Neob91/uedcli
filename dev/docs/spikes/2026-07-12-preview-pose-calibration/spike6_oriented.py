#!/usr/bin/env python3
"""Spike 6: does the brush-align framing ANGLE follow the TARGET BRUSH's orientation?

spike4 killed camera pre-positioning (align snaps canonical, ignores prior camera state). But the
CANONICAL angle itself might follow the brush's own orientation/shape — untested. If aligning to a
flat "signboard" slab views it FACE-ON, then rotating the slab rotates the camera around it → we steer
the view direction by orienting a throwaway target brush. **Pure console (CAMERA ALIGN), no drag.**

Scene: a room with directional landmarks (East=1 pillar, North=2, West=3, South=wide wall) at r≈620.
A flat slab (320-wide X, 24-thin Y, 200 tall) at the CENTRE — its wide-face normal is ±Y at Yaw=0.
Per rotation: add the slab with that Rotation, MAP REBUILD, CAMERA ALIGN to it, screenshot, delete.
Read which landmark sits behind the slab:
  Yaw=0   (face normal ±Y) → if face-on, camera views from ±Y → North(2)/South(wall) behind
  Yaw=90  (face normal ±X) → camera views from ±X → East(1)/West(3) behind
  Yaw=45  → a diagonal
  Pitch=45 → if it follows pitch, camera views from above/below (floor/ceiling in frame)
If the landmark/elevation CHANGES with the slab's rotation → orientation steers the angle → BUILD IT.
If all identical → the angle is a fixed world direction (independent of the brush).

Run: bash -c 'source bin/_dev-run.sh && dev_docker_run python3 <this>.py'
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # Tools/uedctl

from uedctl import builders, rotation, writes                 # noqa: E402
from uedctl.apply import _materialize, _materialized_order    # noqa: E402
from uedctl.driver import Driver                              # noqa: E402
from uedctl.editor import ensure_editor, stop_editor           # noqa: E402
from uedctl.model import Level                                # noqa: E402
from uedctl.normalize import canonical_actor_t3d              # noqa: E402
from uedctl.preview_render import (CLICK, CROP, _WMCTRL_SWEEP,  # noqa: E402
                                   _ini_for_mode)
from uedctl.uuid7 import uuid7                                 # noqa: E402

OUT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/preview-oriented")
TEX = "Engine.DefaultTexture"


def log(*a):
    print("[oriented]", *a, flush=True)


def _pillar(name, x, y, h=300):
    return builders.make_brush_actor(name, builders.cube(48, 48, h, TEX),
                                     location=(x, y, -256 + h / 2), csg="add")


def build_scene() -> Level:
    acts = [builders.make_brush_actor("Room", builders.cube(1600, 1600, 512, TEX),
                                      location=(0, 0, 0), csg="subtract"),
            _pillar("East", 620, 0),
            _pillar("NorthA", -80, 620), _pillar("NorthB", 80, 620),
            _pillar("WestA", -620, -110), _pillar("WestB", -620, 0), _pillar("WestC", -620, 110),
            builders.make_brush_actor("SouthWall", builders.cube(420, 48, 360, TEX),
                                      location=(0, -620, -76), csg="add")]
    return Level(actors={a.name: a for a in acts}, order=[a.name for a in acts])


def add_slab(drv, level, yaw_deg, pitch_deg):
    """A flat signboard slab at centre with the given Rotation; returns its name."""
    name = writes.allocate_name(level, "Target")
    slab = builders.make_brush_actor(name, builders.cube(320, 24, 200, TEX),
                                     location=(0, 0, -80), csg="add")
    slab.props.append(("Rotation", f"(Pitch={rotation.deg_to_uu(pitch_deg)},"
                                    f"Yaw={rotation.deg_to_uu(yaw_deg)},Roll=0)"))
    writes.add_actor(drv, slab, level)
    return name


def shoot(drv, out_png: Path):
    from PIL import Image
    drv.exec("ACTOR SELECT NONE")
    drv.dexec_bash(_WMCTRL_SWEEP)
    drv.click(*CLICK)
    tmp = str(out_png) + ".full.png"
    drv.screenshot(tmp)
    Image.open(tmp).convert("RGB").crop(CROP).save(out_png)
    Path(tmp).unlink(missing_ok=True)


CASES = [(0, 0, "yaw0"), (90, 0, "yaw90"), (45, 0, "yaw45"), (0, 45, "pitch45")]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    level = build_scene()
    ed_id = uuid7()
    try:
        drv = Driver(container=ensure_editor(ed_id, ini_overrides=_ini_for_mode("shaded")))
        result = {n: canonical_actor_t3d(a) for n, a in level.actors.items()}
        mo = _materialized_order(result, level.order)
        log("materializing base scene...")
        _materialize(drv, result=result, materialized_order=mo, packages=["Engine"])
        drv.dexec_bash(_WMCTRL_SWEEP)
        for yaw, pitch, tag in CASES:
            name = add_slab(drv, level, yaw, pitch)
            drv.rebuild()                          # CSG rebuild so the rotated slab is in geometry
            drv.selectname(name)
            drv.camera_align(name=name)
            shoot(drv, OUT / f"{tag}.png")
            drv.selectname(name)
            drv.actor_delete()
            level.actors.pop(name, None)
            log(f"  wrote {tag}.png (yaw={yaw}, pitch={pitch})")
        log("DONE ->", OUT)
        return 0
    finally:
        stop_editor(ed_id)


if __name__ == "__main__":
    sys.exit(main())
