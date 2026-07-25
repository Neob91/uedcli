#!/usr/bin/env python3
"""EXP5: (a) DeusExLevelInfo subclass import; (b) the log-window SET console form
on a live LevelInfo instance (mechanism 2), to confirm it does NOT update the
instance (touches the class default).
"""
import re
import subprocess
import sys
import time
import lidrv as L

CONT = L.CONT
DISP = ["-e", "DISPLAY=:99"]


def log_console(line):
    """Type a command into the engine LOG WINDOW console (> prompt)."""
    r = subprocess.run(["docker", "exec", *DISP, CONT, "xdotool", "search",
                        "--name", "Log"], capture_output=True, text=True)
    wid = r.stdout.split()[0] if r.stdout.split() else None
    if not wid:
        print("  [no Log window found]", flush=True)
        return
    g = subprocess.run(["docker", "exec", *DISP, CONT, "xdotool",
                        "getwindowgeometry", "--shell", wid], capture_output=True, text=True).stdout
    d = dict(l.split("=", 1) for l in g.splitlines() if "=" in l)
    lx, ly, w, h = int(d["X"]), int(d["Y"]), int(d["WIDTH"]), int(d["HEIGHT"])
    subprocess.run(["docker", "exec", *DISP, CONT, "xdotool", "windowactivate", "--sync", wid],
                   capture_output=True, text=True)
    subprocess.run(["docker", "exec", *DISP, CONT, "xdotool", "mousemove",
                    str(lx + 20), str(ly + h - 12), "click", "1"], capture_output=True, text=True)
    subprocess.run(["docker", "exec", *DISP, CONT, "xdotool", "type", "--delay", "20", line],
                   capture_output=True, text=True)
    subprocess.run(["docker", "exec", *DISP, CONT, "xdotool", "key", "Return"],
                   capture_output=True, text=True)
    time.sleep(1)


try:
    # (a) DeusExLevelInfo subclass — does the editor accept importing the subclass?
    dxli = (
        "Begin Map\n"
        "Begin Actor Class=DeusExLevelInfo Name=DeusExLevelInfo0\n"
        '     Title="DXSpike"\n'
        '     Author="uedctl"\n'
        "     AmbientBrightness=33\n"
        '     Name="DeusExLevelInfo0"\n'
        "End Actor\n"
        "End Map\n"
    )
    p = L.put(dxli, "dxli")
    L.ex("MAP NEW")
    L.ex("MAP GRID X=1 Y=1 Z=1")
    L.ex(f"MAP IMPORT FILE={p}")
    t = L.export("dxli")
    print("=== (a) after MAP IMPORT DeusExLevelInfo0 ===", flush=True)
    print(f"  headers={L.all_actor_headers(t)}", flush=True)
    print(L.levelinfo_block(t), flush=True)

    # (b) log-window SET on the live LevelInfo instance.
    L.ex("MAP NEW")
    cur = L.export("set_pre")
    name = re.search(r"Class=(?:DeusEx)?LevelInfo Name=(\S+)", cur).group(1)
    print(f"\n=== (b) live LevelInfo name = {name}; trying log-window SET ===", flush=True)
    log_console(f'SET {name} Title "ConsoleSetTitle"')
    log_console(f"SET {name} AmbientBrightness 99")
    log_console(f'SET LevelInfo Title "ClassDefaultTitle"')   # class-default form
    after = L.export("set_after")
    print(L.levelinfo_block(after), flush=True)
    stuck = ('Title="ConsoleSetTitle"' in after) or ("AmbientBrightness=99" in after)
    print(f"\n  [b] did log-window SET update the instance? {stuck}", flush=True)

    print("\nDONE exp5", flush=True)
except L.EditorDead as e:
    print(f"*** EDITOR DIED: {e}", flush=True)
    sys.exit(1)
