#!/usr/bin/env python3
"""Spike 7: can the brush-align view direction be tilted UP/DOWN (elevation), not just azimuth?

spike6 proved the target brush's YAW steers the camera AZIMUTH, but my pitch test was flawed: I rotated
the slab about the Y-axis (FRotator Pitch), which is the slab's own face-normal axis (±Y), so it left
the steering direction unchanged → level. To tilt the view up/down I must rotate the face-normal OUT of
the horizontal plane. For a slab whose big-face normal is ±Y that means **Roll (about X)**. Test Roll
(and Pitch/Roll ±90) and read whether the camera looks at the FLOOR/CEILING (elevation) vs the level
wall (no elevation). A floor/ceiling-filled frame or a Z-tilted gizmo ⇒ elevation works ⇒ full pose.

Run: bash -c 'source bin/_dev-run.sh && dev_docker_run python3 <this>.py'
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # Tools/uedctl
sys.path.insert(0, str(Path(__file__).resolve().parent))      # import spike6

from uedctl import builders, rotation, writes                 # noqa: E402
from uedctl.apply import _materialize, _materialized_order    # noqa: E402
from uedctl.driver import Driver                              # noqa: E402
from uedctl.editor import ensure_editor, stop_editor           # noqa: E402
from uedctl.normalize import canonical_actor_t3d              # noqa: E402
from uedctl.preview_render import (CLICK, CROP, _WMCTRL_SWEEP,  # noqa: E402
                                   _ini_for_mode)
from uedctl.uuid7 import uuid7                                 # noqa: E402

from spike6_oriented import build_scene, shoot                # noqa: E402

OUT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/preview-elevation")
TEX = "Engine.DefaultTexture"


def log(*a):
    print("[elev]", *a, flush=True)


def add_slab(drv, level, yaw, pitch, roll):
    name = writes.allocate_name(level, "Target")
    slab = builders.make_brush_actor(name, builders.cube(320, 24, 200, TEX),
                                     location=(0, 0, -80), csg="add")
    slab.props.append(("Rotation", f"(Pitch={rotation.deg_to_uu(pitch)},"
                                    f"Yaw={rotation.deg_to_uu(yaw)},Roll={rotation.deg_to_uu(roll)})"))
    writes.add_actor(drv, slab, level)
    return name


# (yaw, pitch, roll, tag) — the four ways to tilt the ±Y face-normal up/down + a big pitch
CASES = [(0, 0, 90, "roll90"), (0, 0, -90, "roll_n90"), (0, 0, 45, "roll45"),
         (0, 90, 0, "pitch90")]


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
        for yaw, pitch, roll, tag in CASES:
            name = add_slab(drv, level, yaw, pitch, roll)
            drv.rebuild()
            drv.selectname(name)
            drv.camera_align(name=name)
            shoot(drv, OUT / f"{tag}.png")
            drv.selectname(name)
            drv.actor_delete()
            level.actors.pop(name, None)
            log(f"  wrote {tag}.png (yaw={yaw}, pitch={pitch}, roll={roll})")
        log("DONE ->", OUT)
        return 0
    finally:
        stop_editor(ed_id)


if __name__ == "__main__":
    sys.exit(main())
