"""Live UED22 probe: what does a SELECTED BSP surface actually look like?

Confirms (or refutes) the disassembly finding in
`softdrv.dll!USoftwareRenderDevice::DrawComplexSurface` (`0x1000e644`-`0x1000e870`): after the
surface is rasterized, `GIsEditor && (Surface.PolyFlags & PF_Selected)` writes a raw, unblended
RGB(0,127,255) pixel on a 1-in-8-horizontal / 1-in-2-vertical stipple lattice.

Method (adapted from `dev/docs/spikes/2026-09-13-polys-render-mode-re/harness/polys_re_probe.py`,
whose recipe is already live-verified): one boot, perspective pane baked to RendMap=6 (PlainTex,
fullbright textured -- no lighting to confound the pixel values). Build a big Subtract room, pose
inside it, then take two shots from the SAME camera differing only in which wall's surface is
selected (a real left-click in the pane both selects the surface under the cursor and forces the
llvmpipe repaint). Diffing them gives the highlight's exact pixel values and lattice in both
directions.

    python3 surfsel_probe.py <out-dir>
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]  # repo root, from dev/docs/board/done/<item>/
sys.path.insert(0, str(ROOT))

from uedcli import builders, writes  # noqa: E402
from uedcli.driver import Driver  # noqa: E402
from uedcli.editor import ensure_editor, stop_editor, EditorNotReadyError  # noqa: E402
from PIL import Image  # noqa: E402

DEFAULT_TEX = "Engine.DefaultTexture"
PANE = (122, 636, 800, 1072)      # bottom-left perspective pane, fixed 1600x1158 headless frame
JUMP_TO = (-1600, 0, -400)
# two click points on (expected) different walls of the room, both inside PANE
CLICKS = {"a": (300, 850), "b": (650, 780)}
STATE_DIR = Path(os.environ.get("SURFSEL_STATE_DIR", "_scratch/surfsel/probe-state"))


def log(*a):
    print("[surfsel]", *a, flush=True)


def build_scene():
    return [
        builders.make_brush_actor(
            "Room", builders.cube(4096, 4096, 2048, DEFAULT_TEX), location=(0, 0, 0), csg="subtract"),
        builders.make_brush_actor(
            "BoxA", builders.cube(640, 640, 640, DEFAULT_TEX), location=(700, 200, -700), csg="add"),
    ]


def shot(d: Driver, tag: str, out_dir: Path) -> Path:
    full = out_dir / f"{tag}_full.png"
    d.screenshot(str(full))
    im = Image.open(full).convert("RGB")
    crop = out_dir / f"{tag}.png"
    im.crop(PANE).save(crop)
    return crop


def report(pa: Path, pb: Path):
    a = Image.open(pa).convert("RGB")
    b = Image.open(pb).convert("RGB")
    assert a.size == b.size
    w, h = a.size
    pa_, pb_ = a.load(), b.load()
    only_b = Counter()   # pixels that appear only in b (b selected here, a not)
    only_a = Counter()
    coords_b = []
    for y in range(h):
        for x in range(w):
            ca, cb = pa_[x, y], pb_[x, y]
            if ca == cb:
                continue
            only_b[cb] += 1
            only_a[ca] += 1
            coords_b.append((x, y, ca, cb))
    log(f"differing pixels: {len(coords_b)} of {w*h}")
    log("most common NEW (shot b) colors:", only_b.most_common(6))
    log("most common OLD (shot a) colors at those pixels:", only_a.most_common(6))
    # lattice: for the dominant new color, dump x/y spacing
    if only_b:
        top = only_b.most_common(1)[0][0]
        pts = [(x, y) for x, y, _, cb in coords_b if cb == top]
        ys = sorted({y for _, y in pts})
        log(f"dominant new color {top}: {len(pts)} px, distinct rows {len(ys)}")
        log("  row parity histogram (y%4):", Counter(y % 4 for _, y in pts).most_common())
        for yy in ys[:4]:
            xs = sorted(x for x, y in pts if y == yy)
            log(f"  row y={yy}: n={len(xs)} first={xs[:12]} dx={[xs[i+1]-xs[i] for i in range(min(8, len(xs)-1))]}")
            log(f"    x%8 histogram: {Counter(x % 8 for x in xs).most_common()}")


def main() -> int:
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    editor_id = str(uuid.uuid4())
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        container = ensure_editor(editor_id, state_dir=STATE_DIR, ready_timeout=180.0,
                                  start_attempts=2,
                                  ini_overrides={"U2Viewport2": {"RendMap": "6"}})
    except EditorNotReadyError as e:
        log(f"!! editor never ready: {e}")
        return 1
    try:
        d = Driver(container=container)
        d.map_new()
        writes._re_add(d, build_scene())
        d.rebuild()
        time.sleep(6)
        d.exec("POLY SELECT NONE")
        d.exec(f"JUMPTO {JUMP_TO[0]},{JUMP_TO[1]},{JUMP_TO[2]}")
        time.sleep(1.5)
        paths = {}
        for tag, (cx, cy) in CLICKS.items():
            d.click(PANE[0] + cx, PANE[1] + cy)
            time.sleep(2.0)
            paths[tag] = shot(d, tag, out_dir)
            log(f"shot {tag} at pane({cx},{cy}) -> {paths[tag]}")
        # a third shot: select every surface, then repaint via a click on the SAME spot as 'b'
        d.exec("POLY SELECT ALL")
        time.sleep(0.5)
        d.click(PANE[0] + CLICKS["b"][0], PANE[1] + CLICKS["b"][1])
        time.sleep(2.0)
        paths["all"] = shot(d, "all", out_dir)
        log("=== diff a (click A selected) vs b (click B selected) ===")
        report(paths["a"], paths["b"])
        log("=== diff b vs all ===")
        report(paths["b"], paths["all"])
        return 0
    finally:
        stop_editor(editor_id, STATE_DIR)


if __name__ == "__main__":
    sys.exit(main())
