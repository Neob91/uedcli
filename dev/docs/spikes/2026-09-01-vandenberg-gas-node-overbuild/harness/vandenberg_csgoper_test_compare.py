#!/usr/bin/env python3
"""Compare the two live-editor goldens `vandenberg_csgoper_test_golden.py` built: A (no Brush230)
vs B (with Brush230, real order). If the editor treats a CsgOper-absent brush as inactive
(CSG_Active, out of world CSG), the two builds are geometrically IDENTICAL.

Usage: .venv/bin/python vandenberg_csgoper_test_compare.py
"""
import sys
from pathlib import Path

ROOT = Path("/workspace/uedcli/.claude/worktrees/vandenberg-gas-parity")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

from uedcli.native import umodel as UM       # noqa: E402
import utexture_decode as UT                  # noqa: E402

OUT_DIR = ROOT / "_scratch/vandenberg-csgoper-test"


def parse(path):
    pkg = UT.load_package(str(path))
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    m = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])
    return pkg, m


def counts(m):
    return (len(m.nodes), len(m.surfs), len(m.leaves), len(m.verts), len(m.points), len(m.vectors))


def main():
    _pa, ma = parse(OUT_DIR / "A_no230.dx")
    _pb, mb = parse(OUT_DIR / "B_with230.dx")
    ca, cb = counts(ma), counts(mb)
    labels = ("nodes", "surfs", "leaves", "verts", "points", "vectors")
    print("A (no Brush230):  " + " ".join(f"{l}={v}" for l, v in zip(labels, ca)))
    print("B (with Brush230):" + " ".join(f"{l}={v}" for l, v in zip(labels, cb)))
    print("IDENTICAL" if ca == cb else f"DIFFER: {[b-a for a, b in zip(ca, cb)]}")


if __name__ == "__main__":
    raise SystemExit(main())
