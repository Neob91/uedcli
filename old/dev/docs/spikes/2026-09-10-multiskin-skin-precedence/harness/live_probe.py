"""Live probe: which texture does UED22 actually paint on a mesh material slot when `Skin`,
`MultiSkins(i)` and the mesh's own `Textures(i)` compete?

Method (see ../README.md). Per CONFIG: `MAP NEW` → reload the mesh packages → `MAP IMPORTADD` the
SAME grid of mesh actors, differing ONLY in their `Skin` / `MultiSkins(N)` lines → `CAMERA OPEN
… REN=6` (PlainTex, capture-once at the fixed default pose, per `unrealed/rendering.md`) → grab that
camera window. The geometry is identical across configs, so any pixel difference between two configs
is caused solely by which texture the engine resolved.

The two probe skins are picked to be unmistakable: `Engine.DefaultTexture` (mean RGB ~131,140,122 —
BRIGHT) vs `Engine.Border` (mean ~19,17,11 — DARK). The mesh's OWN texture is the third, distinct
state.

Package loading: the baked ini's relative `Paths=` entries do not resolve here, so every package is
pulled in with an explicit `OBJ LOAD FILE=` (and re-pulled after each `MAP NEW`, which GCs them).
`DeusExDeco` needs only Core/Engine/Effects/DeusExItems — no `DeusEx.u`, which has no native DLL in
this substrate and cannot load.

    python3 live_probe.py <container> <out-dir> [<config-name>]
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from uedcli import xfer  # noqa: E402
from uedcli.driver import Driver, to_z_path  # noqa: E402

BRIGHT = "Texture'Engine.DefaultTexture'"
DARK = "Texture'Engine.Border'"
CRATE = "LodMesh'DeusExDeco.CrateUnbreakableLarge'"   # visible faces all on texture slot 0
FAUCET = "LodMesh'DeusExDeco.Faucet'"                 # 12 faces spread over texture slots 0/1/2
# 480 faces on texture slot 0 and 480 on slot 1, both plain-flagged — the one mesh in the substrate
# that makes the `Count != 0` branch visible.
EARTH = "LodMesh'DeusExDeco.Earth'"

PRELOAD = [
    r"OBJ LOAD FILE=Z:\opt\Textures\Effects.utx",
    r"OBJ LOAD FILE=Z:\opt\UED22\DeusExItems.u",
    r"OBJ LOAD FILE=Z:\opt\UED22\DeusExDeco.u",
]

# name -> (mesh, drawscale, {property line: value}). A/…/F answer the slot-0 question; G/H/J answer
# the `Count != 0` half (does the mesh's OWN Textures(i) outrank `Skin` at a non-zero slot?).
CONFIGS = {
    "A_skin-bright_multi-dark": (CRATE, 2, {"Skin": BRIGHT, "MultiSkins(0)": DARK}),
    "B_skin-dark_multi-bright": (CRATE, 2, {"Skin": DARK, "MultiSkins(0)": BRIGHT}),
    "C_skin-bright_only": (CRATE, 2, {"Skin": BRIGHT}),
    "D_multi-bright_only": (CRATE, 2, {"MultiSkins(0)": BRIGHT}),
    "E_skin-dark_only": (CRATE, 2, {"Skin": DARK}),
    "F_neither": (CRATE, 2, {}),
    "G_faucet_skin-bright": (FAUCET, 8, {"Skin": BRIGHT}),
    "H_faucet_neither": (FAUCET, 8, {}),
    "J_faucet_multi1-bright": (FAUCET, 8, {"MultiSkins(1)": BRIGHT}),
    "K_faucet_multi0-bright": (FAUCET, 8, {"MultiSkins(0)": BRIGHT}),
    "L_earth_neither": (EARTH, 1, {}),
    "M_earth_skin-bright": (EARTH, 1, {"Skin": BRIGHT}),
    "N_earth_multi1-bright": (EARTH, 1, {"MultiSkins(1)": BRIGHT}),
}

# A grid of copies so that whatever the fixed default camera pose is, some land in frame.
GRID = [(x, y, z) for x in (-384, -128, 128, 384) for y in (-384, -128, 128, 384) for z in (-128, 0, 128)]


def t3d(mesh: str, scale: int, props: dict[str, str]) -> str:
    out = ["Begin Map"]
    for i, (x, y, z) in enumerate(GRID):
        out.append(f"Begin Actor Class=Light Name=Probe{i}")
        out.append(f"    Location=(X={x}.000000,Y={y}.000000,Z={z}.000000)")
        out.append("    DrawType=DT_Mesh")
        out.append(f"    Mesh={mesh}")
        out.append(f"    DrawScale={scale}.000000")
        out.append("    bUnlit=True")
        for k, v in props.items():
            out.append(f"    {k}={v}")
        out.append(f"    Name=Probe{i}")
        out.append("End Actor")
    out.append("End Map")
    return "\n".join(out) + "\n"


def grab_camera_window(d: Driver, host_png: str) -> None:
    """Capture the `CAMERA OPEN` viewport window only.

    The camera window opens at (4,42) UNDER the main editor frame, and X11 here has no backing
    store — `import -window` re-reads the screen, so an un-parked editor frame IS what gets
    captured (that is the 'screenshot shows the toolbar' failure). Raising the camera does not
    work; parking every OTHER window off-screen does. The camera window itself is never moved: a
    `CAMERA OPEN` viewport blanks to black on any re-render (`unrealed/rendering.md`)."""
    park = xfer.cp_in(d.container, str(Path(__file__).with_name("park_others.sh")), ext="sh")
    xid = d.dexec_bash(
        "DISPLAY=:99 wmctrl -l | grep -i 'Viewport$' | tail -1 | awk '{print $1}'"
    ).strip().split()[-1]
    print(f"XID={xid}")
    print(d.dexec_bash(f"bash {park} {xid}"))
    # The camera window sits UNDER the editor frame until the park, and only repaints itself once
    # exposed — capture too soon and you get the stale editor pixels that were on that screen area.
    # ~20 s of idle is what makes the difference between the toolbar image and the real render.
    time.sleep(20)
    print(d.dexec_bash(
        f"DISPLAY=:99 import -window {xid} /work/skinshot.png; ls -l /work/skinshot.png"))
    xfer.cp_out(d.container, "/work/skinshot.png", host_png)
    subprocess.run(["docker", "exec", d.container, "rm", "-f", "/work/skinshot.png"], check=False)


def main() -> None:
    d = Driver(sys.argv[1])
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    only = sys.argv[3] if len(sys.argv) > 3 else None
    for n, (name, (mesh, scale, props)) in enumerate(CONFIGS.items()):
        if only and name != only:
            continue
        d.map_new()
        for line in PRELOAD:
            d.exec(line)
        host_t3d = out / f"{name}.t3d"
        host_t3d.write_text(t3d(mesh, scale, props))
        cpath = xfer.cp_in(d.container, str(host_t3d), ext="t3d")
        d.exec(f"MAP IMPORTADD FILE={to_z_path(cpath)}")
        d.select_none()
        # readback: prove the refs actually BOUND (the editor silently drops an unresolvable ref)
        exp = xfer.work_path("t3d")
        d.exec(f"MAP EXPORT FILE={to_z_path(exp)}")
        try:
            xfer.cp_out(d.container, exp, str(out / f"{name}.export.t3d"))
        except Exception as e:  # a missing readback must not lose the shot
            print(f"!! readback failed for {name}: {e}")
        d.exec(f"CAMERA OPEN NAME=SkinCam{n} XR=640 YR=480 REN=6 FLAGS=8")
        grab_camera_window(d, str(out / f"{name}.png"))
        print(f"== {name} done")


if __name__ == "__main__":
    main()
