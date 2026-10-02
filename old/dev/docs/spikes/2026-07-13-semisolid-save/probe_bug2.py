#!/usr/bin/env python3
r"""Decisive test for "Bug 2" (does a semisolid brush deterministically break the
materialize MAP SAVE?). Reviewer critique: the failing config was castle-scale +
semisolid + LIGHT APPLY + save, and no probe ever ran THAT conjunction. This does,
repeating the suspect cell to separate deterministic from transient:

  T  (suspect): castle + 16 SEMISOLID detail + LIGHT APPLY -> save   x3
  C1 (control): castle + 16 SOLID     detail + LIGHT APPLY -> save   x1
  C2 (control): castle + 16 SEMISOLID detail, NO light      -> save  x1   (known-pass baseline)

All in ONE reused editor. Textures stripped (geometry isolation), plus a couple of
Lights so LIGHT APPLY actually does raycasting work. Reports wrote_file per run.

If T fails >=1x while C1/C2 never fail -> Bug 2 is real (semisolid + LIGHT APPLY at scale).
If T passes all 3 -> "transient" is finally supported (n>=3) and Bug 2 can be closed.

    UEDCLI_REUSE_EDITOR=uned-<uuid> PYTHONPATH=. python3 .../probe_bug2.py
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
from uedcli.materialize import levelinfo_first_order
from uedcli.model import parse_t3d
from uedcli.trunk import read_level
from uedcli.uuid7 import uuid7
from uedcli.editor import ensure_editor, stop_editor

CASTLE = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/castle/uedcli/maps/foobar")


def log(*a):
    print(*a, flush=True)


def settle(ed, s=2.0):
    time.sleep(s)
    try:
        if ed.dismiss_blocking_dialog():
            log("  [dismissed GC dialog]"); time.sleep(1.0)
    except Exception as e:
        log(f"  [dismiss failed: {e}]")


def csize(c, p):
    r = subprocess.run(["docker", "exec", c, "stat", "-c", "%s", p],
                       capture_output=True, text=True, check=False)
    return int(r.stdout.strip()) if r.returncode == 0 else None


def strip_tex(actor):
    import copy
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


def lights():
    out = []
    for i, (x, y, z) in enumerate([(0, 0, 200), (300, 300, 150), (-300, -300, 150)]):
        t = (f"Begin Map\nBegin Actor Class=Light Name=L{i}\n"
             f"    Location=(X={x}.000000,Y={y}.000000,Z={z}.000000)\n"
             f"    Name=\"L{i}\"\nEnd Actor\nEnd Map")
        out.append(next(iter(parse_t3d(t).actors.values())))
    return out


def feed(ed, actors, chunk=24):
    for i in range(0, len(actors), chunk):
        writes._re_add(ed, actors[i:i + chunk]); settle(ed, 1.5)


def cell(ed, tag, base, solidity, do_light):
    log(f"\n===== {tag} (detail={solidity} light={do_light}) =====")
    ed.map_new(); settle(ed)
    feed(ed, base)
    ed.rebuild(); settle(ed, 3.0)
    feed(ed, detail_16(solidity) + lights())
    ed.rebuild(); settle(ed, 3.0)
    if do_light:
        off = ed.log_size()
        try:
            ed.light_apply()
        except Exception as e:
            log(f"  LIGHT APPLY raised: {e}")
        settle(ed, 4.0)
        for l in ed.read_log_since(off).splitlines()[-4:]:
            if l.strip():
                log("  light|", l)
    cwork = f"/work/{tag}_{uuid.uuid4().hex}.dx"
    off = ed.log_size()
    try:
        ed.exec(f"MAP SAVE FILE={to_z_path(cwork)}")
    except Exception as e:
        log(f"  MAP SAVE raised: {e}")
    settle(ed, 3.0)
    sz = csize(ed.container, cwork)
    log(f"  [{tag}] wrote_file={sz is not None} size={sz}")
    if sz is None:
        for l in ed.read_log_since(off).splitlines()[-25:]:
            if l.strip():
                log("   |", l)
    return sz is not None


def main():
    base = load_castle_actors()
    log(f"loaded {len(base)} castle actors "
        f"({sum(1 for a in base if a.brush is not None)} brushes)")
    reuse = os.environ.get("UEDCLI_REUSE_EDITOR")
    ed_id = None
    if reuse:
        container = reuse; log(f"REUSING {container}")
    else:
        ed_id = uuid7(); container = ensure_editor(ed_id, ready_timeout=120.0)
    ed = Driver(container=container)
    results = {}
    try:
        results["T1"] = cell(ed, "T1_semi_light", base, "semisolid", True)
        results["T2"] = cell(ed, "T2_semi_light", base, "semisolid", True)
        results["T3"] = cell(ed, "T3_semi_light", base, "semisolid", True)
        results["C1"] = cell(ed, "C1_solid_light", base, "solid", True)
        results["C2"] = cell(ed, "C2_semi_nolight", base, "semisolid", False)
        log("\n===== SUMMARY =====")
        for k, v in results.items():
            log(f"  {k}: saved={v}")
        t = [results[k] for k in ("T1", "T2", "T3")]
        log(f"\n  suspect (semi+light) saved: {t}  all_pass={all(t)}")
        log(f"  controls: solid+light={results['C1']} semi+nolight={results['C2']}")
    finally:
        if ed_id is not None:
            stop_editor(ed_id); log("editor torn down")
        else:
            log("(reused editor left running)")


if __name__ == "__main__":
    sys.exit(main())
