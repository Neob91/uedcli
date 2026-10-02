#!/usr/bin/env python3
"""Characterize ACTOR SELECT INSIDE selectability across brush-creation variants.

Runs on the HOST, drives the in-container UnrealEd via `docker exec … wine_ctl`.
Liveness-checked: aborts the instant UnrealEd dies, naming the op that killed it.
"""
import copy
import re
import subprocess
import sys
import time

sys.path.insert(0, ".")
from uedcli.model import Actor, Brush, Polygon, parse_t3d
from uedcli.emit import emit_map
from uedcli.writes import exact_fit_cube_t3d

# A known-good 200^3 CSG_Add brush the editor itself produced (carries the
# Origin/Normal/TextureU/TextureV a brush needs to survive CSG). The IMPORTADD
# variant re-emits THIS through uedcli's own parse->emit path, exactly as
# add_actor does on real data — not a hand-built (texture-less) cube.
_TEMPLATE = parse_t3d(open("/home/human/src/dx_lum/Temp/good_brush.t3d").read())
_TEMPLATE_BRUSH = next(a for a in _TEMPLATE.actors.values() if a.brush)


def importadd_actor(name, loc):
    a = copy.deepcopy(_TEMPLATE_BRUSH)
    a.name = name
    a.location = loc
    return a

CONT = "dx-lum-uned"
WCTL = ["docker", "exec", CONT, "python3", "/repo/Extra/AI/wine_ctl.py"]
DELAY = 1.2


class EditorDead(RuntimeError):
    pass


def cube_faces(h):
    return [
        [(h, -h, -h), (h, h, -h), (h, h, h), (h, -h, h)],
        [(-h, h, -h), (-h, -h, -h), (-h, -h, h), (-h, h, h)],
        [(h, h, -h), (-h, h, -h), (-h, h, h), (h, h, h)],
        [(-h, -h, -h), (h, -h, -h), (h, -h, h), (-h, -h, h)],
        [(-h, -h, h), (h, -h, h), (h, h, h), (-h, h, h)],
        [(-h, h, -h), (h, h, -h), (h, -h, -h), (-h, -h, -h)],
    ]


def cube_actor(name, h, loc):
    polys = [Polygon(flags=0, vertices=f) for f in cube_faces(h)]
    return Actor(name=name, cls="Brush", location=loc,
                 props=[("CsgOper", "CSG_Add")], brush=Brush(model_name="Model", polys=polys))


COMPOSE_DIR = "/home/human/src/dx_lum/Extra/AI"
_crash_shots = [0]


def alive():
    """Alive AND driveable: process up and a real editor window resolved.
    The common failure is a zombie (process alive, window gone) — treat as dead."""
    r = subprocess.run(WCTL + ["status"], capture_output=True, text=True)
    return "alive=True" in r.stdout and "unresolved" not in r.stdout


def capture_crash(tag):
    """Full-display screenshot (grabs the wine error dialog) before we recreate."""
    n = _crash_shots[0]; _crash_shots[0] += 1
    cpath = f"/repo/Temp/crash_{n}_{tag}.png"
    subprocess.run(["docker", "exec", "-e", "DISPLAY=:99", CONT,
                    "import", "-window", "root", cpath], capture_output=True, text=True)
    subprocess.run(["docker", "cp", f"{CONT}:{cpath}",
                    f"/home/human/src/dx_lum/Temp/crash_{n}_{tag}.png"], capture_output=True, text=True)
    # also record any visible dialog window names
    w = subprocess.run(["docker", "exec", "-e", "DISPLAY=:99", CONT, "xdotool",
                        "search", "--onlyvisible", "--name", ".", "getwindowname", "%@"],
                       capture_output=True, text=True)
    print(f"    [crash captured -> Temp/crash_{n}_{tag}.png; windows: {w.stdout.split()}]", flush=True)


def restart_editor():
    print("    [restarting container…]", flush=True)
    subprocess.run(["docker", "compose", "up", "-d", "--force-recreate"],
                   cwd=COMPOSE_DIR, capture_output=True, text=True)
    for _ in range(50):
        if alive():
            time.sleep(2)
            print("    [editor back up]", flush=True)
            return True
        time.sleep(3)
    print("    [RESTART FAILED — editor did not come up]", flush=True)
    return False


def put(content, tag):
    path = f"/repo/Temp/mx_{tag}.t3d"
    subprocess.run(["docker", "exec", "-i", CONT, "tee", path],
                   input=content, text=True, capture_output=True, check=True)
    return "Z:\\repo\\Temp\\mx_" + tag + ".t3d"


def ex(line, check=True):
    subprocess.run(WCTL + ["exec", line], capture_output=True, text=True)
    time.sleep(DELAY)
    if check and not alive():
        raise EditorDead(f"editor died after: {line}")


def selection():
    r = subprocess.run(WCTL + ["edit-copy"], capture_output=True, text=True)
    time.sleep(DELAY)
    return sorted(set(re.findall(r"Begin Actor .*?Name=(\S+)", r.stdout)))


