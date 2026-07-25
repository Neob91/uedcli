#!/usr/bin/env python3
"""Spike: can we drive UnrealEd's native brush clipping headless?

Probe the BRUSH CLIP verb family: are they recognized? what do they do with no
clip markers set? Capture Editor.log lines after each to see how the editor reacts.
Then assess whether clip markers can be set without viewport clicks.
"""
import subprocess
import sys
import select_matrix as M


def log_tail(n=6):
    return subprocess.run(["docker", "exec", M.CONT, "tail", "-n", str(n),
                           "/opt/UED22/Editor.log"], capture_output=True, text=True).stdout


def poly_count():
    M.ex(r"MAP EXPORT FILE=Z:\repo\Temp\clip_state.t3d")
    r = subprocess.run(["docker", "exec", M.CONT, "grep", "-c", "Begin Polygon",
                        "/repo/Temp/clip_state.t3d"], capture_output=True, text=True)
    return r.stdout.strip()


def try_verb(v):
    before = log_tail(1)
    M.ex(v)
    print(f"\n>>> {v}", flush=True)
    print(f"    polys now: {poly_count()}", flush=True)
    print("    log tail:", flush=True)
    for ln in log_tail(5).splitlines():
        print(f"      {ln}", flush=True)


for attempt in range(1, 4):
    try:
        M.restart_editor(); M.clear()
        # a single CSG brush to clip
        M.place_builder(128, (0, 0, 0)); M.ex("BRUSH ADD"); M.ex("MAP REBUILD")
        print(f"baseline polys: {poly_count()}", flush=True)
        # select the brush (giant box)
        M.place_builder(2048, (0, 0, 0)); M.ex("ACTOR SELECT NONE"); M.ex("ACTOR SELECT INSIDE")
        print(f"selected: {M.selection()}", flush=True)

        # probe the clip verb family with NO markers set
        for v in ["BRUSH CLIP", "BRUSH CLIP SPLIT", "BRUSH CLIP FLIP", "BRUSH CLIP DELETE"]:
            try_verb(v)

        # probe candidate marker/mode commands (do they register / error?)
        for v in ["MODE CLIP", "BRUSHCLIP", "CLIP ADD", "MODE EDITMODE=12"]:
            try_verb(v)
        sys.exit(0)
    except M.EditorDead as e:
        print(f"*** {e} (attempt {attempt}) ***", flush=True)
        M.capture_crash("clipspike")
sys.exit(1)
