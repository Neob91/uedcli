#!/usr/bin/env python3
"""Find which emit_map difference breaks INSIDE-selectability. Bisect by pasting
variants of my T3D (unique names, fresh restart, rebuild) and checking selection.
Prime suspect: the `Brush=Model'..'` reference emitted BEFORE the Begin Brush block.
"""
import re
import subprocess
import sys
import select_matrix as M

BREF = "Brush=Model'MyLevel.Brush'"


def variant(name, *, brush_ref="before", location=True):
    """Build a paste T3D for a cube brush named `name` with the Brush= line placed
    before/after/omitted, and Location present or not."""
    lines = M.emit_map([M.importadd_actor(name, (0, 0, 0))]).splitlines()
    out = []
    for ln in lines:
        s = ln.strip()
        if s == BREF:                       # drop wherever emit put it; re-add per policy
            continue
        if not location and s.startswith("Location="):
            continue
        out.append(ln)
        if brush_ref == "after" and s == "End Brush":
            out.append(f"    {BREF}")
    if brush_ref == "before":               # restore emit's original placement (control = mine)
        for i, ln in enumerate(out):
            if ln.strip().startswith("Begin Brush"):
                out.insert(i, f"    {BREF}"); break
    return "\n".join(out) + "\n"


GENUINE = open("/home/human/src/dx_lum/Temp/genuine_clip.t3d").read()
GENU = GENUINE.replace("Name=Brush0", "Name=GENU").replace('Name="Brush0"', 'Name="GENU"')


def set_clipboard(content):
    subprocess.run(["docker", "exec", "-i", "-e", "DISPLAY=:99", M.CONT,
                    "xclip", "-selection", "clipboard", "-i"],
                   input=content, text=True, capture_output=True)


def test(label, content, uniq):
    M.restart_editor()
    set_clipboard(content)
    M.ex("EDIT PASTE"); M.ex("MAP REBUILD")
    _, giant = M.probe(uniq, 2048, (0, 0, 0))
    ok = uniq in giant
    print(f"[{label:28}] giant INSIDE={giant} -> {uniq} selectable? {ok}", flush=True)
    return ok


cases = [
    ("GENUINE control", GENU, "GENU"),
    ("mine: Brush ref BEFORE", variant("MINEB", brush_ref="before"), "MINEB"),
    ("mine: Brush ref AFTER", variant("MINEA", brush_ref="after"), "MINEA"),
    ("mine: no Brush ref", variant("MINEN", brush_ref="omit"), "MINEN"),
    ("mine: no Brush, no Loc", variant("MINEX", brush_ref="omit", location=False), "MINEX"),
]

for attempt in range(1, 3):
    try:
        results = {}
        for label, content, uniq in cases:
            results[label] = test(label, content, uniq)
        print("\n===== SUMMARY =====", flush=True)
        for label in results:
            print(f"  {label:28} selectable={results[label]}", flush=True)
        sys.exit(0)
    except M.EditorDead as e:
        print(f"*** {e} (attempt {attempt}) ***", flush=True)
        M.capture_crash("emitfix")
sys.exit(1)
