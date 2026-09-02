"""Attribute remaining final-Pass-1 plane diffs to their creating brush; report scaled-ness.

Inputs are the RUN OUTPUTS of the paired scripts, expected in this script's own directory (rerun
them to regenerate; only the small logs are committed, under ../logs/ with a `pass1-` prefix):
`native_full_375_fixed.log` (pass1_native_states.py FULL:375-375 stderr), `native_counts.log` +
`native_bi.txt` (its COUNTS stderr/stdout), `p1nodes/` (pass1_brush_trace_unatco.py binary dumps)."""
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness"))
os.environ["UEDCLI_PROJECT"] = "/workspace/uedcli/_scratch/bsp-parity-proj"
from pass1_compare import parse_native, read_bin
from uedcli import trunk
from uedcli import rotation as ROT

_, na_nodes = parse_native(HERE / "native_full_375_fixed.log")
ed = read_bin(HERE / "p1nodes/nfinal.bin")
na = na_nodes[375]

# brush boundary table: k -> (bi, nodes_after)
bounds = []
for line in (HERE / "native_counts.log").read_text().splitlines():
    m = re.match(r"BRUSHSTATE k=(\d+) bi=(\d+) nodes=(\d+)", line)
    if m:
        bounds.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))

names = {}
for line in (HERE / "native_bi.txt").read_text().splitlines():
    if line.startswith("BI "):
        _, bi, nm = line.split()
        names[int(bi)] = nm

level, _ = trunk.read_level(Path("/workspace/uedcli/_scratch/bsp-parity-proj/maps/unatco"))

def brush_of_node(i):
    for k, bi, nafter in bounds:
        if i < nafter:
            return bi
    return None

from collections import Counter
c = Counter()
for i, (e, n) in enumerate(zip(ed, na)):
    if e != n:
        bi = brush_of_node(i)
        c[bi] += 1
for bi, cnt in sorted(c.items()):
    nm = names[bi]
    a = level.actors[nm]
    scaled = not (ROT.actor_main_scale(a).is_identity() and ROT.actor_post_scale(a).is_identity())
    oper = dict(a.props).get("CsgOper", "<absent>")
    print(f"bi={bi} {nm} diffs={cnt} scaled={scaled} oper={oper}")
print("total diff nodes:", sum(c.values()))
