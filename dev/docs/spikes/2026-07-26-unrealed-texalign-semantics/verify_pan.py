#!/usr/bin/env python3
"""Check `texalign_model.frame`'s PAN prediction against the probe3 captures, and emit the golden.

The main fixture cannot test the pan at all — every one of its faces already carried `Pan = (0,0)`,
so "the mode zeroes it" and "the mode leaves it alone" produce identical exports. probe3 authors
`Pan U=7 V=13` on every face first, which separates them.

    verify_pan.py <outdir3> [<pans.json>]
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import texalign_model as M                                            # noqa: E402
from uedcli.model import parse_t3d                                    # noqa: E402
from uedcli.polyalign import _world_verts                             # noqa: E402
from uedcli.texframe import newell, world_uv_frame                    # noqa: E402

VSIZE = {"ex_bricks": 256, "aircount_a00": 64, "calendar_2": 256}
AUTHORED_PAN = (7, 13)
MODES = ["WALLCOLUMN", "ONETILE", "WALLPAN", "FLOOR", "WALLDIR", "DEFAULT",
         "WALLX", "WALLY", "CLAMP"]


def collect(path: Path):
    lvl = parse_t3d(path.read_text())
    out = {}
    for name, a in lvl.actors.items():
        if a.brush is None or not any(k == "CsgOper" for k, _ in (a.props or [])):
            continue
        oper = next(v for k, v in a.props if k == "CsgOper")
        for i, p in enumerate(a.brush.polys):
            wv = _world_verts(a, p)
            if len(wv) < 3:
                continue
            n = newell(wv)
            m = math.sqrt(sum(c * c for c in n))
            if m < 1e-9:
                continue
            n_poly = tuple(c / m for c in n)
            sign = -1.0 if oper == "CSG_Subtract" else 1.0
            base, tu, tv, pan = world_uv_frame(a, p)
            out[f"{name}:{i}"] = {
                "n_poly": [round(c, 6) for c in n_poly],
                "n_surf": [round(sign * c, 6) for c in n_poly],
                "verts": [[round(float(c), 6) for c in v] for v in wv],
                "tex": (p.texture or "").lower(),
                "base": [round(c, 6) for c in base],
                "tu": [round(c, 6) for c in tu], "tv": [round(c, 6) for c in tv],
                "pan": [int(pan[0]), int(pan[1])]}
    return out


def main():
    outdir = Path(sys.argv[1])
    ctrl = collect(outdir / "pan-CTRL.t3d")
    assert {tuple(f["pan"]) for f in ctrl.values()} == {AUTHORED_PAN}, \
        "the control does not carry the authored non-zero pan on every face"

    golden = {"_note": "POLY TEXALIGN with a NON-ZERO authored pan (U=7 V=13) on every face — the "
                       "only capture that can tell 'zeroes the pan' from 'leaves it alone'. Spike "
                       "2026-07-26-unrealed-texalign-semantics.",
              "authored_pan": list(AUTHORED_PAN),
              "faces": {k: {"n_surf": v["n_surf"], "n_poly": v["n_poly"], "verts": v["verts"],
                            "tex": v["tex"], "base": v["base"], "tu": v["tu"], "tv": v["tv"]}
                        for k, v in ctrl.items()},
              "pans": {}}

    bad = total = 0
    for mode in MODES:
        got = collect(outdir / f"pan-{mode}.t3d")
        golden["pans"][mode] = {k: v["pan"] for k, v in got.items()}
        for ref, g in got.items():
            c = ctrl[ref]
            pred = M.frame(mode, c["n_surf"], c["n_poly"], c["verts"],
                           c["base"], c["tu"], c["tv"], tuple(AUTHORED_PAN),
                           VSIZE[c["tex"]])
            want = list(AUTHORED_PAN) if pred is None else [int(pred[3][0]), int(pred[3][1])]
            total += 1
            if want != g["pan"]:
                bad += 1
                print(f"MISMATCH {mode} {ref}: predicted {want}, editor wrote {g['pan']}")
    print(f"\n{total - bad}/{total} (mode, face) PAN predictions match")
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(
            json.dumps(golden, sort_keys=True, separators=(",", ":")) + "\n")
        print(f"wrote {sys.argv[2]}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
