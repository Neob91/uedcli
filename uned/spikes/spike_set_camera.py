#!/usr/bin/env python3
"""Spike: does SET <class> ViewRotation/Rotation (Yaw=16384) rotate the camera?
Tested via the bottom Command box (UEditorEngine::Exec). Yaw=16384 = 90deg.
Reads the perspective orientation gizmo after each.
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


ROT = "(Pitch=0,Yaw=16384,Roll=0)"
forms = [
    ("set_cam_viewrot", f"SET Camera ViewRotation {ROT}"),
    ("set_cam_rot",     f"SET Camera Rotation {ROT}"),
    ("set_engcam_vr",   f"SET Engine.Camera ViewRotation {ROT}"),
    ("set_pawn_vr",     f"SET Pawn ViewRotation {ROT}"),
    ("set_spect_vr",    f"SET Spectator ViewRotation {ROT}"),
]

for attempt in range(1, 3):
    try:
        M.restart_editor(); M.clear()
        M.place_builder(128, (0, 0, 0)); M.ex("BRUSH ADD"); M.ex("MAP REBUILD")
        M.ex("ACTOR SELECT NONE"); M.ex("ACTOR SELECT ALL"); M.ex("CAMERA ALIGN")
        gizmo("set_base")
        for tag, cmd in forms:
            M.ex(cmd)
            gizmo(tag)
            print(f"issued: {cmd}  -> Temp/{tag}_g.png", flush=True)
        print("\nsaved: set_base + per-form gizmo crops", flush=True)
        sys.exit(0)
    except M.EditorDead as e:
        print(f"*** {e} (attempt {attempt}) ***", flush=True)
        M.capture_crash("setcam")
sys.exit(1)
