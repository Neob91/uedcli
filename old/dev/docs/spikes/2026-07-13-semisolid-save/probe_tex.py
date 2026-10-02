#!/usr/bin/env python3
r"""Spike harness part 5 — THE ROOT CAUSE TEST.

Geometry saves fine (probe_full.py); the real materialize failure is in uedcli's
TEXTURE-QUALIFY step. `qualify_level_textures` demands a 1:1 match between the
level's textured brushes and the NON-EMPTY `Class Engine.Polys` blocks that `OBJ
DEPENDENCIES PACKAGE=MyLevel` dumps. Hypothesis: a SEMISOLID (or NONSOLID) brush
makes the world BSP `Model` retain textured surfaces, so it exports as an EXTRA
non-empty Engine.Polys block with no authored brush to correlate to -> count
mismatch -> qualify raises -> materialize aborts with NO .dx written (which reads
as "MAP SAVE produced no file").

This loads the REAL LUM_CoreTex package and, for solid / semisolid / nonsolid
detail, dumps OBJ DEPENDENCIES the exact way qualify does and reports:
  * total Engine.Polys blocks, non-empty count, and how many textured brushes
    uedcli counts (the two numbers qualify compares)
  * whether qualify_level_textures() RAISES.

    UEDCLI_REUSE_EDITOR=uned-<uuid> PYTHONPATH=. python3 .../probe_tex.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from uedcli import builders, writes
from uedcli.driver import Driver, to_z_path
from uedcli.model import Level, parse_t3d
from uedcli.qualify import (dump_obj_dependencies, parse_obj_dependencies,
                            qualify_level_textures)
from uedcli.uuid7 import uuid7
from uedcli.editor import ensure_editor, stop_editor

TEX_HOST = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Textures/LUM_CoreTex.utx"
TEXNAME = "LUM_CoreTex.grey_stone_tile"


def log(*a):
    print(*a, flush=True)


def settle(ed, s=2.0):
    time.sleep(s)
    try:
        if ed.dismiss_blocking_dialog():
            log("  [dismissed GC dialog]"); time.sleep(1.0)
    except Exception as e:
        log(f"  [dismiss failed: {e}]")


def add(ed, actors):
    writes._re_add(ed, actors); settle(ed)


def load_texture(ed):
    cwork = f"/work/LUM_CoreTex_{uuid.uuid4().hex}.utx"
    subprocess.run(["docker", "cp", TEX_HOST, f"{ed.container}:{cwork}"],
                   check=True, capture_output=True, text=True)
    ed.exec(f"OBJ LOAD FILE={to_z_path(cwork)} PACKAGE=LUM_CoreTex")
    settle(ed, 2.0)
    log(f"  OBJ LOADed LUM_CoreTex from {cwork}")


def room():
    b = builders.cube(1024, 1024, 512, texture=TEXNAME)
    return builders.make_brush_actor("Room", b, location=(0, 0, 0), csg="subtract")


def cube(name, solidity, at):
    b = builders.cube(128, 128, 128, texture=TEXNAME)
    return builders.make_brush_actor(name, b, location=at, csg="add",
                                     poly_flags=builders.SOLIDITY_FLAGS[solidity])


def build_level_model(actors):
    lv = Level()
    for a in actors:
        lv.actors[a.name] = a
    lv.order = [a.name for a in actors]
    return lv


def csize(c, p):
    r = subprocess.run(["docker", "exec", c, "stat", "-c", "%s", p],
                       capture_output=True, text=True, check=False)
    return int(r.stdout.strip()) if r.returncode == 0 else None


def scenario(ed, tag, solidity):
    log(f"\n===== {tag} (detail={solidity}) =====")
    ed.map_new(); settle(ed)
    actors = [room(), cube("D0", solidity, (0, 0, 0)), cube("D1", solidity, (256, 0, 0))]
    add(ed, actors)
    ed.rebuild(); settle(ed, 3.0)

    # Dump OBJ DEPENDENCIES exactly as qualify does.
    try:
        dump = dump_obj_dependencies(ed)
        blocks = parse_obj_dependencies(dump)
        non_empty = [b for b in blocks if b]
        log(f"  OBJ DEPENDENCIES: {len(blocks)} Engine.Polys blocks, {len(non_empty)} non-empty")
        for i, b in enumerate(blocks):
            log(f"    block[{i}]: {len(b)} textures {b[:3]}{'...' if len(b) > 3 else ''}")
        # how many textured brushes uedcli counts (the OTHER side of the correlation)
        lv = build_level_model(actors)
        textured = [n for n in lv.order if lv.actors[n].brush is not None
                    and any(p.texture is not None for p in lv.actors[n].brush.polys)]
        log(f"  uedcli textured brushes in order: {len(textured)} ({textured})")
        try:
            qualify_level_textures(lv, blocks)
            log("  qualify_level_textures: OK (no raise)")
        except Exception as e:
            log(f"  qualify_level_textures: RAISED -> {e}")
    except Exception as e:
        log(f"  OBJ DEPENDENCIES failed: {e}")

    # And confirm the raw editor MAP SAVE still works (geometry).
    cwork = f"/work/{tag}_{uuid.uuid4().hex}.dx"
    ed.exec(f"MAP SAVE FILE={to_z_path(cwork)}"); settle(ed, 2.0)
    log(f"  raw MAP SAVE exists={csize(ed.container, cwork) is not None}")


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
        scenario(ed, "TEX_solid", "solid")
        scenario(ed, "TEX_semisolid", "semisolid")
        scenario(ed, "TEX_nonsolid", "nonsolid")
    finally:
        if ed_id is not None:
            stop_editor(ed_id); log("editor torn down")
        else:
            log("(reused editor left running)")


if __name__ == "__main__":
    sys.exit(main())
