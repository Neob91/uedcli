#!/usr/bin/env python3
r"""Per-SURF node-count diff between a native-built model and an editor golden.

The sharpest localizer for a node-count gap on a real map: a whole-tree count says "50 nodes too
many", this says WHICH source brush faces they hang off. On UNATCO it reduced a 50-node gap to three
surfs of one brush in a single run, which a plane-multiset or tree-walk diff never did.

Both models must already be canonicalized to the same Surfs order (native's
`reorder_surfs_canonical` does this), so surf index `i` means the same face on both sides — the
printed `iActor`/`iBrushPoly` per differing surf is the check that it does.

Usage:  surf_node_diff.py <native.dx-or-model-body> <golden.dx>
        (each argument is passed to `uedcli.native.umodel.parse_model_body` via the package reader;
        a raw serialized Model body works too — see `build_native_unatco.py`.)
"""
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT))
from uedcli.native import umodel as UM  # noqa: E402
from uedcli.native.pkg_write import parse_package  # noqa: E402


def load(path: Path):
    data = path.read_bytes()
    if data[:4] != b"\xc1\x83\x2a\x9e":  # not a package — a raw Model body
        return UM.parse_model_body(data, 0, len(data))
    pkg = parse_package(data)
    mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
             key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    return UM.parse_model_body(pkg.buf, e["soff"], e["ssize"])


def main():
    nm, em = load(Path(sys.argv[1])), load(Path(sys.argv[2]))
    print(f"nodes {len(nm.nodes)} vs {len(em.nodes)}   surfs {len(nm.surfs)} vs {len(em.surfs)}")
    nc, ec = Counter(n.i_surf for n in nm.nodes), Counter(n.i_surf for n in em.nodes)
    diff = [(s, nc[s], ec[s]) for s in sorted(set(nc) | set(ec)) if nc[s] != ec[s]]
    print(f"surfs with differing node counts: {len(diff)}   total delta: "
          f"{sum(a - b for _, a, b in diff)}")
    for s, a, b in diff:
        ns = nm.surfs[s] if s < len(nm.surfs) else None
        es = em.surfs[s] if s < len(em.surfs) else None
        print(f"  surf {s}: native {a} nodes, editor {b}"
              f"  iActor {ns.i_actor if ns else '-'}/{es.i_actor if es else '-'}"
              f"  iBrushPoly {ns.i_brush_poly if ns else '-'}/{es.i_brush_poly if es else '-'}")


if __name__ == "__main__":
    main()
