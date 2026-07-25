#!/usr/bin/env python3
r"""Identify the world-Model AGGREGATE Engine.Polys block ROBUSTLY (position is NOT
stable: a 2-brush level put it 5th, the 95-brush castle put it 1st, zipped with the
first World-shell subtract brush -> 6-polys-vs-853-textures raise).

Reproduce the castle shape cheaply: a big subtractive World shell + several ADD cubes
with DIFFERENT textures. Dump OBJ DEPENDENCIES and, for EACH reference section, record
its Class and (if Engine.Polys OR Engine.Model) its ordered texture list. Then test the
candidate identifiers:
  (1) Does exactly ONE Engine.Polys block equal a textured Engine.Model block (same
      ordered list)? Is that the aggregate?
  (2) Aggregate position among non-empty Polys blocks (first? last? unstable?).
  (3) After removing the Model-duplicated Polys block, do the remaining non-empty Polys
      blocks correlate 1:1 by COUNT, in order, with the authored brushes?
  (4) Bare-name (suffix) sequence matching: does each brush's authored bare-name sequence
      uniquely pick its block, leaving the aggregate unmatched?

    UEDCTL_REUSE_EDITOR=uned-<uuid> PYTHONPATH=. python3 .../probe_aggregate.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import uuid

from uedctl import builders, writes
from uedctl.driver import Driver, to_z_path
from uedctl.qualify import dump_obj_dependencies
from uedctl.uuid7 import uuid7
from uedctl.editor import ensure_editor, stop_editor

TEX_HOST = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Textures/LUM_CoreTex.utx"
# a few genuinely different textures so bare-name matching is exercised
TEXES = ["LUM_CoreTex.grey_stone_tile", "LUM_CoreTex.red_brick",
         "LUM_CoreTex.wood_planks", "LUM_CoreTex.grey_stone_tile"]
_LINE = re.compile(r"(?:Log:\s*)?\s*(Class|Texture)\s+(\S+)")


def log(*a):
    print(*a, flush=True)


def settle(ed, s=2.0):
    time.sleep(s)
    try:
        ed.dismiss_blocking_dialog()
    except Exception:
        pass


def parse_typed_blocks(dump):
    """Every reference section -> (class_token, [texture refs]). Keeps ALL classes, not just
    Engine.Polys, so we can see the Engine.Model duplication."""
    out = []
    cur_cls = None
    cur = None
    for line in dump.splitlines():
        m = _LINE.match(line)
        if m is None:
            continue
        kind, tok = m.groups()
        if kind == "Class":
            if cur_cls is not None:
                out.append((cur_cls, cur))
            cur_cls, cur = tok, []
        elif cur is not None:
            cur.append(tok)
    if cur_cls is not None:
        out.append((cur_cls, cur))
    return out


def bare(ref):
    return ref.split(".")[-1]


def main():
    reuse = os.environ.get("UEDCTL_REUSE_EDITOR")
    ed_id = None
    if reuse:
        container = reuse; log(f"REUSING {container}")
    else:
        ed_id = uuid7(); container = ensure_editor(ed_id, ready_timeout=120.0)
    ed = Driver(container=container)
    try:
        cwork = f"/work/LUM_CoreTex_{uuid.uuid4().hex}.utx"
        subprocess.run(["docker", "cp", TEX_HOST, f"{ed.container}:{cwork}"],
                       check=True, capture_output=True, text=True)
        ed.exec(f"OBJ LOAD FILE={to_z_path(cwork)} PACKAGE=LUM_CoreTex"); settle(ed)

        # big World shell (subtract) FIRST, then 4 add cubes with different textures
        actors = [builders.make_brush_actor(
            "World_shell", builders.cube(2048, 2048, 1024, texture=TEXES[0]),
            location=(0, 0, 0), csg="subtract")]
        for i, t in enumerate(TEXES):
            actors.append(builders.make_brush_actor(
                f"Cube{i}", builders.cube(128, 128, 128, texture=t),
                location=(i * 300 - 450, 0, 0), csg="add"))

        ed.map_new(); settle(ed)
        writes._re_add(ed, actors); settle(ed)
        ed.rebuild(); settle(ed, 3.0)

        typed = parse_typed_blocks(dump_obj_dependencies(ed))
        polys = [(i, t) for i, (c, t) in enumerate(typed) if c == "Engine.Polys"]
        models = [t for c, t in typed if c == "Engine.Model" and t]
        non_empty_polys = [(i, t) for (i, t) in polys if t]

        log(f"\n#Engine.Polys sections={len(polys)} non-empty={len(non_empty_polys)}")
        log(f"  non-empty Polys sizes (in walk order): {[len(t) for _, t in non_empty_polys]}")
        log(f"#textured Engine.Model sections={len(models)} sizes={[len(t) for t in models]}")

        # (1)+(2): which non-empty Polys blocks duplicate a textured Model block?
        model_set = {tuple(t) for t in models}
        dup_idx = [k for k, (_, t) in enumerate(non_empty_polys) if tuple(t) in model_set]
        log(f"\n(1) non-empty Polys blocks matching a textured Model block: indices {dup_idx} "
            f"sizes={[len(non_empty_polys[k][1]) for k in dup_idx]}")
        largest = max(range(len(non_empty_polys)), key=lambda k: len(non_empty_polys[k][1]))
        log(f"(2) largest non-empty Polys block is at index {largest} of "
            f"{len(non_empty_polys)} (0=first) size={len(non_empty_polys[largest][1])}")

        # authored brush textured-poly counts + bare-name sequences, in order
        brushes = [a for a in actors if a.brush is not None]
        exp_counts = [sum(1 for p in a.brush.polys if p.texture) for a in brushes]
        exp_bare = [tuple(bare(p.texture) for p in a.brush.polys if p.texture) for a in brushes]
        log(f"\nauthored brushes={len(brushes)} counts={exp_counts}")

        # (3): drop the Model-duplicated block, then correlate remaining by count in order
        remaining = [t for k, (_, t) in enumerate(non_empty_polys) if k not in dup_idx]
        log(f"(3) after dropping dup block(s): {len(remaining)} blocks, "
            f"sizes={[len(t) for t in remaining]}  (brushes={len(brushes)})")
        ok3 = len(remaining) == len(brushes) and all(
            len(remaining[j]) == exp_counts[j] for j in range(len(brushes)))
        log(f"    correlate-by-count-in-order OK={ok3}")

        # (4): bare-name sequence matching (position-independent)
        pool = [tuple(bare(x) for x in t) for _, t in non_empty_polys]
        used = set()
        matched = []
        for seq in exp_bare:
            hit = next((k for k in range(len(pool)) if k not in used and pool[k] == seq), None)
            matched.append(hit)
            if hit is not None:
                used.add(hit)
        leftover = [k for k in range(len(pool)) if k not in used]
        log(f"(4) bare-name match per brush -> block idx: {matched}")
        log(f"    leftover (unmatched) block idx: {leftover} "
            f"sizes={[len(non_empty_polys[k][1]) for k in leftover]}")
        log(f"    all brushes matched={all(m is not None for m in matched)} "
            f"leftover_is_single_aggregate={len(leftover) == 1}")
    finally:
        if ed_id is not None:
            stop_editor(ed_id); log("editor torn down")
        else:
            log("(reused editor left running)")


if __name__ == "__main__":
    sys.exit(main())
