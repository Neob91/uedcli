#!/usr/bin/env python3
"""Spike harness: does ALIGN-then-CAMERA-OPEN give a posed, headless shaded shot?

Run from Tools/uedcli with the uedcli venv. Spins an ephemeral editor, materializes an asymmetric
scene, then runs the experiments and prints numeric stats. PNGs land in _scratch/preview-spike/.
Always tears the editor down. See spike.md for the plan + pass criteria.
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # Tools/uedcli

from uedcli.editor import ensure_editor, stop_editor          # noqa: E402
from uedcli.driver import Driver                              # noqa: E402
from uedcli import builders, writes                           # noqa: E402
from uedcli.apply import _materialize, _materialized_order    # noqa: E402
from uedcli.normalize import canonical_actor_t3d              # noqa: E402
from uedcli.model import Level, Actor                         # noqa: E402
from uedcli.rotation import deg_to_uu                         # noqa: E402

SID = "preview-spike"
OUT = Path("/home/human/src/dx_lum/_scratch/preview-spike")
OUT.mkdir(parents=True, exist_ok=True)


def log(*a):
    print("[spike]", *a, flush=True)


def dexec(cid, sh):
    r = subprocess.run(["docker", "exec", cid, "bash", "-lc", sh],
                       capture_output=True, text=True)
    return r.stdout.strip(), r.stderr.strip(), r.returncode


WINE_CTL = "/opt/uned/wine_ctl.py"


def settle(cid, needed=3, timeout=90.0):
    """Poll wine_ctl status until it reports a resolvable window on `needed` CONSECUTIVE checks —
    the editor's window flickers as unresolvable for a bit right after boot (retries=1 fast-fail)."""
    deadline = time.monotonic() + timeout
    hits = 0
    while time.monotonic() < deadline:
        out, _, _ = dexec(cid, f"python3 {WINE_CTL} status")
        if "alive=True" in out and "window=" in out and "unresolved" not in out:
            hits += 1
            if hits >= needed:
                log(f"  editor settled ({out.splitlines()[-1] if out else ''})")
                return True
        else:
            hits = 0
        time.sleep(2.0)
    return False


def build_scene():
    tex = "Engine.DefaultTexture"
    room = builders.make_brush_actor(
        "Room", builders.cube(2048, 2048, 1024, tex), location=(0, 0, 0), csg="subtract")
    # a landmark box off to +X so poses looking different ways differ visibly
    box = builders.make_brush_actor(
        "Box", builders.cube(192, 192, 192, tex), location=(640, 0, -320), csg="add")
    lamp = Actor(name="Lamp", cls="Light", location=(0, 0, 300),
                 props=[("LightBrightness", "220"), ("LightRadius", "48"),
                        ("LightHue", "30"), ("LightSaturation", "24")])
    lvl = Level(actors={a.name: a for a in (room, box, lamp)}, order=["Room", "Box", "Lamp"])
    return lvl


def pose_camera(drv, loc, pitch, yaw):
    """Pose the live perspective camera via a helper Light + CAMERA ALIGN, then delete the helper."""
    helper = Actor(name="SpikeCam", cls="Light", location=loc,
                   props=[("Rotation", f"(Pitch={deg_to_uu(pitch)},Yaw={deg_to_uu(yaw)},Roll=0)")])
    writes.add_actor(drv, helper)
    drv.selectname("SpikeCam")
    drv.camera_align(name="SpikeCam")
    drv.selectname("SpikeCam")
    drv.actor_delete()


def camera_shot(drv, cid, name, ren, host_png):
    """Open a fresh camera in mode `ren`, grab its window, copy the PNG to the host."""
    drv.exec(f"CAMERA OPEN NAME={name} XR=640 YR=480 REN={ren}")
    time.sleep(1.5)
    # the just-opened standalone window is the most recent non-main-editor top-level window
    xid, err, rc = dexec(
        cid, "wmctrl -l | grep -iv 'Unreal Editor' | grep -iv 'Log' | tail -1 | awk '{print $1}'")
    if not xid:
        log(f"  !! no window found for {name} (stderr={err})")
        return None
    dexec(cid, f"import -window {xid} /work/{name}.png")
    subprocess.run(["docker", "cp", f"{cid}:/work/{name}.png", str(host_png)],
                   capture_output=True)
    return host_png if host_png.exists() else None


