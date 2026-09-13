"""Live probe: what does UED22's REN=3 (Polys) render mode actually draw?

Only the numeric enum (`1`=Wire, `2`=Zones, `3`=Polys, `5`=DynLight, `6`=PlainTex) was RE'd before
this spike (`dev/docs/unrealed/commands.md` / `rendering.md`); nobody had captured what Polys (or
Zones) visually shows. `polys_probe.py` (this dir, previous attempt) tried bare `CAMERA OPEN`, which
`rendering.md` "Recommended: CAMERA OPEN" already documents as capture-once-at-a-fixed-default-pose —
in THIS container it came back stuck/stale (every mode looked like the same default grid scene, even
loading a full retail map), so it is superseded. It ALSO built its geometry via `MAP IMPORTADD` of a
raw brush T3D, which `quirks.md` "How brushes enter the level" documents as SKIPPED BY CSG ENTIRELY —
`MAP REBUILD` builds no BSP from an `IMPORTADD`'d brush, so the level stays perfectly solid and every
render mode shows nothing but each brush's own always-drawn wireframe. This spike hit that wall live
(see `spike.md` "Round 1") before finding the fix below.

The working recipe:

1. Build geometry the way `uedcli.writes.add_actor` does: point actors via `MAP IMPORTADD`, BRUSHES
   via `EDIT PASTE` (`writes._re_add`) — the ONLY add path that gets a brush into CSG
   (`quirks.md`). Use `uedcli.builders` (`cube`/`make_brush_actor`) to build them, same as any other
   uedcli-authored geometry.
2. Boot the editor with the perspective pane's render mode baked in at LAUNCH via
   `ensure_editor(..., ini_overrides={"U2Viewport2": {"RendMap": <mode>}})` — runtime `RMODE` cannot
   retarget the pane headless (the console click steals "current" away from it), so one boot = one
   mode.
3. Pose: `CAMERA ALIGN NAME=<brush>` turned out to give a degenerate, near-empty framing for a large
   Subtract room in THIS session (see `spike.md` "Round 2") — instead, `JUMPTO x,y,z` (position only,
   no rotation control, per `driver.py::jumpto`) to a coordinate INSIDE the room, relying on the
   perspective camera's fixed default rotation (yaw looking toward +X) to face the landmark boxes.
   Live-verified to land the boxes in frame (`spike.md` "Round 3").
4. Force the repaint + capture: a real `driver.click()` inside the bottom-left perspective pane
   (makes it current AND triggers the llvmpipe repaint that command-driven redraws skip) ->
   `driver.screenshot()` the main frame -> crop the pane rect `(122, 636, 800, 1072)` (verified at
   this editor build's fixed headless main-frame size, 1600x1158, by the 2026-07-06 spike rounds 3-5).

Scene design (classifies the render as per-poly / per-brush / per-texture): one big Subtract room
(`Engine.DefaultTexture` on all 6 faces, one brush) + two small ADD boxes, separate brushes — BoxA
shares the room's texture, BoxB uses a DIFFERENT texture (`Engine.Border`). If Polys colours by
BRUSH: Room's own faces read as one colour and BoxA (separate brush, same texture as the room) reads
DIFFERENT from Room despite the shared texture. If it colours by TEXTURE: Room and BoxA (both
`DefaultTexture`) match; BoxB (`Border`) differs. If it colours by POLY: the room's own 6 faces
(same brush, same texture) would still differ from each other.

    python3 polys_re_probe.py <out-dir> [mode1,mode2,...]

`mode` tags (name -> (RendMap int, apply light before the shot)):
  wire=1 (no light), zones=2 (light), polys=3 (light), polys_nolight=3 (no light), plaintex=6 (light)
Runs the full set by default; pass a comma list of tags to run a subset.
"""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from uedcli import builders, writes  # noqa: E402
from uedcli.driver import Driver  # noqa: E402
from uedcli.editor import ensure_editor, stop_editor, EditorNotReadyError  # noqa: E402
from uedcli.model import Actor  # noqa: E402
from PIL import Image  # noqa: E402

DEFAULT_TEX = "Engine.DefaultTexture"
BORDER_TEX = "Engine.Border"

