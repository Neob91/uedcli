#!/usr/bin/env python3
"""Spike 5: does RMB-DRAG rotate the RENDERED perspective view (the fix for arbitrary orientation)?

calib/spike4 killed the CAMERA-ALIGN rotation paths (stored-not-rendered; brush-align ignores prior
position). `wine_ctl cmd_drag` docstring says RMB-drag = camera rotate (≈0.06°/px yaw, ≈0.10°/px
pitch) and — unlike a console command — a real drag FORCES the repaint, so the render should reflect
it. If confirmed: position via point-align, then RMB-drag by a computed delta = arbitrary orientation.

Test in the PREVIEW full-window setup: camera point-aligned to the room centre, then RMB-drag by
several (dx,dy) and screenshot. Read the asymmetric landmarks (East=1 pillar, North=2, West=3,
South=wide wall) to confirm the view actually rotates, and calibrate the default facing + yaw/pitch
sign & rate here.

Run: bash -c 'source bin/_dev-run.sh && dev_docker_run python3 <this>.py'
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # Tools/uedctl
sys.path.insert(0, str(Path(__file__).resolve().parent))      # import spike4

from uedctl import builders                                   # noqa: E402
from uedctl.apply import _materialize, _materialized_order     # noqa: E402
from uedctl.driver import Driver                              # noqa: E402
from uedctl.editor import ensure_editor, stop_editor           # noqa: E402
from uedctl.model import Level                                # noqa: E402
from uedctl.normalize import canonical_actor_t3d              # noqa: E402
from uedctl.preview_render import (CLICK, CROP, _WMCTRL_SWEEP,  # noqa: E402
                                   _ini_for_mode)
from uedctl.uuid7 import uuid7                                 # noqa: E402

from spike4_steerable import point_align                      # noqa: E402  (helper-Light position set)

TEX = "Engine.DefaultTexture"


def _pillar(name, x, y, h=300):
    return builders.make_brush_actor(name, builders.cube(48, 48, h, TEX),
                                     location=(x, y, -256 + h / 2), csg="add")


def build_scene() -> Level:
    """Asymmetric landmark room: +X=1 pillar, +Y=2, -X=3, -Y=wide wall (read facing from silhouette)."""
    acts = [builders.make_brush_actor("Room", builders.cube(1600, 1600, 512, TEX),
                                      location=(0, 0, 0), csg="subtract"),
            _pillar("East", 620, 0),
            _pillar("NorthA", -80, 620), _pillar("NorthB", 80, 620),
            _pillar("WestA", -620, -110), _pillar("WestB", -620, 0), _pillar("WestC", -620, 110),
            builders.make_brush_actor("SouthWall", builders.cube(420, 48, 360, TEX),
                                      location=(0, -620, -76), csg="add")]
    return Level(actors={a.name: a for a in acts}, order=[a.name for a in acts])

OUT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/preview-drag")
CENTER = (0, 0, -80)
DRAGX, DRAGY = CLICK                            # drag start = pane centre (same as the repaint click)


def log(*a):
    print("[drag]", *a, flush=True)


def wine_drag(drv, dx, dy):
    steps = max(16, (max(abs(dx), abs(dy)) + 9) // 10)     # keep per-step ≤10px
    subprocess.run(["docker", "exec", drv.container, "python3", "/opt/uned/wine_ctl.py", "drag",
                    str(DRAGX), str(DRAGY), str(dx), str(dy),
                    "--button", "3", "--steps", str(steps), "--step-pause", "0.07"],
                   check=True, capture_output=True, text=True)


def shoot(drv, out_png: Path, dx, dy):
    from PIL import Image
    point_align(drv, calib_level, CENTER)      # reset position (+ default orientation) each shot
    drv.dexec_bash(_WMCTRL_SWEEP)
    if (dx, dy) == (0, 0):
        drv.click(*CLICK)                      # default facing: click-repaint, no rotation
    else:
        wine_drag(drv, dx, dy)                 # RMB-drag rotates AND repaints
    tmp = str(out_png) + ".full.png"
    drv.screenshot(tmp)
    Image.open(tmp).convert("RGB").crop(CROP).save(out_png)
    Path(tmp).unlink(missing_ok=True)


# (dx, dy, tag) — yaw sweep (dx) then pitch sweep (dy). ~0.06°/px yaw → 500px≈30°, 1500px≈90°.
CASES = [
    (0, 0, "default"),
    (500, 0, "yaw_p500"), (1500, 0, "yaw_p1500"), (-1500, 0, "yaw_n1500"),
    (0, 500, "pitch_p500"), (0, -500, "pitch_n500"),
]

calib_level = None


def main() -> int:
    global calib_level
    OUT.mkdir(parents=True, exist_ok=True)
    calib_level = build_scene()
    ed_id = uuid7()
    try:
        drv = Driver(container=ensure_editor(ed_id, ini_overrides=_ini_for_mode("shaded")))
        result = {n: canonical_actor_t3d(a) for n, a in calib_level.actors.items()}
        mo = _materialized_order(result, calib_level.order)
        log("materializing landmark scene...")
        _materialize(drv, result=result, materialized_order=mo, packages=["Engine"])
        drv.dexec_bash(_WMCTRL_SWEEP)
        for dx, dy, tag in CASES:
            shoot(drv, OUT / f"{tag}.png", dx, dy)
            log(f"  wrote {tag}.png (dx={dx}, dy={dy})")
        log("DONE ->", OUT)
        return 0
    finally:
        stop_editor(ed_id)


if __name__ == "__main__":
    sys.exit(main())
