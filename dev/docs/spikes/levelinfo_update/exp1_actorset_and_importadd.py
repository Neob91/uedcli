#!/usr/bin/env python3
"""EXP1: baseline + does NEW+IMPORTADD duplicate LevelInfo? + ACTOR SET in-place.

Steps:
  A. MAP NEW -> export baseline default LevelInfo (what fields a fresh actor 0 has).
  B. MAP IMPORTADD a T3D carrying an authored LevelInfo block -> does it ADD a
     second LevelInfo (duplicate), overwrite the existing one, or get rejected?
  C. On a fresh MAP NEW, SELECTNAME the LevelInfo then ACTOR SET Title/Author/etc.,
     re-export, and check whether the fields stuck.
"""
import sys
import lidrv as L


def show(tag, t3d):
    print(f"\n===== {tag}: actor headers = {L.all_actor_headers(t3d)} =====", flush=True)
    print(L.levelinfo_block(t3d), flush=True)


try:
    # ---------- A. baseline ----------
    L.ex("MAP NEW")
    base = L.export("base")
    show("A baseline (MAP NEW default LevelInfo)", base)

    # ---------- B. NEW + IMPORTADD an authored LevelInfo ----------
    authored = (
        "Begin Map\n"
        "Begin Actor Class=LevelInfo Name=LevelInfo0\n"
        '     Title="SpikeTest"\n'
        '     Author="uedcli"\n'
        "     AmbientBrightness=42\n"
        "     FogDistance=1337.000000\n"
        "     ZoneGravity=(X=0.000000,Y=0.000000,Z=-666.000000)\n"
        '     Name="LevelInfo0"\n'
        "End Actor\n"
        "End Map\n"
    )
    p = L.put(authored, "authored")
    L.ex("MAP NEW")
    L.ex("MAP GRID X=1 Y=1 Z=1")
    L.ex(f"MAP IMPORTADD FILE={p}")
    after_add = L.export("after_importadd")
    show("B after NEW + IMPORTADD authored LevelInfo0", after_add)
    li_count = after_add.count("Class=LevelInfo")
    print(f"\n[B] LevelInfo actor count after IMPORTADD = {li_count} "
          f"(1=overwrite/merge, 2=duplicate)", flush=True)

    # ---------- C. ACTOR SET in place on the default LevelInfo ----------
    L.ex("MAP NEW")
    L.ex("SELECTNAME NAME=LevelInfo0")
    # try a few SET forms via ACTOR SET
    for cmd in [
        'ACTOR SET Title "InPlaceTitle"',
        'ACTOR SET Author "ipAuthor"',
        "ACTOR SET AmbientBrightness 77",
        "ACTOR SET FogDistance 2048",
    ]:
        L.ex(cmd)
    after_set = L.export("after_actorset")
    show("C after SELECTNAME LevelInfo0 + ACTOR SET", after_set)

    print("\nDONE exp1", flush=True)
except L.EditorDead as e:
    print(f"*** EDITOR DIED: {e}", flush=True)
    sys.exit(1)
