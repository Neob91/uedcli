#!/usr/bin/env python3
"""Native's FULL classify trace (kept AND discarded, via LEAF) plus the NADD node-add trace, for
Brush1852 (actor_index=506) -- one clean process, one n=506 build (baseline, to know where the tail
starts) then one n=507 build (LEAF gated to actor=506 the whole time; harmless for actors 0..505
since none match "506"), so NADD-tail-count and LEAF add=true-count come from the SAME computation
and are directly comparable."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

TRUNK = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-check/_scratch/uedcli-parity-cache/"
             "65b9261c371bdf8573cb7bf9128a3f6664b14d2ac360ef6fbfd4a0d292986ece/trunk/maps/15_area51_entrance")
os.environ["UEDCLI_PROJECT"] = str(TRUNK.parent.parent)

from uedcli import trunk as trunk_mod  # noqa: E402
from uedcli.native import brush_marshal as BM  # noqa: E402
import uedcli_native  # noqa: E402
from spike_classindex import class_index  # noqa: E402

level, ranks = trunk_mod.read_level(TRUNK)
ci = class_index()
brush_names = [n for n in level.order
               if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
assert brush_names[506] == "Brush1852"

os.environ["UEDCLI_BSPCSG_DESCENT_ACTOR"] = "506"
os.environ["UEDCLI_BSPCSG_TREE_DUMP"] = "1"

ins506 = [BM._build_brush_input(nm, level.actors[nm]) for nm in brush_names[:506]]
ins507 = [BM._build_brush_input(nm, level.actors[nm]) for nm in brush_names[:507]]


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


lines506 = capture(lambda: uedcli_native.build_geometry_bspcsg(ins506))
lines507 = capture(lambda: uedcli_native.build_geometry_bspcsg(ins507))

nadd506 = [l for l in lines506 if l.startswith("NADD")]
nadd507 = [l for l in lines507 if l.startswith("NADD")]
leaf507 = [l for l in lines507 if l.startswith("LEAF")]

print(f"NADD count: n=506 build={len(nadd506)}  n=507 build={len(nadd507)}  tail={len(nadd507)-len(nadd506)}")
print(f"LEAF (actor=506 classify) count in n=507 build: {len(leaf507)}")
kept = [l for l in leaf507 if l.rstrip().endswith("add=true")]
disc = [l for l in leaf507 if l.rstrip().endswith("add=false")]
print(f"  kept (add=true): {len(kept)}   discarded (add=false): {len(disc)}")

tail_nadd = nadd507[len(nadd506):]
out1 = ROOT / "_scratch/area51_brush1852_native_nadd_v2.log"
out1.write_text("\n".join(tail_nadd) + "\n")
out2 = ROOT / "_scratch/area51_brush1852_native_leaf_v2.log"
out2.write_text("\n".join(leaf507) + "\n")
print("wrote", out1, out2)
print("\n--- NADD tail ---")
for l in tail_nadd:
    print(l)
print("\n--- LEAF (all classify) ---")
for l in leaf507:
    print(l)
