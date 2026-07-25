#!/usr/bin/env python3
"""Clean EDIT PASTE selectability check — unambiguous name tracking.

1. EDIT PASTE a brush named PASTED; record names present (SELECT ALL).
2. BRUSH ADD a control; the NEW name = (names after) - (names before) = the control.
3. Giant ±2048 box SELECT INSIDE; check the literal name PASTED and the control.
"""
import subprocess
import sys
import select_matrix as M
from uedctl.model import parse_t3d


def set_clipboard(content):
    subprocess.run(["docker", "exec", "-i", "-e", "DISPLAY=:99", M.CONT,
                    "xclip", "-selection", "clipboard", "-i"],
                   input=content, text=True, capture_output=True)


def select_all_names():
    M.ex("ACTOR SELECT NONE"); M.ex("ACTOR SELECT ALL")
    return set(M.selection())


for attempt in range(1, 4):
    try:
        M.restart_editor(); M.clear()
        set_clipboard(M.emit_map([M.importadd_actor("PASTED", (0, 0, 0))]))
        M.ex("EDIT PASTE")
        raw = subprocess.run(M.WCTL + ["edit-copy"], capture_output=True, text=True).stdout
        ploc = next(iter(parse_t3d(raw).actors.values()), None)
        print(f"\npaste drift: emitted (0,0,0) -> landed {ploc.location if ploc else '?'}", flush=True)

        before = select_all_names()
        M.place_builder(100, (700, 0, 0)); M.ex("BRUSH ADD")
        after = select_all_names()
        control = (after - before)            # the BRUSH ADD brush's new name
        print(f"\nnames before BRUSH ADD: {sorted(before)}", flush=True)
        print(f"names after  BRUSH ADD: {sorted(after)}", flush=True)
        print(f"BRUSH ADD control name = {sorted(control)}", flush=True)

        _, giant = M.probe("PASTED", 2048, (0, 0, 0))
        print(f"\nGIANT ±2048 box SELECT INSIDE: {giant}", flush=True)
        ctrl = next(iter(control), None)
        print("\n--- CONCLUSION ---", flush=True)
        print(f"  EDIT PASTE brush 'PASTED' INSIDE-selectable? {'PASTED' in giant}", flush=True)
        print(f"  BRUSH ADD control {ctrl!r} INSIDE-selectable? {ctrl in giant if ctrl else 'n/a'}", flush=True)
        sys.exit(0)
    except M.EditorDead as e:
        print(f"*** {e} (attempt {attempt}) ***", flush=True)
        M.capture_crash("paste2")
sys.exit(1)
