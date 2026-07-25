#!/usr/bin/env python3
"""Controlled test: does SET Camera ViewRotation in the LOG WINDOW console rotate the
live camera, tracking the Yaw value? (65536=360deg). Types into the engine console
(log window) — a different Exec path than the editor command box (where SET did nothing).
"""
import re
import subprocess
import sys
import select_matrix as M

DISP = ["-e", "DISPLAY=:99"]


def xdo(*args):
    subprocess.run(["docker", "exec", *DISP, M.CONT, "xdotool", *args],
                   capture_output=True, text=True)


def log_window():
    r = subprocess.run(["docker", "exec", *DISP, M.CONT, "xdotool", "search",
                        "--name", "Log Window"], capture_output=True, text=True)
    wid = r.stdout.split()[0]
    g = subprocess.run(["docker", "exec", *DISP, M.CONT, "xdotool",
                        "getwindowgeometry", "--shell", wid], capture_output=True, text=True).stdout
    d = dict(l.split("=", 1) for l in g.splitlines() if "=" in l)
    return wid, int(d["X"]), int(d["Y"]), int(d["WIDTH"]), int(d["HEIGHT"])


def gizmo(tag):
    subprocess.run(["docker", "exec", *DISP, M.CONT, "import", "-window", "root",
                    f"/repo/Temp/{tag}.png"], capture_output=True, text=True)
    subprocess.run(["docker", "exec", M.CONT, "convert", f"/repo/Temp/{tag}.png", "-crop",
                    "300x260+120+880", "+repage", "-resize", "240%", f"/repo/Temp/{tag}_g.png"],
                   capture_output=True, text=True)
    subprocess.run(["docker", "cp", f"{M.CONT}:/repo/Temp/{tag}_g.png",
                    f"/home/human/src/dx_lum/Temp/{tag}_g.png"], capture_output=True, text=True)


def console_cmd(wid, lx, ly, w, h, line):
    xdo("windowactivate", "--sync", wid)
    xdo("mousemove", str(lx + 10), str(ly + h - 12), "click", "1")   # the > prompt
    xdo("type", "--delay", "20", line)
    xdo("key", "Return")


for attempt in range(1, 3):
    try:
        M.restart_editor(); M.clear()
        M.place_builder(128, (0, 0, 0)); M.ex("BRUSH ADD"); M.ex("MAP REBUILD")
        M.ex("ACTOR SELECT NONE"); M.ex("ACTOR SELECT ALL"); M.ex("CAMERA ALIGN")
        gizmo("lc_base")
        wid, lx, ly, w, h = log_window()
        print(f"log window {wid} @ {lx},{ly} {w}x{h}", flush=True)
        for yaw in [0, 16384, 32768, 49152]:
            console_cmd(wid, lx, ly, w, h, f"SET Camera ViewRotation (Pitch=0,Yaw={yaw},Roll=0)")
            import time; time.sleep(1)
            gizmo(f"lc_yaw{yaw}")
            print(f"SET ... Yaw={yaw} -> Temp/lc_yaw{yaw}_g.png", flush=True)
        print("\nsaved lc_base + lc_yaw{0,16384,32768,49152}", flush=True)
        sys.exit(0)
    except M.EditorDead as e:
        print(f"*** {e} (attempt {attempt}) ***", flush=True)
        M.capture_crash("lcset")
sys.exit(1)
