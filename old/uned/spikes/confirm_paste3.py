#!/usr/bin/env python3
"""Is the unselectability MY T3D's fault? Compare a genuine editor EDIT COPY
against my emit_map output, and paste the GENUINE clipboard back to test if it
stays selectable. If genuine-paste IS selectable, my emitted T3D is the problem.
"""
import subprocess
import sys
import select_matrix as M


def set_clipboard(content):
    subprocess.run(["docker", "exec", "-i", "-e", "DISPLAY=:99", M.CONT,
                    "xclip", "-selection", "clipboard", "-i"],
                   input=content, text=True, capture_output=True)


def names():
    M.ex("ACTOR SELECT NONE"); M.ex("ACTOR SELECT ALL")
    return set(M.selection())


for attempt in range(1, 4):
    try:
        M.restart_editor(); M.clear()
        # 1. make a real BRUSH ADD brush and capture the editor's OWN clipboard T3D
        M.place_builder(100, (0, 0, 0)); M.ex("BRUSH ADD")
        genuine = subprocess.run(M.WCTL + ["edit-copy"], capture_output=True, text=True).stdout
        open("/home/human/src/dx_lum/Temp/genuine_clip.t3d", "w").write(genuine)
        mine = M.emit_map([M.importadd_actor("PASTED", (0, 0, 0))])
        open("/home/human/src/dx_lum/Temp/mine_emit.t3d", "w").write(mine)
        print(f"=== GENUINE editor EDIT COPY ({len(genuine)} bytes) ===\n{genuine}", flush=True)
        print(f"=== MINE emit_map ({len(mine)} bytes) ===\n{mine}", flush=True)

        # 2. paste the GENUINE clipboard into a clean map and test selectability
        M.clear()
        before = names()
        set_clipboard(genuine)
        M.ex("EDIT PASTE")
        after = names()
        pasted = sorted(after - before)
        print(f"\nnames before paste: {sorted(before)}", flush=True)
        print(f"names after  paste: {sorted(after)}", flush=True)
        print(f"pasted (genuine) actor(s): {pasted}", flush=True)

        _, giant = M.probe("?", 2048, (0, 0, 0))
        print(f"\nGIANT ±2048 box SELECT INSIDE: {giant}", flush=True)
        print("\n--- CONCLUSION ---", flush=True)
        sel = any(n in giant for n in pasted)
        print(f"  GENUINE editor-copied brush, pasted, INSIDE-selectable? {sel}", flush=True)
        if sel:
            print("  => MY emit_map T3D is the problem (genuine paste IS selectable).", flush=True)
        else:
            print("  => Not my T3D — even genuine editor-copied paste is unselectable.", flush=True)
        sys.exit(0)
    except M.EditorDead as e:
        print(f"*** {e} (attempt {attempt}) ***", flush=True)
        M.capture_crash("paste3")
sys.exit(1)
