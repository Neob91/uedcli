#!/usr/bin/env python3
"""Spike 2: does `CAMERA ALIGN NAME=<BRUSH>` actually RE-AIM the headless perspective render?

calib.py proved the helper-Light rotation-adopt does NOT re-aim the render (all 9 pitch/yaw poses
gave the identical level view; only camera POSITION varied). The docs claim aligning to a *brush*
does a "look-at/frame" instead of a rotation-adopt. If that genuinely swings the rendered view to
the target, it's the fix (and a look-at/auto-frame is better UX than raw angles anyway).

Test: same landmark scene, align to each landmark BRUSH in turn and screenshot. If the view follows
(East->1 pillar centred, West->3 pillars, South->wide wall, North->2 pillars), look-at works. Also
capture where the camera ends up (does align reposition, or just aim?) by reading the silhouette size.

Run (from Tools/uedctl):
    bash -c 'source bin/_dev-run.sh && dev_docker_run python3 \
        dev/docs/spikes/2026-07-12-preview-pose-calibration/spike2_lookat.py'
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # Tools/uedctl
sys.path.insert(0, str(Path(__file__).resolve().parent))      # this spike dir (import calib)

from uedctl.apply import _materialize, _materialized_order     # noqa: E402
from uedctl.driver import Driver                               # noqa: E402
from uedctl.editor import ensure_editor, stop_editor           # noqa: E402
from uedctl.normalize import canonical_actor_t3d               # noqa: E402
from uedctl.preview_render import (CLICK, CROP, _WMCTRL_SWEEP,  # noqa: E402
                                   _ini_for_mode)
from uedctl.uuid7 import uuid7                                 # noqa: E402

import calib                                                  # noqa: E402  (scene builder)

OUT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/preview-lookat")

# (target brush name, tag) — expected framed silhouette in comments
TARGETS = [
    ("EastPillar", "east_1pillar"),      # +X : 1 pillar
    ("WestPillarB", "west_3pillar"),     # -X : 3 pillars
    ("SouthWall", "south_wall"),         # -Y : wide wall
    ("NorthPillarA", "north_2pillar"),   # +Y : 2 pillars
]


def log(*a):
    print("[lookat]", *a, flush=True)


def shoot(drv, tag, out_png: Path):
    from PIL import Image
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
        level = calib.build_scene()
        result = {n: canonical_actor_t3d(a) for n, a in level.actors.items()}
        mo = _materialized_order(result, level.order)
        log("materializing scene...")
        _materialize(drv, result=result, materialized_order=mo, packages=["Engine"])
        drv.dexec_bash(_WMCTRL_SWEEP)

        # baseline: default camera, no align
        log("baseline (no align)")
        shoot(drv, "baseline", OUT / "baseline.png")

        for name, tag in TARGETS:
            log(f"CAMERA ALIGN NAME={name}  -> {tag}")
            drv.selectname(name)
            drv.camera_align(name=name)      # align to a BRUSH = look-at/frame per docs
            shoot(drv, tag, OUT / f"{tag}.png")
        log("DONE ->", OUT)
        return 0
    finally:
        stop_editor(ed_id)


if __name__ == "__main__":
    sys.exit(main())
