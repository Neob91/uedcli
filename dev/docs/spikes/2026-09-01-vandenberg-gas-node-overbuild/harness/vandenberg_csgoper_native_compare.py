#!/usr/bin/env python3
"""Native build of the SAME two brush sets `vandenberg_csgoper_test_golden.py` built live
(A = Brush2054,Brush73,Brush54; B = Brush230,Brush2054,Brush73,Brush54), compared against the two
live-editor goldens. Brush230 has no `CsgOper=` -- native's `_build_brush_input` currently defaults
an absent CsgOper to `"CSG_Add"`. The live A/B comparison already showed the editor does NOT treat
Brush230 as a no-op (B has FAR FEWER nodes/surfs than A: 181 vs 483) -- refuting the "CSG_Active
means skip" hypothesis for this case. This script checks what NATIVE's current CSG_Add-default
behavior produces for the same two sets, to see whether it already matches editor reality (ruling
out a CsgOper-related bug entirely) or diverges (and how).

Usage: .venv/bin/python vandenberg_csgoper_native_compare.py
"""
import sys
from pathlib import Path

ROOT = Path("/workspace/uedcli/.claude/worktrees/vandenberg-gas-parity")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

from uedcli import trunk                                   # noqa: E402
from uedcli.native import brush_marshal as BM               # noqa: E402
from uedcli.native import umodel as UM                       # noqa: E402
import uedcli_native                                          # noqa: E402
import utexture_decode as UT                                  # noqa: E402

TRUNK = (ROOT / "_scratch/uedcli-parity-cache/"
         "7d06dd6155e5daa7c78e76ed19a66068852973670d1c56dddd9628b2ca393c13/trunk/maps/12_vandenberg_gas")
OUT_DIR = ROOT / "_scratch/vandenberg-csgoper-test"


def parse_golden(path):
    pkg = UT.load_package(str(path))
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    m = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])
    return m


def build_native(names, level):
    ins = [BM._build_brush_input(n, level.actors[n]) for n in names]
    built = uedcli_native.build_geometry_bspcsg(ins)
    nbody = uedcli_native.serialize_model(built)
    return UM.parse_model_body(nbody, 0, len(nbody))


def counts(m):
    return (len(m.nodes), len(m.surfs), len(m.leaves), len(m.verts), len(m.points), len(m.vectors))


def main():
    level, _ranks = trunk.read_level(TRUNK)
    labels = ("nodes", "surfs", "leaves", "verts", "points", "vectors")

    for tag, names, golden_file in (
        ("A", ["Brush2054", "Brush73", "Brush54"], "A_no230.dx"),
        ("B", ["Brush230", "Brush2054", "Brush73", "Brush54"], "B_with230.dx"),
    ):
        nm = build_native(names, level)
        em = parse_golden(OUT_DIR / golden_file)
        cn, ce = counts(nm), counts(em)
        print(f"=== {tag} ({','.join(names)}) ===")
        print(f"  native: " + " ".join(f"{l}={v}" for l, v in zip(labels, cn)))
        print(f"  editor: " + " ".join(f"{l}={v}" for l, v in zip(labels, ce)))
        print(f"  delta:  " + " ".join(f"{l}={b-a:+d}" for l, a, b in zip(labels, ce, cn)))


if __name__ == "__main__":
    raise SystemExit(main())
