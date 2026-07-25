#!/usr/bin/env python3
"""Round 6: does CAMERA OPEN clone the CURRENT viewport's pose? If ALIGN + click-to-make-the-
perspective-pane-current + CAMERA OPEN inherits the pose, we get per-shot POSE *and* per-shot MODE
(REN=) *and* a clean window grab — the ideal, no cropping, no per-command-mode limit.

Round-1 tested ALIGN-then-OPEN WITHOUT the make-current click (found in round 3), so this fills the gap.
"""
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

SID = "preview-spike6"
OUT = Path("/home/human/src/dx_lum/_scratch/preview-spike")
CLICK = (460, 840)   # inside the bottom-left perspective pane


def click(cid):
    H.dexec(cid, f"python3 {H.WINE_CTL} click --x {CLICK[0]} --y {CLICK[1]} --button 1")


def run(cid):
    drv = Driver(container=cid)
    lvl = H.build_scene()
    result = {n: canonical_actor_t3d(a) for n, a in lvl.actors.items()}
    _materialize(drv, result=result, materialized_order=_materialized_order(result, lvl.order),
                 packages=["Engine"])
    drv.light_apply()
    H.log("scene ready.")

    # per shot: ALIGN pose -> click perspective pane (make CURRENT + repaint) -> CAMERA OPEN REN=n
    poses = [((-800, 0, -300), -6, 0, "px", 6),      # look +X, shaded
             ((0, -800, -300), -6, 90, "yaw90", 6),  # look +Y, shaded
             ((0, 0, 300), -89, 0, "top", 6),        # look straight down, shaded
             ((-800, 0, -300), -6, 0, "px_wire", 1)]  # look +X, WIRE (per-shot mode alongside pose)
    shots = []
    for (loc, pit, yaw, tag, ren) in poses:
        H.pose_camera(drv, loc, pit, yaw)
        click(cid); time.sleep(0.5)                  # make the posed perspective pane current
        s = H.camera_shot(drv, cid, f"r6_{tag}", ren, OUT / f"r6_{tag}.png")
        if s:
            shots.append(s)
    H.stats(shots)
    H.log("DONE — if r6_px/yaw90/top DIFFER, CAMERA OPEN inherits the current (posed) viewport")


def main():
    H.SID = SID
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


if __name__ == "__main__":
    sys.exit(main())
