#!/usr/bin/env python3
"""Clean paste test — no broken clear(), fresh restart = genuinely empty map.
Tests the REBUILD hypothesis: does a pasted brush become INSIDE-selectable only
after MAP REBUILD? Also reports the post-paste auto-selection (paste selects the
new actor, so that alone proves it's selectable by SOME means).
"""
import subprocess
import sys
import select_matrix as M

GENUINE = open("/home/human/src/dx_lum/Temp/genuine_clip.t3d").read()


def set_clipboard(content):
    subprocess.run(["docker", "exec", "-i", "-e", "DISPLAY=:99", M.CONT,
                    "xclip", "-selection", "clipboard", "-i"],
                   input=content, text=True, capture_output=True)


def names():
    M.ex("ACTOR SELECT NONE"); M.ex("ACTOR SELECT ALL")
    return set(M.selection())


for attempt in range(1, 4):
    try:
        M.restart_editor()                 # fresh empty map — NO clear(), no pollution
        before = names()
        print(f"empty-map actors (just builder): {sorted(before)}", flush=True)

        set_clipboard(GENUINE)
        M.ex("EDIT PASTE")
        # paste auto-selects the new actor — read it directly off the clipboard
        post = subprocess.run(M.WCTL + ["edit-copy"], capture_output=True, text=True).stdout
        import re
        auto = sorted(set(re.findall(r"Begin Actor .*?Name=(\S+)", post)))
        after = names()
        pasted = sorted(after - before)
        print(f"\npost-paste AUTO-selection (paste selects new actor): {auto}", flush=True)
        print(f"names after paste: {sorted(after)}   -> pasted = {pasted}", flush=True)

        _, g_norb = M.probe("?", 2048, (0, 0, 0))
        print(f"\ngiant box, NO rebuild -> {g_norb}", flush=True)

        M.ex("MAP REBUILD")
        _, g_rb = M.probe("?", 2048, (0, 0, 0))
        print(f"giant box, AFTER rebuild -> {g_rb}", flush=True)

        print("\n--- CONCLUSION ---", flush=True)
        ps = pasted[0] if pasted else (auto[0] if auto else None)
        print(f"  pasted brush = {ps}", flush=True)
        print(f"  auto-selected by EDIT PASTE itself?   {bool(auto)}", flush=True)
        print(f"  INSIDE-selectable BEFORE rebuild?     {ps in g_norb if ps else '?'}", flush=True)
        print(f"  INSIDE-selectable AFTER rebuild?      {ps in g_rb if ps else '?'}", flush=True)
        sys.exit(0)
    except M.EditorDead as e:
        print(f"*** {e} (attempt {attempt}) ***", flush=True)
        M.capture_crash("paste4")
sys.exit(1)
