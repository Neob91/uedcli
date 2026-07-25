#!/usr/bin/env python3
"""Round 3 (decisive): does CAMERA ALIGN (exact pose on the main perspective pane) + a mouse-click
to repaint + a crop of the bottom-left perspective pane give DISTINCT posed images?

Perspective pane = bottom-left quadrant of the 1600x1158 frame (learned in round 2). If the crops
for distinct poses differ AND match their poses, the main-pane-crop mechanism is the viable path.
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from uedctl.editor import ensure_editor, stop_editor           # noqa: E402
from uedctl.driver import Driver                               # noqa: E402
from uedctl.apply import _materialize, _materialized_order     # noqa: E402
from uedctl.normalize import canonical_actor_t3d               # noqa: E402
import harness as H                                            # noqa: E402
from PIL import Image                                          # noqa: E402

SID = "preview-spike3"
OUT = Path("/home/human/src/dx_lum/_scratch/preview-spike")
PANE = (120, 600, 800, 1075)   # left, top, right, bottom of the perspective (bottom-left) pane
CLICK = (460, 840)             # window-relative point inside that pane


def click(cid, x, y):
    H.dexec(cid, f"python3 {H.WINE_CTL} click --x {x} --y {y} --button 1")


def frame_crop(drv, cid, tag):
    full = OUT / f"r3_{tag}_full.png"
    drv.screenshot(str(full))
    im = Image.open(full).convert("RGB").crop(PANE)
    crop = OUT / f"r3_{tag}.png"
    im.save(crop)
    return crop


def run(cid):
    drv = Driver(container=cid)
    lvl = H.build_scene()
    result = {n: canonical_actor_t3d(a) for n, a in lvl.actors.items()}
    _materialize(drv, result=result, materialized_order=_materialized_order(result, lvl.order),
                 packages=["Engine"])
    drv.light_apply()
    H.log("scene ready.")

    # make the perspective pane current + repaint once (a click), capture a baseline crop
    click(cid, *CLICK)
    time.sleep(0.8)
    base = frame_crop(drv, cid, "base")

    # distinct poses via ALIGN, each followed by a click (make current + repaint), then crop
    poses = [((0, 0, 200), -89, 0, "down"),       # look straight down
             ((-800, 0, -300), -6, 0, "yaw0"),    # look +X, level
             ((0, -800, -300), -6, 90, "yaw90")]  # look +Y, level
    crops = [base]
    for (loc, pit, yaw, tag) in poses:
        H.pose_camera(drv, loc, pit, yaw)
        click(cid, *CLICK)            # make current + force llvmpipe repaint of the posed view
        time.sleep(0.8)
        crops.append(frame_crop(drv, cid, tag))
    H.stats(crops)
    H.log("DONE — inspect r3_*.png (perspective-pane crops)")


def main():
    for attempt in (1, 2):
        H.log(f"=== attempt {attempt}: editor ===")
        try:
            cid = ensure_editor(SID, ready_timeout=120.0)
        except Exception as e:  # noqa: BLE001
            H.log(f"  ensure_editor failed: {e}"); stop_editor(SID); continue
        try:
            if not H.settle(cid):
                stop_editor(SID); continue
            run(cid); stop_editor(SID); return 0
        except Exception as e:  # noqa: BLE001
            H.log(f"  run failed: {e}"); stop_editor(SID); time.sleep(3.0)
    return 1


H.SID = SID

if __name__ == "__main__":
    sys.exit(main())
