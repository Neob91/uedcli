"""Live UED22 probe: does clicking WELL INSIDE a StaticMesh actor's wireframe silhouette (away
from any drawn edge) select it in an ortho (wireframe) pane, or only a click on/near an actual
drawn wireframe line?

Disassembly (`GUI-PARITY.md` "Mesh selection ..." section) already shows:
  - `render.dll`'s `DrawActorSprite` (RVA 0x1f0a0) issues ONE `UViewport::PushHit(HActor)` call
    wrapping the actor's ENTIRE draw (own-binary: `AActor::GetHitActor`/`HActor::HActor`/
    `UViewport::PushHit` resolved by IAT import name).
  - `DrawLodMesh`'s Wire/Ortho branch (RVA 0xd050) draws ONLY per-face line segments in that mode
    (the filled-triangle block is skipped, per the already-closed "Mesh-actor wireframe rendering"
    finding).
  - `Engine.dll`'s `UViewport::ExecuteHits` (RVA 0x134bc0) walks a run-length hit-proxy BUFFER
    looking for a non-null entry, then dispatches its `Click` virtual -- a literal per-pixel
    readback, not an object-level test.
Combined: a mesh actor's hit-proxy is only ever stamped where something was actually PAINTED for
it, and in Wire/Ortho mode nothing paints between the wireframe edges -- so an interior click
should MISS. This probe checks that live.

Method: one large DT_Mesh actor (`DeusExDeco.CrateUnbreakableLarge`, DrawScale=8) at the origin, an
ortho TOP pane (RendMap=13, already the default `[U2Viewport0]` per `rendering.md`). Selection is
read back visually, not via `EDIT COPY`/property readback: a selected mesh-actor wireframe edge
renders in UED22's own confirmed selected color (`.2,.8,.1` bright green, RGB ~51,204,26) vs
unselected (`.6,.4,.1` olive/brown, RGB ~153,102,26) -- GUI-PARITY.md "Mesh-actor wireframe
rendering". So the test is: click a point, screenshot, and check whether any of the actor's own
wireframe pixels turned bright green.

**Status: NOT completed this session.** This got only as far as `main()` below (boot + place the
actor + one screenshot) before the host's docker daemon/disk blocked it (see the board item's
overview.md and GUI-PARITY.md's "Mesh-actor wireframe SELECTION" section for the two separate
failures hit). The click points below are NOT yet calibrated against a real screenshot -- the crate
occupies an UNKNOWN screen footprint at the ortho pane's default zoom (`rendering.md`: "Ortho
REN=13/14/15 render near-blank at the default zoom" is a real risk with DrawScale=8 alone). A
session that can actually boot the editor should: run this script once to get `01_before.png`,
measure the crate's actual on-screen bounding box from it (look for its `(153,102,26)` unselected
wireframe pixels), then add two `d.click(...)` + `d.screenshot(...)` calls -- one at the crate's
silhouette CENTER (expected: no green pixels appear, if the fix holds), one squarely on one of its
edges (expected: green pixels DO appear, the positive control proving the click mechanism itself
works) -- and diff each against `01_before.png` for `(51,204,26)` pixels.

    python3 harness-meshsel-probe.py <out-dir>
"""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]  # repo root, from dev/docs/board/done/<item>/
sys.path.insert(0, str(ROOT))

from uedcli.driver import Driver  # noqa: E402
from uedcli.editor import ensure_editor, stop_editor, EditorNotReadyError  # noqa: E402
from uedcli.writes import _write_container_file  # noqa: E402
from PIL import Image  # noqa: E402

# A daemon-mountable dir is required -- NOT under the worktree (`dev/docs/board/...`): this
# session's rootless dockerd could not `mkdir` anywhere under `/workspace` at all (same limitation
# already on file for the surface-selection-highlight/pivot-cross-toggle topics in GUI-PARITY.md).
STATE_DIR = Path("/tmp/meshsel-probe-state")
CRATE = "LodMesh'DeusExDeco.CrateUnbreakableLarge'"

PRELOAD = [
    r"OBJ LOAD FILE=Z:\opt\Textures\Effects.utx",
    r"OBJ LOAD FILE=Z:\opt\UED22\DeusExItems.u",
    r"OBJ LOAD FILE=Z:\opt\UED22\DeusExDeco.u",
]


def log(*a):
    print("[meshsel]", *a, flush=True)


def t3d() -> str:
    out = ["Begin Map"]
    out.append("Begin Actor Class=Light Name=Crate0")
    out.append("    Location=(X=0.000000,Y=0.000000,Z=0.000000)")
    out.append("    DrawType=DT_Mesh")
    out.append(f"    Mesh={CRATE}")
    out.append("    DrawScale=8.000000")
    out.append("    bUnlit=True")
    out.append("End Actor")
    out.append("End Map")
    return "\n".join(out)


def main() -> int:
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    editor_id = str(uuid.uuid4())
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        container = ensure_editor(editor_id, state_dir=STATE_DIR, ready_timeout=180.0, start_attempts=2)
    except EditorNotReadyError as e:
        log(f"!! editor never ready: {e}")
        return 1
    try:
        d = Driver(container=container)
        d.exec("MAP NEW")
        for line in PRELOAD:
            d.exec(line)
        # import the mesh actor via a raw T3D snippet, same pattern as writes._re_add
        d.map_importadd(_write_container_file(d, t3d()))
        time.sleep(1.5)
        d.exec("JUMPTO 0,0,0")
        time.sleep(1.0)
        full1 = out_dir / "01_before.png"
        d.screenshot(str(full1))
        log(f"wrote {full1} size={Image.open(full1).size}")
        return 0
    finally:
        stop_editor(editor_id, STATE_DIR)


if __name__ == "__main__":
    sys.exit(main())
