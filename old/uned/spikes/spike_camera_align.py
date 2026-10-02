#!/usr/bin/env python3
"""Spike: camera rotation after CAMERA ALIGN. Build an ASYMMETRIC scene (big cube +
small cube offset in +X) so orientation is readable, align, screenshot. Repeat at a
far position. If the perspective pane looks the SAME at both, rotation is a world-fixed
default (align repositions only); if different, rotation tracks the target.
"""
import subprocess
import sys
import select_matrix as M


def build_marker_scene(cx):
    """Big 256^3 cube at (cx,0,0) + small 96^3 cube at (cx+400,0,0) marking +X.
    BRUSH ADD (selectable, no paste needed for a viewing spike)."""
    for half, x in [(128, cx), (48, cx + 400)]:
        box = M.exact_fit_cube_t3d((-half, -half, -half), (half, half, half), eps=0)
        p = M.put(box, f"mk{half}")
        M.ex("MAP GRID X=1 Y=1 Z=1"); M.ex(f"BRUSH IMPORT FILE={p}")
        M.ex(f"BRUSH MOVETO X={x} Y=0 Z=0"); M.ex("BRUSH ADD")


def shot(tag):
    cp = f"/repo/Temp/{tag}.png"
    subprocess.run(M.WCTL + ["shot", cp], capture_output=True, text=True)
    # crop the perspective pane (bottom-left "Dynamic Light"), upscale
    subprocess.run(["docker", "exec", M.CONT, "convert", cp, "-crop",
                    "960x590+120+595", "+repage", "-resize", "150%", f"/repo/Temp/{tag}_persp.png"],
                   capture_output=True, text=True)
    subprocess.run(["docker", "cp", f"{M.CONT}:/repo/Temp/{tag}_persp.png",
                    f"/home/human/src/dx_lum/Temp/{tag}_persp.png"], capture_output=True, text=True)
    subprocess.run(["docker", "cp", f"{M.CONT}:{cp}",
                    f"/home/human/src/dx_lum/Temp/{tag}.png"], capture_output=True, text=True)


for attempt in range(1, 4):
    try:
        M.restart_editor(); M.clear()
        build_marker_scene(0)
        M.ex("ACTOR SELECT NONE"); M.ex("ACTOR SELECT ALL"); M.ex("CAMERA ALIGN")
        print(f"scene@origin SELECT ALL: {M.selection()}", flush=True)
        shot("camspike_origin")

        M.clear()
        build_marker_scene(4000)
        M.ex("ACTOR SELECT NONE"); M.ex("ACTOR SELECT ALL"); M.ex("CAMERA ALIGN")
        print(f"scene@4000 SELECT ALL: {M.selection()}", flush=True)
        shot("camspike_far")
        print("saved Temp/camspike_origin{,_persp}.png and camspike_far{,_persp}.png", flush=True)
        sys.exit(0)
    except M.EditorDead as e:
        print(f"*** {e} (attempt {attempt}) ***", flush=True)
        M.capture_crash("camspike")
sys.exit(1)