PANE = (122, 636, 800, 1072)      # bottom-left perspective pane in the fixed 1600x1158 main frame
CLICK = (460, 850)                # a point inside PANE
JUMP_TO = (-1600, 0, -400)        # inside the room, off the -X wall, mid-height -- live-verified to
#                                   land both landmark boxes in the perspective pane's default view

STATE_DIR = Path(__file__).resolve().parents[5] / "_scratch" / "polys-re-probe-state"

# tag -> (RendMap, build_light)
MODES: dict[str, tuple[int, bool]] = {
    "wire": (1, True),
    "zones": (2, True),
    "polys": (3, True),
    "polys_nolight": (3, False),
    "plaintex": (6, True),
}


def build_scene_actors() -> list[Actor]:
    """Room (Subtract, `Engine.DefaultTexture`) + BoxA (Add, same texture as the room -- tests
    per-brush vs per-texture) + BoxB (Add, `Engine.Border` -- a second, distinct texture) + a Light.
    Coordinates match the room/box layout live-verified in `spike.md` Round 3 to land both boxes in
    the perspective pane's default (JUMPTO) view."""
    room = builders.make_brush_actor(
        "Room", builders.cube(4096, 4096, 2048, DEFAULT_TEX), location=(0, 0, 0), csg="subtract")
    box_a = builders.make_brush_actor(
        "BoxA", builders.cube(640, 640, 640, DEFAULT_TEX), location=(700, 200, -700), csg="add")
    box_b = builders.make_brush_actor(
        "BoxB", builders.cube(520, 520, 520, BORDER_TEX), location=(-700, -400, -750), csg="add")
    lamp = Actor(name="Lamp", cls="Light", location=(0, 0, 600),
                 props=[("LightBrightness", "200"), ("LightRadius", "64"),
                        ("LightHue", "0"), ("LightSaturation", "0")])
    return [room, box_a, box_b, lamp]


def log(*a):
    print("[polys-re]", *a, flush=True)


def capture(d: Driver, tag: str, out_dir: Path) -> Path:
    d.select_none()
    d.exec(f"JUMPTO {JUMP_TO[0]},{JUMP_TO[1]},{JUMP_TO[2]}")
    time.sleep(1.0)
    d.click(*CLICK)
    time.sleep(1.5)
    full = out_dir / f"{tag}_full.png"
    d.screenshot(str(full))
    cropped = out_dir / f"{tag}.png"
    im = Image.open(full).convert("RGB")
    log(f"  {tag}: full frame {im.size}")
    im.crop(PANE).save(cropped)
    return cropped


def run_mode(tag: str, rendmap: int, build_light: bool, out_dir: Path) -> bool:
    editor_id = uuid.uuid1().hex
    editor_id = "-".join([editor_id[0:8], editor_id[8:12], editor_id[12:16],
                          editor_id[16:20], editor_id[20:32]])
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        container = ensure_editor(editor_id, state_dir=STATE_DIR, ready_timeout=120.0,
                                  start_attempts=2,
                                  ini_overrides={"U2Viewport2": {"RendMap": str(rendmap)}})
    except EditorNotReadyError as e:
        log(f"  !! editor never became ready for {tag}: {e}")
        return False
    try:
        d = Driver(container=container)
        d.map_new()
        writes._re_add(d, build_scene_actors())
        d.rebuild()
        time.sleep(5)
        if build_light:
            d.light_apply()
            time.sleep(2)
        log(f"{tag}: scene ready (RendMap={rendmap}, light={build_light})")
        capture(d, tag, out_dir)
        log(f"{tag}: captured")
        return True
    finally:
        stop_editor(editor_id, STATE_DIR)


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("_scratch/polys-re-probe")
    out_dir.mkdir(parents=True, exist_ok=True)
    tags = sys.argv[2].split(",") if len(sys.argv) > 2 else list(MODES.keys())
    ok = True
    for tag in tags:
        rendmap, build_light = MODES[tag]
        log(f"=== mode {tag} (RendMap={rendmap}, light={build_light}) ===")
        success = run_mode(tag, rendmap, build_light, out_dir)
        if not success:
            log(f"  retrying {tag} once...")
            success = run_mode(tag, rendmap, build_light, out_dir)
        ok = ok and success
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