def actors_present():
    ex(r"MAP EXPORT FILE=Z:\repo\Temp\mx_state.t3d")
    r = subprocess.run(["docker", "exec", CONT, "grep", "-E", "Begin Actor",
                        "/repo/Temp/mx_state.t3d"], capture_output=True, text=True)
    return re.findall(r"Name=(\S+)", r.stdout)


def clear():
    ex("ACTOR SELECT ALL"); ex("ACTOR DELETE"); ex("MAP REBUILD"); time.sleep(1)


def place_builder(h, loc):
    p = put(exact_fit_cube_t3d((-h, -h, -h), (h, h, h), eps=0), f"box{h}")
    ex("MAP GRID X=1 Y=1 Z=1")
    ex(f"BRUSH IMPORT FILE={p}")
    ex(f"BRUSH MOVETO X={loc[0]} Y={loc[1]} Z={loc[2]}")


def probe(target, box_half, loc):
    place_builder(box_half, loc)
    ex("ACTOR SELECT NONE"); ex("ACTOR SELECT INSIDE")
    sel = selection()
    return target in sel, sel


BRUSH_HALF, LOC, ENCLOSE, TOOSMALL = 100, (0, 0, 0), 128, 90


def run_variant(label, method, rebuild):
    print(f"\n--- {label}", flush=True)
    clear()
    tname = "MXTARGET"
    if method == "importadd":
        p = put(emit_map([importadd_actor(tname, LOC)]), "ia")
        ex("MAP GRID X=1 Y=1 Z=1"); ex(f"MAP IMPORTADD FILE={p}")
    else:
        place_builder(BRUSH_HALF, LOC); ex("BRUSH ADD")
    if rebuild:
        ex("MAP REBUILD"); time.sleep(1)
    present = actors_present()
    target = tname if tname in present else next(
        (n for n in present if n.startswith("Brush") and n != "Brush1"), "?")
    print(f"    actor name: {target}   present: {present}", flush=True)
    enc_hit, enc_sel = probe(target, ENCLOSE, LOC)
    print(f"    256^3 enclosing -> selected={enc_hit}  read-back={enc_sel}", flush=True)
    sml_hit, sml_sel = probe(target, TOOSMALL, LOC)
    print(f"    180^3 too-small -> selected={sml_hit}  read-back={sml_sel}", flush=True)


def shot(tag):
    cp = f"/repo/Temp/{tag}.png"
    subprocess.run(WCTL + ["shot", cp], capture_output=True, text=True)
    subprocess.run(["docker", "cp", f"{CONT}:{cp}",
                    f"/home/human/src/dx_lum/Temp/{tag}.png"], capture_output=True, text=True)
    time.sleep(DELAY)


def camera_test():
    """Can a command move the viewport camera to an arbitrary position?
    Place a brush far from origin, then CAMERA ALIGN onto it (it's selected right
    after BRUSH ADD) — if the view jumps to X=2048, that's command-driven arbitrary
    camera positioning (via selection). Screenshots let us judge visually."""
    try:
        clear()
        shot("cam_0_origin")                 # baseline view (empty, camera at default)
        place_builder(BRUSH_HALF, (2048, 0, 0))
        ex("BRUSH ADD")                      # brush now at X=2048, selected
        shot("cam_1_far_noalign")            # camera hasn't moved yet
        ex("CAMERA ALIGN")                   # align viewports to the selected far brush
        shot("cam_2_far_aligned")            # camera should now be on X=2048
        print("    camera: placed brush @ X=2048, then CAMERA ALIGN.", flush=True)
        print("    compare Temp/cam_1_far_noalign.png (before) vs "
              "Temp/cam_2_far_aligned.png (after) — did the view jump to the brush?", flush=True)
    except EditorDead as e:
        print(f"    camera test crashed at: {e}", flush=True)
        capture_crash("camera")
        restart_editor()


def main():
    variants = [
        ("IMPORTADD, no rebuild", "importadd", False),
        ("IMPORTADD, rebuilt",    "importadd", True),
        ("BRUSH ADD, no rebuild", "brushadd",  False),
        ("BRUSH ADD, rebuilt",    "brushadd",  True),
    ]
    MAX_TRIES = 3
    print("===== SELECT INSIDE MATRIX =====", flush=True)
    print(f"target 200^3 (half {BRUSH_HALF}) @ {LOC}; enclosing 256^3 / too-small 180^3 @ {LOC}", flush=True)
    if not alive() and not restart_editor():
        print("cannot start editor", flush=True); return 1
    for label, method, rebuild in variants:
        for attempt in range(1, MAX_TRIES + 1):
            try:
                run_variant(f"{label} (try {attempt})", method, rebuild)
                break
            except EditorDead as e:
                print(f"    *** {e} ***", flush=True)
                capture_crash(method + ("_rb" if rebuild else ""))
                if attempt == MAX_TRIES:
                    print(f"    >>> RESULT: {label} — REPRODUCIBLY CRASHES the editor "
                          f"({MAX_TRIES} tries), last op: {e}", flush=True)
                if not restart_editor():
                    return 1
    print("\n===== camera-position test =====", flush=True)
    camera_test()
    print("\n===== MATRIX COMPLETE =====", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
