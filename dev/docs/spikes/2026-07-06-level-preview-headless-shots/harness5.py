#!/usr/bin/env python3
"""Round 5 (mode-via-ini): set [U2Viewport2] RendMap=6 (PlainTex) in the editor ini, restart, and
confirm a POSED shot of the perspective pane is now bright textured (vs the dark DynLight of round 4).
Proves the mode is selectable via the launch ini (runtime RMODE being blocked headless).
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

SID = "preview-spike5"
OUT = Path("/home/human/src/dx_lum/_scratch/preview-spike")
PANE = (122, 636, 800, 1072)
CLICK = (460, 850)

SET_INI = (
    "import sys\n"
    "p='/opt/UED22/UnrealEd.ini'\n"
    "sec=None; out=[]\n"
    "for l in open(p).read().split(chr(10)):\n"
    "    if l.startswith('['): sec=l.strip()\n"
    "    if sec=='[U2Viewport2]' and l.startswith('RendMap='): l='RendMap=6'\n"
    "    out.append(l)\n"
    "open(p,'w').write(chr(10).join(out))\n"
    "print('ini set')\n"
)


def click(cid):
    H.dexec(cid, f"python3 {H.WINE_CTL} click --x {CLICK[0]} --y {CLICK[1]} --button 1")


def crop(drv, tag):
    full = OUT / f"r5_{tag}_full.png"
    drv.screenshot(str(full))
    Image.open(full).convert("RGB").crop(PANE).save(OUT / f"r5_{tag}.png")
    return OUT / f"r5_{tag}.png"


def main():
    H.SID = SID
    try:
        cid = ensure_editor(SID, ready_timeout=120.0)
        if not H.settle(cid):
            H.log("no settle"); stop_editor(SID); return 1
        # edit the perspective-pane RendMap -> 6 (PlainTex), then restart so it re-reads the ini
        out, err, rc = subprocess.run(
            ["docker", "exec", cid, "python3", "-c", SET_INI],
            capture_output=True, text=True).stdout, "", 0
        H.log(f"ini edit: {out.strip()}")
        subprocess.run(["docker", "restart", cid], capture_output=True)
        H.log("restarted; settling...")
        if not H.settle(cid, timeout=120):
            H.log("no settle after restart"); stop_editor(SID); return 1

        drv = Driver(container=cid)
        lvl = H.build_scene()
        result = {n: canonical_actor_t3d(a) for n, a in lvl.actors.items()}
        _materialize(drv, result=result, materialized_order=_materialized_order(result, lvl.order),
                     packages=["Engine"])
        H.log("scene ready (perspective pane should be PlainTex now).")

        H.pose_camera(drv, (-800, 0, -300), pitch=-6, yaw=0)   # look +X toward the box
        click(cid); time.sleep(0.8)
        a = crop(drv, "shaded_px")
        H.pose_camera(drv, (0, -800, -300), pitch=-6, yaw=90)  # look +Y
        click(cid); time.sleep(0.8)
        b = crop(drv, "shaded_yaw90")
        H.stats([a, b])
        H.log("DONE — r5_shaded_px.png should be BRIGHT textured (mean >> the ~9 DynLight of round 4)")
        return 0
    finally:
        stop_editor(SID)


if __name__ == "__main__":
    sys.exit(main())
