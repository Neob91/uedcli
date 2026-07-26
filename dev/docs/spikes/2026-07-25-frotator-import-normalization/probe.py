"""Live probe: does UnrealEd 2.2's T3D **import** normalize an FRotator field mod 65536,
or preserve the authored integer verbatim?

WHY IT MATTERS. UE1 stores rotations as FRotator ints (65536 == 360 deg). The committed
editor-EXPORTED .t3d corpus is full of out-of-range values (`Rotation=(Yaw=-131072)` ~900x,
`(Yaw=-65536)` ~1900x, `(Yaw=-81920)`, `(Yaw=65536)`), all orientation-identical to a smaller
value. `level materialize` imports the T3D trunk, `MAP SAVE`s, re-exports the saved map and
text-compares against the trunk (H3 post-verify). If import reduced mod 65536, an actor authored
`(Yaw=-131072)` would come back as `(Yaw=0)` -- i.e. the whole `Rotation=` line would VANISH
(zero == class default, never exported) -- and post-verify could never pass for any ingested
retail actor with an over-range rotation. Two committed docstrings in `uedcli/rotation.py`
disagreed on this (`compose_uu` said "a materialize import normalizes mod 65536 anyway";
the compare-side fold said values must NEVER be reduced). This settles it empirically.

METHOD. One ephemeral `dx-lum-uned` editor; `MAP IMPORTADD` a tiny T3D of point actors
(`Engine.Light` + one `Engine.PlayerStart`) whose only interesting property is `Rotation`,
then read the value back on THREE separate legs so the leg that changes anything (if any) is
identified:

  leg A  `MAP EXPORT` straight after the import  -- the in-memory value the importer produced
  leg B  `MAP SAVE` -> offline UCC `batchexport` -- exactly what materialize's H3 post-verify reads
  leg C  `MAP LOAD` the saved .dx -> `MAP EXPORT` -- the editor's own binary read-back

Inputs (see `CASES`): two-full-turn negative, one-full-turn negative, one-full-turn positive,
an in-range positive control, an in-range negative (does it wrap to 49152?), a 1.25-turn
negative, and one actor exercising Pitch/Roll rather than Yaw.

Run host-native from anywhere inside the LUM project:
    /home/.../Tools/uedcli/.venv/bin/python <this file>
(or `cd Tools/uedcli && bin/uedcli`-style venv python). Raw exports land in `_scratch/`.
"""
import os
import re
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "..", ".."))

from uedcli import config, xfer                                   # noqa: E402
from uedcli.container_assets import resource_mounts               # noqa: E402
from uedcli.driver import Driver                                  # noqa: E402
from uedcli.editor import ensure_editor, stop_editor              # noqa: E402
from uedcli.store_export import export_dx_t3d                     # noqa: E402
from uedcli.uuid7 import uuid7                                    # noqa: E402

# name -> (class, authored Rotation=... value)
CASES = [
    ("RotTwoTurnNeg",  "Engine.Light",       "(Yaw=-131072)"),   # -2 full turns
    ("RotOneTurnNeg",  "Engine.Light",       "(Yaw=-65536)"),    # -1 full turn
    ("RotOneTurnPos",  "Engine.Light",       "(Yaw=65536)"),     # +1 full turn
    ("RotInRangePos",  "Engine.Light",       "(Yaw=16384)"),     # control: 90 deg, in range
    ("RotInRangeNeg",  "Engine.Light",       "(Yaw=-16384)"),    # in-range negative -> 49152?
    ("RotTurnAndQtr",  "Engine.Light",       "(Yaw=-81920)"),    # -1.25 turns
    ("RotPitchRoll",   "Engine.Light",       "(Pitch=-65536,Roll=-131072)"),  # other components
    ("RotPlayerStart", "Engine.PlayerStart", "(Yaw=-131072)"),   # class-independence check
]

DX_PATH = "/work/rotprobe.dx"


def build_t3d() -> str:
    out = ["Begin Map"]
    for i, (name, cls, rot) in enumerate(CASES):
        out += [f"Begin Actor Class={cls} Name={name}",
                f"    Location=(X={64 * (i + 1)}.000000,Y=0.000000,Z=0.000000)",
                f"    Rotation={rot}",
                "End Actor"]
    out += ["End Map", ""]
    return "\n".join(out)


