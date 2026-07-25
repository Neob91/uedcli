#!/usr/bin/env python3
"""EXP3: characterize the whole-level-import path for updating LevelInfo.

Q1. MAP IMPORT (replace) vs MAP IMPORTADD (add) of a T3D carrying a LevelInfo:
    does each yield exactly ONE LevelInfo with the authored fields? duplicate?
Q2. Does replacement depend on the imported LevelInfo's NAME matching the
    editor's default (LevelInfoN)? Try importing one named LevelInfo0 onto a
    default that is LevelInfoN (mismatched), and check the count + which fields.
Q3. DeusExLevelInfo subclass — does importing Class=DeusExLevelInfo work, and
    does it coexist with / replace the auto-created stock LevelInfo?
"""
import re
import sys
import lidrv as L

AUTHORED_FIELDS = (
    '     Title="SpikeTest"\n'
    '     Author="uedctl"\n'
    "     AmbientBrightness=42\n"
    "     FogDistance=1337.000000\n"
    "     ZoneGravity=(X=0.000000,Y=0.000000,Z=-666.000000)\n"
    "     bLonePlayer=True\n"
    "     IdealPlayerCount=\"3-4\"\n"
)


def li_actor(name, cls="LevelInfo"):
    return (
        "Begin Map\n"
        f"Begin Actor Class={cls} Name={name}\n"
        + AUTHORED_FIELDS +
        f'     Name="{name}"\n'
        "End Actor\n"
        "End Map\n"
    )


def report(tag, t3d):
    heads = L.all_actor_headers(t3d)
    nli = len([h for h in heads if "LevelInfo" in h[0]])
    print(f"\n===== {tag} =====", flush=True)
    print(f"  headers={heads}  | #LevelInfo actors={nli}", flush=True)
    print(L.levelinfo_block(t3d), flush=True)
    return nli


try:
    # Q1a: MAP IMPORT (replace whole level) carrying a LevelInfo
    p = L.put(li_actor("LevelInfo0"), "imp")
    L.ex("MAP NEW")
    L.ex("MAP GRID X=1 Y=1 Z=1")
    L.ex(f"MAP IMPORT FILE={p}")
    report("Q1a MAP IMPORT (replace) LevelInfo0", L.export("q1a"))

    # Q1b: MAP IMPORTADD carrying a LevelInfo named LevelInfo0
    L.ex("MAP NEW")
    cur = L.export("q1b_pre")
    pre_name = re.search(r"Class=(?:DeusEx)?LevelInfo Name=(\S+)", cur).group(1)
    print(f"\n[Q1b] pre-import default LevelInfo name = {pre_name}", flush=True)
    L.ex("MAP GRID X=1 Y=1 Z=1")
    L.ex(f"MAP IMPORTADD FILE={p}")
    report(f"Q1b MAP IMPORTADD LevelInfo0 (default was {pre_name})", L.export("q1b"))

    # Q2: mismatched name — import a LevelInfo named ZZ_Authored
    p2 = L.put(li_actor("ZZ_Authored"), "imp2")
    L.ex("MAP NEW")
    cur = L.export("q2_pre")
    pre_name = re.search(r"Class=(?:DeusEx)?LevelInfo Name=(\S+)", cur).group(1)
    print(f"\n[Q2] pre-import default LevelInfo name = {pre_name}", flush=True)
    L.ex("MAP GRID X=1 Y=1 Z=1")
    L.ex(f"MAP IMPORTADD FILE={p2}")
    report(f"Q2 IMPORTADD a mismatched-name LevelInfo (default {pre_name})", L.export("q2"))

    print("\nDONE exp3", flush=True)
except L.EditorDead as e:
    print(f"*** EDITOR DIED: {e}", flush=True)
    sys.exit(1)
