#!/usr/bin/env python3
"""Round 7: the perspective pane's OWN toolbar has per-viewport render-mode buttons (cube icons).
Clicking one targets THAT pane directly (no command box, no focus-steal, no restart) and repaints.
Probe the toolbar x-positions to map button -> mode, so mode becomes per-shot with a single click.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from uedcli.editor import ensure_editor, stop_editor           # noqa: E402
from uedcli.driver import Driver                               # noqa: E402
from uedcli.apply import _materialize, _materialized_order     # noqa: E402
from uedcli.normalize import canonical_actor_t3d               # noqa: E402
import harness as H                                            # noqa: E402
from PIL import Image                                          # noqa: E402

SID = "preview-spike7"
OUT = Path("/home/human/src/dx_lum/_scratch/preview-spike")
PANE = (122, 636, 800, 1072)
TOOLBAR_Y = 607                       # the pane's toolbar row (full-frame y)
PROBE_X = list(range(380, 516, 8))    # candidate mode-button x positions


def click(cid, x, y):
    H.dexec(cid, f"python3 {H.WINE_CTL} click --x {x} --y {y} --button 1")


def crop_mean(drv, tag):
    full = OUT / f"r7_{tag}_full.png"
    drv.screenshot(str(full))
    im = Image.open(full).convert("L").crop(PANE)
    p = OUT / f"r7_{tag}.png"
    Image.open(full).convert("RGB").crop(PANE).save(p)
    px = list(im.getdata())
    return sum(px) / len(px)


def run(cid):
    drv = Driver(container=cid)
    lvl = H.build_scene()
    result = {n: canonical_actor_t3d(a) for n, a in lvl.actors.items()}
    _materialize(drv, result=result, materialized_order=_materialized_order(result, lvl.order),
                 packages=["Engine"])
    drv.light_apply()
    # pose looking +X toward the box so there is textured content in frame
    H.pose_camera(drv, (-800, 0, -300), pitch=-6, yaw=0)
    click(cid, 460, 850); time.sleep(0.5)              # make current + repaint (baseline DynLight)
    base = crop_mean(drv, "base")
    H.log(f"baseline (DynLight) mean = {base:.1f}")
    for x in PROBE_X:
        click(cid, x, TOOLBAR_Y); time.sleep(0.6)      # click a toolbar button
        m = crop_mean(drv, f"x{x}")
        H.log(f"  click x={x} y={TOOLBAR_Y} -> pane mean = {m:.1f}")
    H.log("DONE — a big mean change at some x == that button switched the pane's render mode")


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
