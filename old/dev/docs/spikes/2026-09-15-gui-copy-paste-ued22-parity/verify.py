"""Live verification: does a REAL UnrealEd 2.2 `EDIT PASTE` correctly reconstruct a T3D blob
produced by `uedcli serve`'s new GUI clipboard-copy endpoint (`GET /api/level/{level}/actors/t3d`,
`uedcli/serve/app.py`)?

Drives an ephemeral editor container (`editor.ensure_editor`, the same production spin-up path
`level materialize`/`level photo` use) with NO package mounts (the fixture is a plain Light +
an untextured cube brush — no content packages needed). Builds a small in-memory Level, fetches the
SAME T3D text the GUI's Cmd/Ctrl+C would (via `create_app`'s real route, over `TestClient` — no HTTP
server needed for this), pastes it into a fresh `MAP NEW`, exports, and checks:

  1. both actors reappear, right Class/Name;
  2. the brush's geometry (poly/vertex count, winding-implied shape) survives;
  3. whether the well-known `EDIT PASTE +32uu drift` (quirks.md) applies to the POINT actor too, or
     only the brush -- settles what (if anything) the endpoint needs to compensate for a mixed
     point+brush selection pasted as ONE `Begin Map` blob (the endpoint does NOT split by kind the
     way `writes._re_add` does for `level materialize`'s own automated re-add).

Usage: `.venv/bin/python dev/docs/spikes/2026-09-15-gui-copy-paste-ued22-parity/verify.py`
(run from the repo root; needs Docker and the `ued-x86-runtime:latest` image, already built by any
prior `level materialize`/`level photo` run on this host)."""
from __future__ import annotations

import shutil
import sys
import time
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from fastapi.testclient import TestClient

from uedcli import editor, model, xfer
from uedcli.builders import cube, make_brush_actor
from uedcli.driver import Driver
from uedcli.serve import app as serve_app

EDITOR_ID = "spike-gui-copy-paste-verify"


def build_test_level():
    room = make_brush_actor("VerifyRoom", cube(256.0, 256.0, 128.0), location=(500.0, 300.0, 200.0),
                            csg="add")
    light = model.Actor(name="VerifyLight", cls="Light",
                        location=(Decimal(1000), Decimal(2000), Decimal(300)),
                        props=[("LightBrightness", "180"), ("Tag", "VerifySpike")])
    return room, light


def fetch_t3d_via_real_endpoint(tmp_path, room, light) -> str:
    """Exactly the code path the GUI hits: `create_app` + `GET .../actors/t3d`."""
    from uedcli import trunk
    root = tmp_path / "proj"
    maps_dir = root / "maps" / "VerifyLevel"
    maps_dir.mkdir(parents=True)
    level = model.Level(actors={room.name: room, light.name: light}, order=[room.name, light.name])
    trunk.write_level(maps_dir, level, {room.name: "n000", light.name: "n001"})
    project = SimpleNamespace(root=str(root), maps=None)
    # No packages needed for this fixture (untextured cube + a plain Light) -- bypass real
    # project/game config resolution the same way test_serve_actors_t3d.py does.
    serve_app._scene_inputs = lambda p: ([], None, None)
    app = serve_app.create_app(project, "VerifyLevel")
    with TestClient(app) as c:
        r = c.get("/api/level/VerifyLevel/actors/t3d", params={"names": f"{room.name},{light.name}"})
        r.raise_for_status()
        return r.json()["t3d"]


def wait_for_stable_file(driver: Driver, container_path: str, *, tries: int = 20, poll: float = 1.0) -> None:
    last = None
    for _ in range(tries):
        time.sleep(poll)
        cur = driver.container_stat(container_path)
        if cur is not None and cur == last:
            return
        last = cur
    raise RuntimeError(f"{container_path} never stabilized on {driver.container}")


def main() -> int:
    # A bind-mount SOURCE must be visible to the docker daemon, not just this shell -- /tmp under a
    # sandboxed shell is private and the mount silently fails ("not a directory": parallel-
    # editors.md). Use a repo-tree scratch dir instead, same as uedcli's own project state dir.
    # Left in place (gitignored, next run wipes it) so a failure's exported.t3d stays inspectable.
    scratch_root = Path(__file__).resolve().parents[4] / "_scratch" / "gui-copy-paste-verify"
    shutil.rmtree(scratch_root, ignore_errors=True)
    scratch_root.mkdir(parents=True)

    room, light = build_test_level()
    t3d = fetch_t3d_via_real_endpoint(scratch_root, room, light)
    print("=== T3D fetched from the real endpoint ===")
    print(t3d)

    state_dir = scratch_root / ".uedcli"
    state_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n=== starting ephemeral editor {EDITOR_ID!r} ===")
    container = editor.ensure_editor(EDITOR_ID, state_dir=state_dir, mounts=None)
    driver = Driver(container)
    try:
        driver.exec("MAP NEW")
        time.sleep(2.0)
        driver.set_grid(1, 1, 1)
        driver.set_clipboard(t3d)
        driver.edit_paste()
        time.sleep(2.0)

        work = xfer.work_path("t3d")
        driver.map_export(work)
        wait_for_stable_file(driver, work)
        host_out = str(scratch_root / "exported.t3d")
        xfer.cp_out(container, work, host_out)
        exported_text = Path(host_out).read_text()
        print("\n=== MAP EXPORT of the pasted result ===")
        print(exported_text)

        exported = model.parse_t3d(exported_text)
        print("\n=== actors in the exported level ===")
        for name, a in exported.actors.items():
            print(f"  {name}: cls={a.cls} location={a.location} brush={'yes' if a.brush else 'no'}")

        room_out = next((a for a in exported.actors.values() if a.cls == room.cls and a.brush), None)
        light_out = next((a for a in exported.actors.values() if a.cls == "Light"), None)

        print("\n=== findings ===")
        if room_out is None:
            print("FAIL: no brush actor of the expected class came back")
        else:
            dx = room_out.location[0] - room.location[0]
            dy = room_out.location[1] - room.location[1]
            dz = room_out.location[2] - room.location[2]
            print(f"brush Location drift: dx={dx} dy={dy} dz={dz}")
            print(f"brush poly count: authored={len(room.brush.polys)} "
                  f"exported={len(room_out.brush.polys) if room_out.brush else 'N/A'}")

        if light_out is None:
            print("FAIL: no Light actor came back")
        else:
            dx = light_out.location[0] - light.location[0]
            dy = light_out.location[1] - light.location[1]
            dz = light_out.location[2] - light.location[2]
            print(f"point-actor Location drift: dx={dx} dy={dy} dz={dz}")
            print(f"point-actor props: {light_out.props}")
    finally:
        print(f"\n=== tearing down {container} ===")
        editor.stop_editor(EDITOR_ID, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
