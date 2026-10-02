"""Live pixel verification of the UED22 surface-selection stipple in the real GUI.

Headless Chromium (real WebGL 2 via SwiftShader) against this session's own dev server
(vite 5199 -> backend 8799, `showcase_bar`, rebuilt so the textured mesh exists). Switches the
perspective pane to Fullbright (the stipple only applies where the base mesh is drawn), grabs the
pane's exact WebGL drawing buffer, clicks a real BSP surface, grabs it again, and diffs: the changed
pixels must be exactly RGB(0,127,255) on a 1-in-2-row / 1-in-8-column lattice with the 4px
alternating phase `DrawComplexSurface` writes.

`page.screenshot()` is NOT usable for the colour half of this: the app's canvases land at fractional
CSS offsets (y=521.296875, width 540.5 for a 540px buffer), so the compositor resamples every
1-device-pixel dot across two output pixels at ~50% each. An init script forces
`preserveDrawingBuffer` on so `canvas.toDataURL()` returns the untouched drawing buffer instead.

    python3 stipple_verify.py <out-dir> [x y ...]     # click points, pane-relative
"""
from __future__ import annotations

import base64
import io
import os
import sys
from collections import Counter
from pathlib import Path

from playwright.sync_api import sync_playwright
from PIL import Image

URL = "http://localhost:5199/"
CHROME = "/home/agent/.cache/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell"
ARGS = ["--enable-unsafe-swiftshader", "--use-gl=angle", "--use-angle=swiftshader",
        "--disable-gpu-sandbox", "--no-sandbox"]
LIBS = os.environ.get("SURFSEL_LIBS", "_scratch/surfsel/libs")  # see harness-chromium-stubs.py

PRESERVE = """
const orig = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function (type, attrs) {
  if (type === 'webgl2' || type === 'webgl') attrs = { ...(attrs || {}), preserveDrawingBuffer: true };
  return orig.call(this, type, attrs);
};
"""
GRAB = "() => document.querySelectorAll('canvas')[2].toDataURL('image/png')"


def log(*a):
    print("[verify]", *a, flush=True)


def grab(page, path: Path) -> Image.Image:
    url = page.evaluate(GRAB)
    im = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGB")
    im.save(path)
    return im


def diff(a: Image.Image, b: Image.Image, tag: str) -> int:
    w, h = a.size
    pa, pb = a.load(), b.load()
    pts, new = [], Counter()
    for y in range(h):
        for x in range(w):
            if pa[x, y] != pb[x, y]:
                pts.append((x, y))
                new[pb[x, y]] += 1
    log(f"{tag}: {len(pts)} changed pixels of {w*h}")
    log(f"{tag}: new colours {new.most_common(4)}")
    target = [(x, y) for x, y in pts if pb[x, y] == (0, 127, 255)]
    log(f"{tag}: EXACTLY RGB(0,127,255) -> {len(target)} px "
        f"({100*len(target)/max(1,len(pts)):.1f}% of every changed pixel)")
    if not target:
        return 0
    ys = sorted({y for _, y in target})
    log(f"{tag}: rows touched {len(ys)}, y-parity counts {dict(Counter(y % 2 for _, y in target))}")
    log(f"{tag}: gaps between touched rows {sorted(Counter(ys[i+1]-ys[i] for i in range(len(ys)-1)).items())}")
    xgaps, phases = Counter(), Counter()
    for yy in ys:
        xs = sorted(x for x, y in target if y == yy)
        xgaps.update(xs[i+1]-xs[i] for i in range(len(xs)-1))
        phases[((yy // 2) % 2, xs[0] % 8)] += 1
    log(f"{tag}: gaps between dots within a row {sorted(xgaps.items())}")
    log(f"{tag}: (drawn-row parity, first dot's x%8) {sorted(phases.items())}")
    return len(target)


def main() -> int:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    pts = [(int(sys.argv[i]), int(sys.argv[i + 1])) for i in range(2, len(sys.argv) - 1, 2)]
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, args=ARGS,
                                    env={**os.environ, "LD_LIBRARY_PATH": LIBS})
        page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        page.add_init_script(PRESERVE)
        page.goto(URL, wait_until="networkidle")
        page.wait_for_timeout(12000)
        page.get_by_role("button", name="Fullbright").click()
        page.wait_for_timeout(6000)
        rect = page.evaluate("() => { const b = document.querySelectorAll('canvas')[2].getBoundingClientRect(); return [b.x, b.y, b.width, b.height] }")
        log("perspective pane rect:", rect)
        base = grab(page, out / "base.png")
        log("drawing buffer:", base.size)
        for n, (px, py) in enumerate(pts):
            page.mouse.click(rect[0] + px, rect[1] + py)
            page.wait_for_timeout(2500)
            sel = grab(page, out / f"sel{n}.png")
            log(f"click #{n} at pane({px},{py})")
            diff(base, sel, f"click{n}")
            page.keyboard.press("Escape")
            page.wait_for_timeout(1200)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
