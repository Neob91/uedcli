#!/usr/bin/env python3
"""Round 9: make the EMBEDDED perspective pane fill the whole main window via the ini Pct rects
(no HWND surgery), so a posed shot needs NO crop. Sets [U2Viewport2] to full-window + RendMap=6 and
hides the other 3, restarts, poses, captures the WHOLE window.
"""
import subprocess
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

SID = "preview-spike9"
OUT = Path("/home/human/src/dx_lum/_scratch/preview-spike")
CLICK = (760, 560)   # somewhere central in the (now full-window) perspective pane

# Set U2Viewport2 -> full-window + PlainTex; deactivate the other 3 panes.
SET_INI = r"""
import re
p='/opt/UED22/UnrealEd.ini'
lines=open(p).read().split(chr(10))
sec=None; out=[]
for l in lines:
    if l.startswith('['): sec=l.strip()
    if sec=='[U2Viewport2]':
        if l.startswith('RendMap='): l='RendMap=6'
        elif l.startswith('Active='): l='Active=1'
        elif l.startswith('PctLeft='): l='PctLeft=0.000000'
        elif l.startswith('PctTop='): l='PctTop=0.000000'
        elif l.startswith('PctRight='): l='PctRight=1.000000'
        elif l.startswith('PctBottom='): l='PctBottom=1.000000'
        elif l.startswith('ShowBackdrop='): l='ShowBackdrop=1'   # skybox/backdrop visible
    elif sec in ('[U2Viewport0]','[U2Viewport1]','[U2Viewport3]'):
        if l.startswith('Active='): l='Active=0'
    out.append(l)
open(p,'w').write(chr(10).join(out))
print('ini set: viewport2 full-window PlainTex, others inactive')
"""


def mean(p):
    if not p or not p.exists():
        return -1
    d = list(Image.open(p).convert('L').getdata())
    return sum(d) / len(d)


def shot(drv, cid, tag):
    drv.exec("") if False else None
    H.dexec(cid, f"python3 {H.WINE_CTL} click --x {CLICK[0]} --y {CLICK[1]} --button 1")
    time.sleep(0.6)
    p = OUT / f"r9_{tag}.png"
    drv.screenshot(str(p))
    return p


def main():
    H.SID = SID
    try:
        cid = ensure_editor(SID, ready_timeout=120.0)
        if not H.settle(cid):
            H.log("no settle"); stop_editor(SID); return 1
        out = subprocess.run(["docker", "exec", cid, "python3", "-c", SET_INI],
                             capture_output=True, text=True).stdout.strip()
        H.log(f"ini: {out}")
        subprocess.run(["docker", "restart", cid], capture_output=True)
        H.log("restarted; settling...")
        if not H.settle(cid, timeout=120):
            H.log("no settle after restart"); stop_editor(SID); return 1

        drv = Driver(container=cid)
        lvl = H.build_scene()
        result = {n: canonical_actor_t3d(a) for n, a in lvl.actors.items()}
        _materialize(drv, result=result, materialized_order=_materialized_order(result, lvl.order),
                     packages=["Engine"])
        H.log("scene ready (perspective pane should fill the window).")

        H.pose_camera(drv, (-800, 0, -300), -6, 0)
        a = shot(drv, cid, "px")
        H.pose_camera(drv, (0, -800, -300), -6, 90)
        b = shot(drv, cid, "yaw90")
        H.log(f"  r9_px mean={mean(a):.1f}  r9_yaw90 mean={mean(b):.1f}  (bright + differ => full-window posed shot, no crop)")
        return 0
    finally:
        stop_editor(SID)


if __name__ == "__main__":
    sys.exit(main())
