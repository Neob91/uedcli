"""Second leg of the FRotator over-range probe: the BRUSH path.

`probe.py` covers point actors, which `materialize` re-adds with `MAP IMPORTADD`. BRUSHES take a
different editor entry point — `writes._re_add` puts them on the X clipboard and runs `EDIT PASTE`
(the only add verb that leaves a brush ACTOR-SELECT-INSIDE-selectable). So the "does the editor
normalize an FRotator mod 65536?" question has to be answered for that entry point too, or the H3
post-verify conclusion only covers half of what materialize imports.

Method: build a cube with `builders.cube`, wrap it with `make_brush_actor`, give it
`Rotation=(Yaw=-131072)` (two full negative turns), push it through the PRODUCTION
`writes._re_add` paste path, `MAP REBUILD` (as materialize does), then read the value back on the
same three legs as `probe.py`:
  A `MAP EXPORT` after the paste       B `MAP SAVE` -> offline UCC batchexport      C reload -> export

A second cube carries an in-range control `(Yaw=16384)`.
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "..", ".."))

from uedcli import builders, config, writes                       # noqa: E402
from uedcli.container_assets import resource_mounts               # noqa: E402
from uedcli.driver import Driver                                  # noqa: E402
from uedcli.editor import ensure_editor, stop_editor              # noqa: E402
from uedcli.store_export import export_dx_t3d                     # noqa: E402
from uedcli.uuid7 import uuid7                                    # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe import export_and_read, rotation_of, wait_for_file      # noqa: E402

CASES = [("BrushTwoTurnNeg", "(Yaw=-131072)", (0.0, 0.0, 0.0)),
         ("BrushInRange",    "(Yaw=16384)",   (512.0, 0.0, 0.0))]
DX_PATH = "/work/rotprobe_brush.dx"


def main() -> int:
    scratch = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           *([".."] * 6), "_scratch"))
    os.makedirs(scratch, exist_ok=True)

    project = config.resolve_project(env_project=os.environ.get("UEDCLI_PROJECT"),
                                     cwd=os.getcwd())
    user_config = config.load_user_config()
    search_dirs = config.composed_search_dirs(project, user_config)
    mounts = resource_mounts(search_dirs)
    state_dir = config.state_dir(project.root, create=True)

    actors = []
    for name, rot, loc in CASES:
        a = builders.make_brush_actor(name, builders.cube(256, 256, 256), location=loc)
        a.props.insert(0, ("Rotation", rot))       # authored over-range / control rotation
        actors.append(a)

    ed_id = uuid7()
    legs: dict[str, str] = {}
    try:
        ed = Driver(container=ensure_editor(ed_id, mounts=mounts, state_dir=state_dir))
        ed.set_grid(1, 1, 1)
        ed.exec("MAP ROTGRID PITCH=1 YAW=1 ROLL=1")
        writes._re_add(ed, actors)                 # the PRODUCTION brush paste path
        time.sleep(3)
        ed.dismiss_blocking_dialog()
        ed.rebuild()
        time.sleep(10)
        legs["A_after_paste"] = export_and_read(ed, "/work/legb_a.t3d")

        subprocess.run(["docker", "exec", ed.container, "rm", "-f", DX_PATH], check=False,
                       capture_output=True)
        ed.dismiss_blocking_dialog()
        ed.map_save(DX_PATH)
        wait_for_file(ed.container, DX_PATH)
        legs["B_after_save_ucc"] = export_dx_t3d(ed.container, DX_PATH)

        ed.dismiss_blocking_dialog()
        ed.map_load_dx(DX_PATH)
        time.sleep(5)
        legs["C_after_reload"] = export_and_read(ed, "/work/legb_c.t3d")
    finally:
        stop_editor(ed_id, state_dir)

    for leg, text in legs.items():
        with open(os.path.join(scratch, f"rotprobe_brush_{leg}.t3d"), "w", encoding="latin-1") as f:
            f.write(text)

    width = max(len(n) for n, _, _ in CASES)
    print(f"{'actor'.ljust(width)} | {'authored'.ljust(14)} | "
          + " | ".join(leg.ljust(18) for leg in legs))
    for name, rot, _loc in CASES:
        print(" | ".join([name.ljust(width), rot.ljust(14)]
                         + [rotation_of(t, name).ljust(18) for t in legs.values()]))
    print("\nraw exports under", scratch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