def stats(pngs):
    """Per-image mean + pairwise mean-abs-diff, via Pillow if present else ImageMagick."""
    try:
        from PIL import Image
        import statistics
        arrs = {}
        for p in pngs:
            im = Image.open(p).convert("L").resize((160, 120))
            arrs[p.name] = list(im.getdata())
        for p in pngs:
            log(f"  mean[{p.name}] = {statistics.mean(arrs[p.name]):.1f}")
        names = [p.name for p in pngs]
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = arrs[names[i]], arrs[names[j]]
                d = sum(abs(x - y) for x, y in zip(a, b)) / len(a)
                log(f"  meanabsdiff[{names[i]} vs {names[j]}] = {d:.1f}")
    except Exception as e:  # noqa: BLE001
        log(f"  (stats unavailable: {e})")


def run_experiments(cid):
        drv = Driver(container=cid)
        lvl = build_scene()
        result = {n: canonical_actor_t3d(a) for n, a in lvl.actors.items()}
        mo = _materialized_order(result, lvl.order)
        log("materializing scene...")
        _materialize(drv, result=result, materialized_order=mo, packages=["Engine"])
        drv.light_apply()
        log("scene ready.")

        # EXP 1 — pose control: default OPEN vs ALIGN-then-OPEN
        log("EXP1: default vs aligned")
        s_def = camera_shot(drv, cid, "def0", 6, OUT / "exp1_default.png")
        pose_camera(drv, (-700, 0, -300), pitch=-8, yaw=0)      # near -X wall, looking +X toward the box
        s_aln = camera_shot(drv, cid, "aln0", 6, OUT / "exp1_aligned.png")
        stats([p for p in (s_def, s_aln) if p])

        # EXP 2 — multi-shot, 3 distinct poses in one boot
        log("EXP2: 3 poses one boot")
        poses = [((-700, 0, -300), -8, 0, "px"),      # look +X (toward box)
                 ((700, 0, -300), -8, 180, "nx"),     # look -X (away from box)
                 ((0, 0, 400), -89, 0, "top")]        # look straight down
        e2 = []
        for (loc, pit, yaw, tag) in poses:
            pose_camera(drv, loc, pit, yaw)
            s = camera_shot(drv, cid, f"exp2_{tag}", 6, OUT / f"exp2_{tag}.png")
            if s:
                e2.append(s)
        stats(e2)

        # EXP 3 — modes from one pose
        log("EXP3: modes")
        pose_camera(drv, (-700, 0, -300), pitch=-8, yaw=0)
        e3 = []
        for tag, ren in (("shaded", 6), ("lit", 5), ("zones", 2), ("polys", 3), ("wire", 1)):
            s = camera_shot(drv, cid, f"exp3_{tag}", ren, OUT / f"exp3_{tag}.png")
            if s:
                e3.append(s)
        stats(e3)

        log("DONE — inspect PNGs in", OUT)


def main():
    attempts = 2
    for attempt in range(1, attempts + 1):
        log(f"=== attempt {attempt}/{attempts}: spinning editor ===")
        try:
            cid = ensure_editor(SID, ready_timeout=120.0)
        except Exception as e:  # noqa: BLE001
            log(f"  ensure_editor failed: {e}")
            stop_editor(SID)
            continue
        log(f"editor up: {cid}; settling...")
        try:
            if not settle(cid):
                log("  editor never settled — recreating")
                stop_editor(SID)
                continue
            run_experiments(cid)
            log("run complete.")
            stop_editor(SID)
            return 0
        except Exception as e:  # noqa: BLE001
            log(f"  run failed on attempt {attempt}: {e}")
            stop_editor(SID)
            time.sleep(3.0)
    log("!! all attempts failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
