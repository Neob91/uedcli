#!/usr/bin/env python3
r"""Spike harness part 6 — the TWO remaining questions the earlier probes left open.

The earlier probes drove import -> rebuild -> MAP SAVE and concluded "geometry
saves fine, only qualify off-by-one is the bug". But the REAL materialize path is
import -> rebuild -> **LIGHT APPLY** -> MAP SAVE, and a live `--no-verify`
materialize (qualify skipped) of castle+1 semisolid STILL failed at MAP SAVE. So
LIGHT APPLY is the untested step. This probe:

  Q1 (light-vs-save): minimal subtracted room + one ADD cube, per solidity, run BOTH
     ways in the SAME editor:
        A) rebuild -> MAP SAVE           (no light)
        B) rebuild -> LIGHT APPLY -> MAP SAVE
     For each: did LIGHT APPLY complete, and did MAP SAVE write a file?
     If B fails where A succeeds for semisolid, LIGHT APPLY is the trigger.

  Q2 (qualify world-Model identity): for the solid room+cube, print the FULL RAW
     OBJ DEPENDENCIES segment so we can see whether each `Class Engine.Polys` line
     carries an OWNER name (e.g. `MyLevel.Model`) that lets us drop the world-Model
     block by identity instead of by fragile position.

    UEDCLI_REUSE_EDITOR=uned-<uuid> PYTHONPATH=. python3 .../probe_lightsave.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid

from uedcli import builders, writes
from uedcli.driver import Driver, to_z_path
from uedcli.qualify import dump_obj_dependencies, parse_obj_dependencies
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


def load_texture(ed):
    cwork = f"/work/LUM_CoreTex_{uuid.uuid4().hex}.utx"
    subprocess.run(["docker", "cp", TEX_HOST, f"{ed.container}:{cwork}"],
                   check=True, capture_output=True, text=True)
    ed.exec(f"OBJ LOAD FILE={to_z_path(cwork)} PACKAGE=LUM_CoreTex")
    settle(ed, 2.0)


def csize(c, p):
    r = subprocess.run(["docker", "exec", c, "stat", "-c", "%s", p],
                       capture_output=True, text=True, check=False)
    return int(r.stdout.strip()) if r.returncode == 0 else None


def room():
    return builders.make_brush_actor("Room", builders.cube(1024, 1024, 512, texture=TEXNAME),
                                     location=(0, 0, 0), csg="subtract")


def add_cube(name, solidity, at):
    return builders.make_brush_actor(name, builders.cube(128, 128, 128, texture=TEXNAME),
                                     location=at, csg="add",
                                     poly_flags=builders.SOLIDITY_FLAGS[solidity])


def a_light():
    from uedcli.model import parse_t3d
    t = ("Begin Map\nBegin Actor Class=Light Name=Torch\n"
         "    Location=(X=0.000000,Y=0.000000,Z=0.000000)\n    Name=\"Torch\"\nEnd Actor\nEnd Map")
    return next(iter(parse_t3d(t).actors.values()))


def save(ed, tag):
    cwork = f"/work/{tag}_{uuid.uuid4().hex}.dx"
    off = ed.log_size()
    try:
        ed.exec(f"MAP SAVE FILE={to_z_path(cwork)}")
    except Exception as e:
        log(f"    MAP SAVE exec raised: {e}")
    settle(ed, 3.0)
    sz = csize(ed.container, cwork)
    log(f"    [{tag}] MAP SAVE wrote_file={sz is not None} size={sz}")
    tail = ed.read_log_since(off)
    for l in tail.splitlines()[-12:]:
        if l.strip():
            log("      |", l)
    return sz is not None


def q1(ed, solidity):
    log(f"\n===== Q1 {solidity}: rebuild->save   vs   rebuild->LIGHT APPLY->save =====")
    actors = [room(), add_cube("D0", solidity, (0, 0, 0)), a_light()]

    # A) no light
    ed.map_new(); settle(ed)
    writes._re_add(ed, actors); settle(ed)
    ed.rebuild(); settle(ed, 3.0)
    a_ok = save(ed, f"A_nolight_{solidity}")

    # B) with LIGHT APPLY
    ed.map_new(); settle(ed)
    writes._re_add(ed, actors); settle(ed)
    ed.rebuild(); settle(ed, 3.0)
    off = ed.log_size()
    try:
        ed.light_apply()
        log("    LIGHT APPLY issued")
    except Exception as e:
        log(f"    LIGHT APPLY exec raised: {e}")
    settle(ed, 4.0)
    lt = ed.read_log_since(off)
    for l in lt.splitlines()[-8:]:
        if l.strip():
            log("      light|", l)
    b_ok = save(ed, f"B_light_{solidity}")
    log(f"  RESULT {solidity}: no-light save={a_ok}   light+save={b_ok}")
    return a_ok, b_ok


def q2_raw(ed):
    log("\n===== Q2: RAW OBJ DEPENDENCIES (solid room+cube) — owner names? =====")
    ed.map_new(); settle(ed)
    writes._re_add(ed, [room(), add_cube("D0", "solid", (0, 0, 0))]); settle(ed)
    ed.rebuild(); settle(ed, 3.0)
    raw = dump_obj_dependencies(ed)
    log("  --- raw segment (Class/owner lines) ---")
    for l in raw.splitlines():
        if "Class" in l or "Polys" in l or "Model" in l:
            log("   >", l)
    log("  --- parsed ---")
    blocks = parse_obj_dependencies(raw)
    log(f"  {len(blocks)} blocks, sizes={[len(b) for b in blocks]}")


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
        q2_raw(ed)
        r_solid = q1(ed, "solid")
        r_semi = q1(ed, "semisolid")
        log("\n===== SUMMARY =====")
        log(f"  solid:     no-light={r_solid[0]} light={r_solid[1]}")
        log(f"  semisolid: no-light={r_semi[0]} light={r_semi[1]}")
    finally:
        if ed_id is not None:
            stop_editor(ed_id); log("editor torn down")
        else:
            log("(reused editor left running)")


if __name__ == "__main__":
    sys.exit(main())
