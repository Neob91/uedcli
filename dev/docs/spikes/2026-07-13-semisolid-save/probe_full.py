#!/usr/bin/env python3
r"""Spike harness part 4: reproduce the failure at FULL CASTLE SCALE by driving the
editor directly (bypassing uedctl's texture-qualify step, which errors on an
unrelated package issue in this env). We feed the ENTIRE castle trunk (95 brushes
+ points) PLUS the 16 detail brushes from build_detail.sh BATCH 3+4, rebuild, and
MAP SAVE — once with the 16 detail brushes SEMISOLID, once SOLID. Textures are
stripped from every brush (both variants equally) so the editor needs no package
loads; the only difference between the two runs is the detail solidity flag.

Reuse the booted editor:
    UEDCTL_REUSE_EDITOR=uned-<uuid> PYTHONPATH=. python3 .../probe_full.py
"""
from __future__ import annotations

import copy
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from uedctl import builders, writes
from uedctl.driver import Driver, to_z_path
from uedctl.materialize import levelinfo_first_order
from uedctl.trunk import read_level
from uedctl.uuid7 import uuid7
from uedctl.editor import ensure_editor, stop_editor

CASTLE = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/castle/uedctl/maps/foobar")


def log(*a):
    print(*a, flush=True)


def dexec(c, *cmd):
    return subprocess.run(["docker", "exec", c, *cmd], capture_output=True, text=True, check=False)


def csize(c, p):
    r = dexec(c, "stat", "-c", "%s", p)
    return int(r.stdout.strip()) if r.returncode == 0 else None


def settle(ed, s=2.0):
    time.sleep(s)
    try:
        if ed.dismiss_blocking_dialog():
            log("  [dismissed GC dialog]"); time.sleep(1.0)
    except Exception as e:
        log(f"  [dismiss failed: {e}]")


def strip_tex(actor):
    a = copy.deepcopy(actor)
    if a.brush is not None:
        for p in a.brush.polys:
            p.texture = None
    return a


def load_castle_actors():
    level, ranks = read_level(CASTLE)
    names = sorted(level.actors, key=lambda n: (ranks.get(n, ""), n))
    classes = {n: level.actors[n].cls for n in names}
    has_brush = {n: level.actors[n].brush is not None for n in names}
    order = levelinfo_first_order(names, classes, has_brush)
    return [strip_tex(level.actors[n]) for n in order]


def detail_16(solidity):
    pf = builders.SOLIDITY_FLAGS[solidity]

    def C(name, at, w, b, h):
        return builders.make_brush_actor(name, builders.cube(w, b, h, texture=None),
                                         location=at, csg="add", poly_flags=pf)
    out = []
    for x, y in [(57, 57), (-57, 57), (57, -57), (-57, -57)]:
        out.append(C(f"Butt_{x}_{y}", (x, y, 132), 20, 20, 264))
    for x, y in [(160, 160), (-160, 160), (160, -160), (-160, -160)]:
        out.append(C(f"TButt_{x}_{y}", (x, y, 120), 22, 22, 240))
    for x, y in [(240, 240), (-240, 240), (240, -240), (-240, -240)]:
        out.append(C(f"Brazier_{x}_{y}", (x, y, 22), 24, 24, 44))
        out.append(C(f"BrazBowl_{x}_{y}", (x, y, 49), 40, 40, 10))
    return out


def feed(ed, actors, chunk=24):
    """Feed a big actor list in chunks so one EDIT PASTE clipboard isn't enormous."""
    for i in range(0, len(actors), chunk):
        writes._re_add(ed, actors[i:i + chunk])
        settle(ed, 1.5)


def save_probe(ed, tag):
    cwork = f"/work/{tag}_{uuid.uuid4().hex}.dx"
    off = ed.log_size()
    try:
        ed.exec(f"MAP SAVE FILE={to_z_path(cwork)}")
    except Exception as e:
        log(f"  MAP SAVE exec raised: {e}")
    settle(ed, 3.0)
    try:
        ed.exec("MAP GRID X=16 Y=16 Z=16")
    except Exception:
        pass
    time.sleep(1.5)
    tail = ed.read_log_since(off)
    size = csize(ed.container, cwork)
    log(f"  [{tag}] MAP SAVE exists={size is not None} size={size}")
    log("  --- log across save (last 60 lines) ---")
    for l in tail.splitlines()[-60:]:
        if l.strip():
            log("   |", l)
    log("  --- end ---")
    return size is not None


def run(ed, tag, solidity, base):
    log(f"\n===== {tag} (detail={solidity}) =====")
    ed.map_new(); settle(ed)
    log(f"  feeding {len(base)} base castle actors ...")
    feed(ed, base)
    ed.rebuild(); settle(ed, 3.0)
    det = detail_16(solidity)
    log(f"  feeding {len(det)} detail brushes ({solidity}) ...")
    feed(ed, det)
    ed.rebuild(); settle(ed, 3.0)
    return save_probe(ed, tag)


def main():
    base = load_castle_actors()
    log(f"loaded {len(base)} castle actors "
        f"({sum(1 for a in base if a.brush is not None)} brushes)")
    reuse = os.environ.get("UEDCTL_REUSE_EDITOR")
    ed_id = None
    if reuse:
        container = reuse; log(f"REUSING {container}")
    else:
        ed_id = uuid7(); container = ensure_editor(ed_id, ready_timeout=120.0)
    ed = Driver(container=container)
    try:
        semi = run(ed, "FULL_semisolid", "semisolid", base)
        solid = run(ed, "FULL_solid", "solid", base)
        log("\n===== SUMMARY =====")
        log(f"  FULL castle + 16 SEMISOLID detail saved: {semi}")
        log(f"  FULL castle + 16 SOLID     detail saved: {solid}")
    finally:
        if ed_id is not None:
            stop_editor(ed_id); log("editor torn down")
        else:
            log("(reused editor left running)")


if __name__ == "__main__":
    sys.exit(main())
