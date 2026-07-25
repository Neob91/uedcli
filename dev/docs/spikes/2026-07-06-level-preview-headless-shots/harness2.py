#!/usr/bin/env python3
"""Round 2: (a) capture the main 4-pane frame to learn the layout, (b) ortho modes via CAMERA OPEN.

Reuses harness.py's helpers. Determines the perspective-pane location (for the pose experiments in
round 3) and whether ortho REN=13/14/15 auto-frame the level.
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # Tools/uedctl
sys.path.insert(0, str(Path(__file__).resolve().parent))       # this dir (import harness)

from uedctl.editor import ensure_editor, stop_editor           # noqa: E402
from uedctl.driver import Driver                               # noqa: E402
from uedctl.apply import _materialize, _materialized_order     # noqa: E402
from uedctl.normalize import canonical_actor_t3d               # noqa: E402
import harness as H                                            # noqa: E402

SID = "preview-spike2"
OUT = Path("/home/human/src/dx_lum/_scratch/preview-spike")


def run(cid):
    drv = Driver(container=cid)
    lvl = H.build_scene()
    result = {n: canonical_actor_t3d(a) for n, a in lvl.actors.items()}
    mo = _materialized_order(result, lvl.order)
    H.log("materializing...")
    _materialize(drv, result=result, materialized_order=mo, packages=["Engine"])
    drv.light_apply()
    H.log("scene ready.")

    # (a) main 4-pane frame — to learn the layout + which quadrant is the 3D perspective pane
    H.log("capturing main frame...")
    drv.screenshot(str(OUT / "r2_mainframe.png"))
    out, _, _ = H.dexec(cid, f"python3 {H.WINE_CTL} status")
    H.log(f"  status: {out.splitlines()[-1] if out else ''}")

    # (b) ortho modes via CAMERA OPEN (auto-framed top/side, no pose needed)
    H.log("EXP5: ortho modes")
    e5 = []
    for tag, ren in (("orthoXY_top", 13), ("orthoXZ", 14), ("orthoYZ", 15)):
        s = H.camera_shot(drv, cid, f"r2_{tag}", ren, OUT / f"r2_{tag}.png")
        if s:
            e5.append(s)
    H.stats(e5)
    H.log("DONE")


def main():
    for attempt in (1, 2):
        H.log(f"=== attempt {attempt}: editor ===")
        try:
            cid = ensure_editor(SID, ready_timeout=120.0)
        except Exception as e:  # noqa: BLE001
            H.log(f"  ensure_editor failed: {e}")
            stop_editor(SID)
            continue
        try:
            if not H.settle(cid):
                stop_editor(SID)
                continue
            run(cid)
            stop_editor(SID)
            return 0
        except Exception as e:  # noqa: BLE001
            H.log(f"  run failed: {e}")
            stop_editor(SID)
            time.sleep(3.0)
    return 1


# harness.py uses SID="preview-spike"; ensure stop_editor targets ours
H.SID = SID

if __name__ == "__main__":
    sys.exit(main())
