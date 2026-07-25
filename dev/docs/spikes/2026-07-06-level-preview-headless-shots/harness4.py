#!/usr/bin/env python3
"""Round 4: confirm SHADED (RMODE 6 PlainTex) on the posed main perspective pane + a clean crop.

Recipe under test (per shot): CAMERA ALIGN pose -> click pane (make current + repaint) -> RMODE 6
-> click again (repaint in the new mode) -> screenshot frame -> crop the perspective pane. Compares
the DynLight (default) crop vs the PlainTex crop (shaded should be much brighter).
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
from PIL import Image                                          # noqa: E402

SID = "preview-spike4"
OUT = Path("/home/human/src/dx_lum/_scratch/preview-spike")
PANE = (122, 636, 800, 1072)   # perspective pane, toolbar row trimmed off the top
CLICK = (460, 850)


def click(cid):
    H.dexec(cid, f"python3 {H.WINE_CTL} click --x {CLICK[0]} --y {CLICK[1]} --button 1")


def crop(drv, tag):
    full = OUT / f"r4_{tag}_full.png"
    drv.screenshot(str(full))
    im = Image.open(full).convert("RGB").crop(PANE)
    p = OUT / f"r4_{tag}.png"
    im.save(p)
    return p


def run(cid):
    drv = Driver(container=cid)
    lvl = H.build_scene()
    result = {n: canonical_actor_t3d(a) for n, a in lvl.actors.items()}
    _materialize(drv, result=result, materialized_order=_materialized_order(result, lvl.order),
                 packages=["Engine"])
    drv.light_apply()
    H.log("scene ready.")

    # pose looking +X toward the landmark box, level
    H.pose_camera(drv, (-800, 0, -300), pitch=-6, yaw=0)
    click(cid); time.sleep(0.6)
    dyn = crop(drv, "dynlight")            # default DynLight (5)
    drv.rmode(6)                           # current pane -> PlainTex (textured fullbright)
    click(cid); time.sleep(0.6)            # repaint in the new mode
    tex = crop(drv, "shaded")
    # a second pose to confirm pose still varies under shaded
    H.pose_camera(drv, (0, -800, -300), pitch=-6, yaw=90)
    click(cid); time.sleep(0.6)
    tex2 = crop(drv, "shaded_yaw90")
    H.stats([dyn, tex, tex2])
    H.log("DONE — r4_dynlight.png (dark) vs r4_shaded.png (should be bright textured)")


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
