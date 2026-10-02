#!/usr/bin/env python3
"""Spike: can CAMERAMOVE set an EXACT camera rotation (reliable 90deg)?
Unreal rotation units: 65536 = 360deg, so Yaw=16384 is exactly 90deg.
Issue CAMERAMOVE variants, crop the perspective orientation gizmo to read rotation.
"""
import subprocess
import sys
import select_matrix as M


def gizmo(tag):
    cp = f"/repo/Temp/{tag}.png"
    subprocess.run(M.WCTL + ["shot", cp], capture_output=True, text=True)
    subprocess.run(["docker", "exec", M.CONT, "convert", cp, "-crop",
                    "300x260+120+880", "+repage", "-resize", "260%", f"/repo/Temp/{tag}_g.png"],
                   capture_output=True, text=True)
    subprocess.run(["docker", "cp", f"{M.CONT}:/repo/Temp/{tag}_g.png",
                    f"/home/human/src/dx_lum/Temp/{tag}_g.png"], capture_output=True, text=True)


for attempt in range(1, 3):
    try:
        M.restart_editor(); M.clear()
        M.place_builder(128, (0, 0, 0)); M.ex("BRUSH ADD"); M.ex("MAP REBUILD")
        M.ex("ACTOR SELECT NONE"); M.ex("ACTOR SELECT ALL"); M.ex("CAMERA ALIGN")
        gizmo("cm_base")
        forms = [
            ("cm_yaw90",  "CAMERAMOVE X=0 Y=0 Z=256 Pitch=0 Yaw=16384 Roll=0"),
            ("cm_yaw180", "CAMERAMOVE X=0 Y=0 Z=256 Pitch=0 Yaw=32768 Roll=0"),
            ("cm_pitch90","CAMERAMOVE X=0 Y=0 Z=256 Pitch=16384 Yaw=0 Roll=0"),
            ("cm_nokeys", "CAMERAMOVE"),
        ]
        for tag, cmd in forms:
            M.ex(cmd)
            gizmo(tag)
            print(f"issued: {cmd}  -> Temp/{tag}_g.png", flush=True)
        print("\nsaved gizmo crops: cm_base, cm_yaw90, cm_yaw180, cm_pitch90, cm_nokeys", flush=True)
        sys.exit(0)
    except M.EditorDead as e:
        print(f"*** {e} (attempt {attempt}) ***", flush=True)
        M.capture_crash("cameramove")
sys.exit(1)
