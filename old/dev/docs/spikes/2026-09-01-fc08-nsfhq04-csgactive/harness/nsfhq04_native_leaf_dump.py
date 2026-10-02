#!/usr/bin/env python3
"""Native's FULL classify trace (kept AND discarded, via LEAF) plus the NADD node-add trace, for
NSFHQ04's `Brush842` (actor_index=512) -- same method as Area51's `area51_native_leaf_dump.py`: one
n=512 build (baseline, to know where the tail starts) then one n=513 build (LEAF gated to
actor=512 the whole time; harmless for actors 0..511 since none match "512"), so NADD-tail-count and
LEAF add=true-count come from the SAME computation and are directly comparable to the live editor's
own AddBrushToWorldFunc tail (`nsfhq04_addfunc_oracle.py` + `nsfhq04_compare_tail.py`).
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

TRUNK = ROOT / "_scratch/nsfhq04-structural-only2/maps/nsfhq04"
os.environ["UEDCLI_PROJECT"] = str(TRUNK.parent.parent)

from uedcli import trunk as trunk_mod  # noqa: E402
from uedcli.native import brush_marshal as BM  # noqa: E402
import uedcli_native  # noqa: E402
from spike_classindex import class_index  # noqa: E402

level, ranks = trunk_mod.read_level(TRUNK)
ci = class_index()
brush_names = [n for n in level.order
               if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
assert brush_names[512] == "Brush842"

os.environ["UEDCLI_BSPCSG_DESCENT_ACTOR"] = "512"
os.environ["UEDCLI_BSPCSG_TREE_DUMP"] = "1"

ins512 = [BM._build_brush_input(nm, level.actors[nm]) for nm in brush_names[:512]]
ins513 = [BM._build_brush_input(nm, level.actors[nm]) for nm in brush_names[:513]]


def capture(fn):
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".log")
    tf.close()
    fd = os.open(tf.name, os.O_WRONLY)
    saved = os.dup(2)
    os.dup2(fd, 2)
    try:
        fn()
    finally:
        os.dup2(saved, 2)
        os.close(saved)
        os.close(fd)
    return open(tf.name).read().splitlines()


lines512 = capture(lambda: uedcli_native.build_geometry_bspcsg(ins512))
lines513 = capture(lambda: uedcli_native.build_geometry_bspcsg(ins513))

nadd512 = [l for l in lines512 if l.startswith("NADD")]
nadd513 = [l for l in lines513 if l.startswith("NADD")]
leaf513 = [l for l in lines513 if l.startswith("LEAF")]

print(f"NADD count: n=512 build={len(nadd512)}  n=513 build={len(nadd513)}  "
      f"tail={len(nadd513)-len(nadd512)}")
print(f"LEAF (actor=512 classify) count in n=513 build: {len(leaf513)}")
kept = [l for l in leaf513 if l.rstrip().endswith("add=true")]
disc = [l for l in leaf513 if l.rstrip().endswith("add=false")]
print(f"  kept (add=true): {len(kept)}   discarded (add=false): {len(disc)}")

tail_nadd = nadd513[len(nadd512):]
out1 = ROOT / "_scratch/nsfhq04_brush842_native_nadd.log"
out1.write_text("\n".join(tail_nadd) + "\n")
out2 = ROOT / "_scratch/nsfhq04_brush842_native_leaf.log"
out2.write_text("\n".join(leaf513) + "\n")
print("wrote", out1, out2)
