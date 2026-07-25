#!/usr/bin/env python3
"""Round 8: can a CAMERA OPEN window be POSED by JUMPTO/CAMERA ALIGN issued AFTER it's open (or by
JUMPTO+ALIGN before open)? If yes → mode (REN=/FLAGS=) + pose in ONE window, no restart-per-mode, no
crop. Round 6 only tested ALIGN-then-OPEN (refuted); this tests the OPEN-then-pose order + adds JUMPTO.
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

SID = "preview-spike8"
OUT = Path("/home/human/src/dx_lum/_scratch/preview-spike")


def grab_open_window(cid, host_png):
    """Grab the most-recent CAMERA OPEN standalone window (title 'Viewport' for REN=6)."""
    xid, _, _ = H.dexec(cid, "wmctrl -l | grep -iv 'Unreal Editor' | grep -iv 'Log' | tail -1 | awk '{print $1}'")
    if not xid:
        return None
    H.dexec(cid, f"import -window {xid} /work/{host_png.name}")
    subprocess.run(["docker", "cp", f"{cid}:/work/{host_png.name}", str(host_png)], capture_output=True)
    return host_png if host_png.exists() else None


def mean(p):
    if not p or not p.exists():
        return -1
    im = Image.open(p).convert("L")
    d = list(im.getdata())
    return sum(d) / len(d)


def run(cid):
    drv = Driver(container=cid)
    lvl = H.build_scene()
    result = {n: canonical_actor_t3d(a) for n, a in lvl.actors.items()}
    _materialize(drv, result=result, materialized_order=_materialized_order(result, lvl.order),
                 packages=["Engine"])
    drv.light_apply()
    H.log("scene ready.")

    posA = (-800, 0, -300)   # look +X toward the box
    posB = (0, -800, -300)   # look +Y

    # VARIANT A: JUMPTO+ALIGN (set the perspective pose) THEN a fresh CAMERA OPEN
    H.log("VARIANT A: pose (jumpto+align) THEN open")
    drv.jumpto(*posA); H.pose_camera(drv, posA, -6, 0)
    drv.exec("CAMERA OPEN NAME=aA XR=640 YR=480 REN=6"); time.sleep(1.2)
    a_px = grab_open_window(cid, OUT / "r8_A_px.png")
    drv.jumpto(*posB); H.pose_camera(drv, posB, -6, 90)
    drv.exec("CAMERA OPEN NAME=aB XR=640 YR=480 REN=6"); time.sleep(1.2)
    a_yaw = grab_open_window(cid, OUT / "r8_A_yaw90.png")
    H.log(f"  A_px mean={mean(a_px):.1f}  A_yaw90 mean={mean(a_yaw):.1f}")

    # VARIANT B: CAMERA OPEN first, THEN jumpto+align retarget it; grab (and grab-after-click)
    H.log("VARIANT B: open THEN pose (does it retarget the open window?)")
    drv.exec("CAMERA OPEN NAME=bWin XR=640 YR=480 REN=6"); time.sleep(1.2)
    b_default = grab_open_window(cid, OUT / "r8_B_default.png")
    drv.jumpto(*posA); H.pose_camera(drv, posA, -6, 0); time.sleep(0.6)
    b_px = grab_open_window(cid, OUT / "r8_B_px.png")
    drv.jumpto(*posB); H.pose_camera(drv, posB, -6, 90); time.sleep(0.6)
    b_yaw = grab_open_window(cid, OUT / "r8_B_yaw90.png")
    H.log(f"  B_default mean={mean(b_default):.1f}  B_px mean={mean(b_px):.1f}  B_yaw90 mean={mean(b_yaw):.1f}")
    H.log("VERDICT: A_px vs A_yaw90 differ? -> pose-then-open works. "
          "B_default/px/yaw90 differ (and not ~0 black)? -> open window is retargetable.")


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
