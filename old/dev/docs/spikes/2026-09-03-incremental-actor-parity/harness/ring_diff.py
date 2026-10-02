#!/usr/bin/env python3
"""Compare two builds' world `Model` node vertex RINGS by resolved coordinate, not by pool index.

`model_dump.py` diffs the raw `Verts` array, so it reports every ORPHAN slot (a `FVert` in no live
node ring — excluded from the gate, and routinely stale in both builds) as a difference. That reads
as "the rings differ" when they do not: UNATCO N=29 showed 391 of 860 `FVert`s naming different
`Points`, yet all 91 live rings were coordinate-identical and the real divergence was a surf's
`Texture` ref (board item `unatco-n-29-world-model2-vert-rings-reference`).

This walks each node's `[iVertPool, iVertPool+NumVertices)` ring, resolves it through `Points`, and
classifies the pair as identical / a cyclic rotation / genuinely different — so a `Verts` diff can be
told apart from ring noise before anything is traced.

Nodes are paired POSITIONALLY, so the report only means something when the two trees agree on node
order -- check the gate's node tokens first if they might not.

Usage: ring_diff.py <a.dx> <b.dx> [<model-name>]      # model-name defaults to Model2
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import model_dump as md  # noqa: E402
import parity_gate as pg  # noqa: E402

# `model_write.rs` node field order: the ten compact indices after the plane/zone-mask/flags.
VERT_POOL, NUM_VERTICES = 0, 9


def _load(path: str, name: str) -> dict:
    p = pg.load_package(path)
    return md.decode(p, md.find(p, name))


def _ring(model: dict, node) -> list:
    """The node's ring as resolved point coordinates. A vert whose `iVertex` is out of range (the
    orphan case the exclusion set describes) reports as `("iVertex", i)` rather than raising."""
    cis = node[3]
    base, count = cis[VERT_POOL], cis[NUM_VERTICES]
    out = []
    for k in range(count):
        i = model["verts"][base + k][0]
        out.append(model["points"][i] if 0 <= i < len(model["points"]) else ("iVertex", i))
    return out


def main() -> int:
    a, b = sys.argv[1], sys.argv[2]
    name = sys.argv[3] if len(sys.argv) > 3 else "Model2"
    A, B = _load(a, name), _load(b, name)
    print(f"points {'SAME' if A['points'] == B['points'] else 'DIFF'} "
          f"({len(A['points'])} vs {len(B['points'])})")
    print(f"verts  {len(A['verts'])} vs {len(B['verts'])}   "
          f"nodes {len(A['nodes'])} vs {len(B['nodes'])}")
    if len(A["nodes"]) != len(B["nodes"]):
        print("node COUNT differs -- the trees are not comparable ring by ring")
        return 1
    same = rotated = other = 0
    for i, (na, nb) in enumerate(zip(A["nodes"], B["nodes"])):
        ra, rb = _ring(A, na), _ring(B, nb)
        if ra == rb:
            same += 1
            continue
        rot = next((k for k in range(len(ra)) if len(ra) == len(rb) and ra[k:] + ra[:k] == rb), None)
        if rot is not None:
            rotated += 1
            print(f"node {i}: ring ROTATED by {rot} (same {len(ra)} points)")
        else:
            other += 1
            print(f"node {i}: ring DIFFERS ({len(ra)} vs {len(rb)} points, "
                  f"same point SET: {sorted(ra, key=repr) == sorted(rb, key=repr)})")
            print(f"   a: {ra}")
            print(f"   b: {rb}")
    print(f"rings: identical={same} rotated={rotated} different={other}")
    return 0 if rotated == other == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
