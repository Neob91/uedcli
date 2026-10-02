#!/usr/bin/env python3
"""Definitive: paste with UNIQUE names (no Brush0/Brush1 ambiguity), fresh restart
each time. Compare GENUINE editor clip vs MY emit_map — both renamed uniquely —
and check the literal unique name in the giant-box INSIDE selection.
"""
import re
import subprocess
import sys
import select_matrix as M

GENUINE = open("/home/human/src/dx_lum/Temp/genuine_clip.t3d").read()
# rename the genuine clip's actor to a unique, collision-free name
GENU = GENUINE.replace("Name=Brush0", "Name=GENU").replace('Name="Brush0"', 'Name="GENU"')
MINE = M.emit_map([M.importadd_actor("MINE", (0, 0, 0))])


def set_clipboard(content):
    subprocess.run(["docker", "exec", "-i", "-e", "DISPLAY=:99", M.CONT,
                    "xclip", "-selection", "clipboard", "-i"],
                   input=content, text=True, capture_output=True)


def run_one(label, content, uniq):
    M.restart_editor()                       # fresh empty map
    set_clipboard(content)
    M.ex("EDIT PASTE")
    post = subprocess.run(M.WCTL + ["edit-copy"], capture_output=True, text=True).stdout
    auto = sorted(set(re.findall(r"Begin Actor .*?Name=(\S+)", post)))
    M.ex("MAP REBUILD")
    _, giant = M.probe(uniq, 2048, (0, 0, 0))
    print(f"\n[{label}] paste name expected={uniq}", flush=True)
    print(f"   post-paste auto-selection: {auto}", flush=True)
    print(f"   giant box (rebuilt) INSIDE: {giant}", flush=True)
    print(f"   ==> '{uniq}' INSIDE-selectable? {uniq in giant}", flush=True)
    return uniq in giant


for attempt in range(1, 4):
    try:
        g = run_one("GENUINE editor clip", GENU, "GENU")
        m = run_one("MY emit_map", MINE, "MINE")
        print("\n===== VERDICT =====", flush=True)
        print(f"  genuine editor-copied brush INSIDE-selectable after paste? {g}", flush=True)
        print(f"  my emit_map brush INSIDE-selectable after paste?          {m}", flush=True)
        if g and not m:
            print("  => MY emitted T3D is broken (genuine works, mine doesn't).", flush=True)
        elif g and m:
            print("  => Both selectable — earlier 'no' was name-tracking confusion.", flush=True)
        elif not g and not m:
            print("  => Neither selectable via INSIDE after paste — needs deeper look.", flush=True)
        sys.exit(0)
    except M.EditorDead as e:
        print(f"*** {e} (attempt {attempt}) ***", flush=True)
        M.capture_crash("paste5")
sys.exit(1)
