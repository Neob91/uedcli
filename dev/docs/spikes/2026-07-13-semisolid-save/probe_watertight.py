#!/usr/bin/env python3
r"""Linchpin test: is the world BSP `Model`'s OBJ DEPENDENCIES `Engine.Polys` block
EMPTY for a clean watertight (pure-subtractive) level, but NON-EMPTY once a
free-standing additive (esp. semisolid) brush is present? That empty-vs-non-empty
of the ONE world-Model block is exactly what makes qualify_level_textures balance
(N brushes == N non-empty blocks) or raise (N vs N+1).

Scenarios (textured, real LUM_CoreTex loaded):
  W1 lone subtracted room                          -> brushes=1
  W2 two subtracted rooms (still watertight)       -> brushes=2
  W3 room + 1 SOLID free add                       -> brushes=2
  W4 room + 1 SEMISOLID free add                   -> brushes=2
For each: non-empty Engine.Polys blocks and whether qualify raises.

    UEDCLI_REUSE_EDITOR=uned-<uuid> PYTHONPATH=. python3 .../probe_watertight.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid

from uedcli import builders, writes
from uedcli.driver import Driver, to_z_path
from uedcli.model import Level
from uedcli.qualify import dump_obj_dependencies, parse_obj_dependencies, qualify_level_textures
from uedcli.uuid7 import uuid7
from uedcli.editor import ensure_editor, stop_editor

TEX_HOST = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Textures/LUM_CoreTex.utx"
TEXNAME = "LUM_CoreTex.grey_stone_tile"


def log(*a):
    print(*a, flush=True)


def settle(ed, s=2.0):
    time.sleep(s)
    try:
        ed.dismiss_blocking_dialog()
    except Exception:
        pass


def load_texture(ed):
    cwork = f"/work/LUM_CoreTex_{uuid.uuid4().hex}.utx"
    subprocess.run(["docker", "cp", TEX_HOST, f"{ed.container}:{cwork}"], check=True,
                   capture_output=True, text=True)
    ed.exec(f"OBJ LOAD FILE={to_z_path(cwork)} PACKAGE=LUM_CoreTex"); settle(ed)


def sub_room(name, at, w=1024, b=1024, h=512):
    return builders.make_brush_actor(name, builders.cube(w, b, h, texture=TEXNAME),
                                     location=at, csg="subtract")


def add_cube(name, solidity, at):
    return builders.make_brush_actor(name, builders.cube(128, 128, 128, texture=TEXNAME),
                                     location=at, csg="add",
                                     poly_flags=builders.SOLIDITY_FLAGS[solidity])


def probe(ed, tag, actors):
    log(f"\n===== {tag} =====")
    ed.map_new(); settle(ed)
    writes._re_add(ed, actors); settle(ed)
    ed.rebuild(); settle(ed, 3.0)
    blocks = parse_obj_dependencies(dump_obj_dependencies(ed))
    non_empty = [b for b in blocks if b]
    log(f"  blocks={len(blocks)} non_empty={len(non_empty)} sizes={[len(b) for b in blocks]}")
    lv = Level()
    for a in actors:
        lv.actors[a.name] = a
    lv.order = [a.name for a in actors]
    textured = [n for n in lv.order if lv.actors[n].brush is not None
                and any(p.texture is not None for p in lv.actors[n].brush.polys)]
    try:
        qualify_level_textures(lv, blocks)
        log(f"  textured_brushes={len(textured)} qualify=OK")
    except Exception as e:
        log(f"  textured_brushes={len(textured)} qualify=RAISED: {e}")


def main():
    reuse = os.environ.get("UEDCLI_REUSE_EDITOR")
    ed_id = None
    if reuse:
        container = reuse; log(f"REUSING {container}")
    else:
        ed_id = uuid7(); container = ensure_editor(ed_id, ready_timeout=120.0)
    ed = Driver(container=container)
    try:
        load_texture(ed)
        probe(ed, "W1_lone_room", [sub_room("Room", (0, 0, 0))])
        probe(ed, "W2_two_rooms", [sub_room("Room", (0, 0, 0)),
                                   sub_room("Room2", (1200, 0, 0))])
        probe(ed, "W3_room_plus_solid_add", [sub_room("Room", (0, 0, 0)),
                                             add_cube("Add", "solid", (0, 0, 0))])
        probe(ed, "W4_room_plus_semisolid_add", [sub_room("Room", (0, 0, 0)),
                                                 add_cube("SS", "semisolid", (0, 0, 0))])
    finally:
        if ed_id is not None:
            stop_editor(ed_id); log("editor torn down")
        else:
            log("(reused editor left running)")


if __name__ == "__main__":
    sys.exit(main())