def _cat(container: str, path: str) -> str | None:
    r = subprocess.run(["docker", "exec", container, "cat", path],
                       capture_output=True, text=True, check=False)
    return r.stdout if r.returncode == 0 else None


def export_and_read(ed: Driver, container_path: str, *, timeout: int = 60) -> str:
    """`MAP EXPORT` (fire-and-forget) + poll for a COMPLETE file, dismissing the GC dialog."""
    subprocess.run(["docker", "exec", ed.container, "rm", "-f", container_path], check=False,
                   capture_output=True)
    ed.dismiss_blocking_dialog()
    ed.map_export(container_path)
    for _ in range(timeout):
        time.sleep(1)
        ed.dismiss_blocking_dialog()
        txt = _cat(ed.container, container_path)
        if txt and "End Map" in txt:
            return txt
    raise TimeoutError(f"MAP EXPORT never completed: {container_path}")


def wait_for_file(container: str, path: str, *, timeout: int = 120) -> None:
    last = -1
    stable = 0
    for _ in range(timeout):
        time.sleep(1)
        r = subprocess.run(["docker", "exec", container, "stat", "-c", "%s", path],
                           capture_output=True, text=True, check=False)
        if r.returncode != 0:
            continue
        size = int(r.stdout.strip())
        if size > 0 and size == last:
            stable += 1
            if stable >= 3:
                return
        else:
            stable = 0
        last = size
    raise TimeoutError(f"file never appeared/settled: {path}")


def rotation_of(text: str, name: str) -> str:
    """The `Rotation=` value the export carries for `name`, or '<ABSENT>' / '<NO ACTOR>'."""
    m = re.search(rf"Begin Actor Class=\w+ Name={name}\b(.*?)End Actor", text, re.DOTALL)
    if m is None:
        return "<NO ACTOR>"
    r = re.search(r"^\s*Rotation=(\S+)", m.group(1), re.MULTILINE)
    return r.group(1) if r else "<ABSENT>"


def main() -> int:
    scratch = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "..", "..", "..", "..", "..", "_scratch")
    scratch = os.path.abspath(scratch)
    os.makedirs(scratch, exist_ok=True)

    project = config.resolve_project(env_project=os.environ.get("UEDCLI_PROJECT"),
                                     cwd=os.getcwd())
    user_config = config.load_user_config()
    search_dirs = config.composed_search_dirs(project, user_config)
    mounts = resource_mounts(search_dirs)
    state_dir = config.state_dir(project.root, create=True)
    ed_id = uuid7()
    legs: dict[str, str] = {}
    try:
        ed = Driver(container=ensure_editor(ed_id, mounts=mounts, state_dir=state_dir))
        ed.set_grid(1, 1, 1)
        ed.exec("MAP ROTGRID PITCH=1 YAW=1 ROLL=1")      # no rotation snapping
        with tempfile.NamedTemporaryFile("w", suffix=".t3d", delete=False) as f:
            f.write(build_t3d())
            host_in = f.name
        ed.map_importadd(xfer.cp_in(ed.container, host_in, ext=".t3d"))

        legs["A_after_import"] = export_and_read(ed, "/work/leg_a.t3d")

        subprocess.run(["docker", "exec", ed.container, "rm", "-f", DX_PATH], check=False,
                       capture_output=True)
        ed.dismiss_blocking_dialog()
        ed.map_save(DX_PATH)
        wait_for_file(ed.container, DX_PATH)
        legs["B_after_save_ucc"] = export_dx_t3d(ed.container, DX_PATH)

        ed.dismiss_blocking_dialog()
        ed.map_load_dx(DX_PATH)
        time.sleep(5)
        legs["C_after_reload"] = export_and_read(ed, "/work/leg_c.t3d")
    finally:
        stop_editor(ed_id, state_dir)

    for leg, text in legs.items():
        with open(os.path.join(scratch, f"rotprobe_{leg}.t3d"), "w", encoding="latin-1") as f:
            f.write(text)

    width = max(len(n) for n, _, _ in CASES)
    hdr = f"{'actor'.ljust(width)} | {'authored'.ljust(28)} | " + " | ".join(
        leg.ljust(28) for leg in legs)
    print(hdr)
    print("-" * len(hdr))
    for name, _cls, rot in CASES:
        row = [name.ljust(width), rot.ljust(28)]
        row += [rotation_of(text, name).ljust(28) for text in legs.values()]
        print(" | ".join(row))
    print("\nraw exports under", scratch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
