#!/usr/bin/env python3
"""Round 10: CLEAN full-window shot — full-window perspective pane (ini Pct) + wmctrl the floating
black browser/log windows off-screen + crop the editor chrome (toolbars/command bar) to just the
viewport. Saves the full post-wmctrl frame AND a chrome-cropped version for tuning.
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

SID = "preview-spike10"
OUT = Path("/home/human/src/dx_lum/_scratch/preview-spike")
CLICK = (760, 560)
# first-guess chrome crop (left toolbar col, top menu+toolbar+pane-header, bottom command bar) — tune
CHROME = (104, 92, 1596, 1104)

SET_INI = r"""
p='/opt/UED22/UnrealEd.ini'
sec=None; out=[]
for l in open(p).read().split(chr(10)):
    if l.startswith('['): sec=l.strip()
    if sec=='[U2Viewport2]':
        if l.startswith('RendMap='): l='RendMap=6'
        elif l.startswith('Active='): l='Active=1'
        elif l.startswith('PctLeft='): l='PctLeft=0.000000'
        elif l.startswith('PctTop='): l='PctTop=0.000000'
        elif l.startswith('PctRight='): l='PctRight=1.000000'
        elif l.startswith('PctBottom='): l='PctBottom=1.000000'
    elif sec in ('[U2Viewport0]','[U2Viewport1]','[U2Viewport3]'):
        if l.startswith('Active='): l='Active=0'
    out.append(l)
open(p,'w').write(chr(10).join(out)); print('ini set')
"""

# move every top-level window EXCEPT the main editor frame (matched by ID, not title substring —
# the Log Window's title CONTAINS the main title, so a substring filter wrongly keeps it)
WMCTRL_SWEEP = (
    "MID=$(python3 /opt/uned/wine_ctl.py status | grep -oE 'window=[0-9]+' | cut -d= -f2); "
    "MHEX=$(printf '0x%08x' \"$MID\"); "
    "wmctrl -l | awk -v m=\"$MHEX\" 'tolower($1)!=tolower(m){print $1}' | "
    "while read w; do wmctrl -i -r \"$w\" -e 0,3200,3200,200,150 2>/dev/null; done; "
    "echo \"swept (kept main $MHEX)\"; wmctrl -l | sed 's/  */ /g' | cut -d' ' -f1,4-"
)


def main():
    H.SID = SID
    try:
        cid = ensure_editor(SID, ready_timeout=120.0)
        if not H.settle(cid):
            H.log("no settle"); stop_editor(SID); return 1
        H.log(subprocess.run(["docker", "exec", cid, "python3", "-c", SET_INI],
                             capture_output=True, text=True).stdout.strip())
        subprocess.run(["docker", "restart", cid], capture_output=True)
        H.log("restarted; settling...")
        if not H.settle(cid, timeout=120):
            H.log("no settle"); stop_editor(SID); return 1

        drv = Driver(container=cid)
        lvl = H.build_scene()
        result = {n: canonical_actor_t3d(a) for n, a in lvl.actors.items()}
        _materialize(drv, result=result, materialized_order=_materialized_order(result, lvl.order),
                     packages=["Engine"])
        H.log("scene ready.")

        out, err, _ = H.dexec(cid, WMCTRL_SWEEP)
        H.log("wmctrl windows after sweep:\n" + out)

        H.pose_camera(drv, (-800, 0, -300), -6, 0)
        H.dexec(cid, f"python3 {H.WINE_CTL} click --x {CLICK[0]} --y {CLICK[1]} --button 1")
        time.sleep(0.8)
        full = OUT / "r10_full.png"
        drv.screenshot(str(full))
        Image.open(full).convert("RGB").crop(CHROME).save(OUT / "r10_crop.png")
        H.log(f"saved r10_full.png (post-wmctrl) + r10_crop.png (chrome {CHROME})")
        return 0
    finally:
        stop_editor(SID)


if __name__ == "__main__":
    sys.exit(main())
