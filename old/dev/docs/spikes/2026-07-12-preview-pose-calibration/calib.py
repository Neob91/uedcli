#!/usr/bin/env python3
"""Calibrate `level preview`'s camera POSE convention (pitch sign + yaw compass + gimbal pole).

The 2026-07-06 spike proved the ALIGN-helper recipe poses the MAIN perspective pane, but LEFT THE
PITCH SIGN AND YAW COMPASS UNVERIFIED (spike.md lines 49-50, 204; `preview_shots.py` PRESETS comment
"signs PROVISIONAL until a live shot confirms"). A live `level preview` run of the castle (2026-07-12)
showed the presets are WRONG: `@top` (-90) renders a horizon, and yaw presets aim off-compass.

This harness boots ONE editor (same code path as `preview_render`: `ensure_editor(ini_overrides=…)`
+ `_pose_camera` + main-pane screenshot + `CROP`), materializes an ASYMMETRIC landmark scene, and
sweeps yaw {0,90,180,270} and pitch {-89,-45,0,45,89} from the room centre. Read the PNGs to map
each yaw -> compass direction and each pitch -> up/level/down (+ whether the ±90 pole breaks).

Landmarks (unmistakable by silhouette), each standing on the floor (Z=-256):
  +X (EAST)  : ONE  pillar   at (620, 0)
  +Y (NORTH) : TWO  pillars  at (0, 620)
  -X (WEST)  : THREE pillars at (-620, 0)
  -Y (SOUTH) : a WIDE WALL   at (0, -620)
Plus a floor PAD at (0,0,-240) and a ceiling BAR at (0,0,+240) to read pitch up/down.

Run (no host installs): from Tools/uedcli,
    bash -c 'source bin/_dev-run.sh && dev_docker_run python3 \
        dev/docs/spikes/2026-07-12-preview-pose-calibration/calib.py'
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # Tools/uedcli

from uedcli import builders                                    # noqa: E402
from uedcli.apply import _materialize, _materialized_order     # noqa: E402
from uedcli.driver import Driver                               # noqa: E402
from uedcli.editor import ensure_editor, stop_editor           # noqa: E402
from uedcli.model import Level                                 # noqa: E402
from uedcli.normalize import canonical_actor_t3d               # noqa: E402
from uedcli.preview_render import (CLICK, CROP, _WMCTRL_SWEEP,  # noqa: E402
                                   _ini_for_mode)
from uedcli import rotation, writes                            # noqa: E402
from uedcli.model import Actor                                 # noqa: E402
from uedcli.uuid7 import uuid7                                 # noqa: E402

OUT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/preview-calib")
TEX = "Engine.DefaultTexture"


def _pose_camera(drv, level, location, pitch, yaw):
    """The ORIGINAL point-align + Rotation posing (removed from preview_render when auto-frame landed;
    Finding 1 proved it sets position only — its Rotation never renders). Kept local so this harness
    still reproduces that finding."""
    name = writes.allocate_name(level, "Light")
    helper = Actor(name=name, cls="Light", location=location,
                   props=[("Rotation", f"(Pitch={rotation.deg_to_uu(pitch)},"
                                        f"Yaw={rotation.deg_to_uu(yaw)},Roll=0)")])
    writes.add_actor(drv, helper, level)
    drv.selectname(name)
    drv.camera_align(name=name)
    drv.selectname(name)
    drv.actor_delete()
    level.actors.pop(name, None)


def log(*a):
    print("[calib]", *a, flush=True)


def pillar(name, x, y):
    # 48x48x300 vertical post standing on the floor (floor top at Z=-256 -> centre Z=-106)
    return builders.make_brush_actor(name, builders.cube(48, 48, 300, TEX),
                                     location=(x, y, -106), csg="add")


def build_scene() -> Level:
    room = builders.make_brush_actor("Room", builders.cube(1600, 1600, 512, TEX),
                                     location=(0, 0, 0), csg="subtract")
    acts = [room,
            pillar("EastPillar", 620, 0),                       # +X : 1 pillar
            pillar("NorthPillarA", -80, 620), pillar("NorthPillarB", 80, 620),   # +Y : 2 pillars
            pillar("WestPillarA", -620, -110), pillar("WestPillarB", -620, 0),   # -X : 3 pillars
            pillar("WestPillarC", -620, 110),
            # -Y : one WIDE WALL slab (400 wide x 360 tall), unmistakable vs pillars
            builders.make_brush_actor("SouthWall", builders.cube(400, 48, 360, TEX),
                                      location=(0, -620, -76), csg="add"),
            # pitch markers: a flat PAD on the floor centre, a BAR on the ceiling centre
            builders.make_brush_actor("FloorPad", builders.cube(160, 160, 32, TEX),
                                      location=(0, 0, -240), csg="add"),
            builders.make_brush_actor("CeilBar", builders.cube(260, 48, 32, TEX),
                                      location=(0, 0, 240), csg="add")]
    order = [a.name for a in acts]
    return Level(actors={a.name: a for a in acts}, order=order)


# (location, pitch, yaw, tag)  — camera at room centre (0,0,-80)
C = (0, 0, -80)
POSES = [
    (C, -3, 0,   "yaw000"), (C, -3, 90,  "yaw090"),
    (C, -3, 180, "yaw180"), (C, -3, 270, "yaw270"),
    (C, -89, 0,  "pitch_dn89"), (C, -45, 0, "pitch_dn45"), (C, 0, 0, "pitch_lvl"),
    (C, 45, 0,   "pitch_up45"), (C, 89, 0, "pitch_up89"),
]


def render(drv, level, loc, pitch, yaw, out_png: Path):
    from PIL import Image
    _pose_camera(drv, level, loc, pitch, yaw)
    drv.exec("ACTOR SELECT NONE")
    drv.dexec_bash(_WMCTRL_SWEEP)
    drv.click(*CLICK)
    tmp = str(out_png) + ".full.png"
    drv.screenshot(tmp)
    Image.open(tmp).convert("RGB").crop(CROP).save(out_png)
    Path(tmp).unlink(missing_ok=True)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ed_id = uuid7()
    try:
        drv = Driver(container=ensure_editor(ed_id, ini_overrides=_ini_for_mode("shaded")))
        level = build_scene()
        result = {n: canonical_actor_t3d(a) for n, a in level.actors.items()}
        mo = _materialized_order(result, level.order)
        log("materializing calibration scene...")
        _materialize(drv, result=result, materialized_order=mo, packages=["Engine"])
        drv.dexec_bash(_WMCTRL_SWEEP)
        log("scene ready; sweeping poses...")
        for (loc, pit, yaw, tag) in POSES:
            render(drv, level, loc, pit, yaw, OUT / f"{tag}.png")
            log(f"  wrote {tag}.png  (pitch={pit}, yaw={yaw})")
        log("DONE ->", OUT)
        return 0
    finally:
        stop_editor(ed_id)


if __name__ == "__main__":
    sys.exit(main())
