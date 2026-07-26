#!/usr/bin/env python3
"""Check `texalign_model.frame` against EVERY measured face of EVERY captured mode, and emit the
distilled golden the regression test consumes.

    verify_model.py <outdir> [<golden.json>]
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
from uedcli.preview import _face_normal                               # noqa: E402
from uedcli.preview_native import _world_uv_frame                     # noqa: E402

# bound texture -> VSize (needed only by CLAMP)
VSIZE = {"ex_bricks": 256, "aircount_a00": 64, "calendar_2": 256}

VEC_TOL = 2e-3          # bspAddVector(…, Exact=0) shares near-equal vectors
PT_TOL = 0.2            # bspAddPoint + the float32 local<->world round trip


def collect(path: Path):
    """{(brush, poly): dict} of the measured world frame + geometry for one export."""
    lvl = parse_t3d(path.read_text())
    out = {}
    for name, a in lvl.actors.items():
        if a.brush is None:
            continue
        oper = dict(a.props or {}).get("CsgOper") if isinstance(a.props, dict) else \
            next((v for k, v in (a.props or []) if k == "CsgOper"), None)
        if oper is None:
            continue                                    # the red builder brush
        for i, p in enumerate(a.brush.polys):
            wv = _world_verts(a, p)
            if len(wv) < 3:
                continue
            n = _face_normal(wv)
            m = math.sqrt(sum(c * c for c in n))
            if m < 1e-9:
                continue
            n_poly = tuple(c / m for c in n)
            sign = -1.0 if oper == "CSG_Subtract" else 1.0
            base, tu, tv, pan = _world_uv_frame(a, p)
            out[(name, i)] = dict(n_poly=n_poly,
                                  n_surf=tuple(sign * c for c in n_poly),
                                  verts=[tuple(float(c) for c in v) for v in wv],
                                  base=base, tu=tu, tv=tv, pan=(pan[0], pan[1]),
                                  tex=(p.texture or "").lower())
    return out


def R(v):
    """6-dp rounding: the golden must not carry float noise the export never had (the T3D itself is
    written at 6 decimal places)."""
    return [round(float(c), 6) for c in v]


def close(a, b, tol):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def main():
    outdir = Path(sys.argv[1])
    golden_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    ref = collect(outdir / "NONE.t3d")
    golden = {"_note": "measured POLY TEXALIGN output, uned/UED22, spike "
                       "2026-07-26-unrealed-texalign-semantics",
              "faces": {}, "modes": {}}
    for key, f in sorted(ref.items()):
        golden["faces"][f"{key[0]}:{key[1]}"] = {
            "n_poly": R(f["n_poly"]), "n_surf": R(f["n_surf"]),
            "verts": [R(v) for v in f["verts"]], "tex": f["tex"],
            "base": R(f["base"]), "tu": R(f["tu"]), "tv": R(f["tv"]),
            "pan": [int(f["pan"][0]), int(f["pan"][1])]}

    bad = 0
    total = 0
    for mode in ["DEFAULT", "FLOOR", "WALLDIR", "WALLX", "WALLY", "WALLPAN", "WALLCOLUMN",
                 "ONETILE", "CLAMP"]:
        p = outdir / f"{mode}.t3d"
        if not p.exists():
            continue
        got = collect(p)
        golden["modes"][mode] = {}
        for key, g in sorted(got.items()):
            r = ref[key]
            golden["modes"][mode][f"{key[0]}:{key[1]}"] = {
                "base": R(g["base"]), "tu": R(g["tu"]), "tv": R(g["tv"]),
                "pan": [int(g["pan"][0]), int(g["pan"][1])]}
            pred = M.frame(mode, r["n_surf"], r["n_poly"], r["verts"],
                           r["base"], r["tu"], r["tv"], r["pan"], VSIZE.get(r["tex"], 0))
            if pred is None:
                pred = (r["base"], r["tu"], r["tv"], r["pan"])
            total += 1
            ok = (close(pred[0], g["base"], PT_TOL) and close(pred[1], g["tu"], VEC_TOL)
                  and close(pred[2], g["tv"], VEC_TOL) and tuple(pred[3]) == tuple(g["pan"]))
            if not ok:
                bad += 1
                print(f"MISMATCH {mode} {key[0]}:{key[1]}")
                print(f"   n_surf={r['n_surf']}")
                print(f"   pred base={pred[0]} tu={pred[1]} tv={pred[2]} pan={pred[3]}")
                print(f"   got  base={g['base']} tu={g['tu']} tv={g['tv']} pan={g['pan']}")
    print(f"\n{total - bad}/{total} (mode, face) predictions match")
    if golden_path:
        golden_path.write_text(json.dumps(golden, sort_keys=True,
                                          separators=(",", ":")) + "\n")
        print(f"wrote {golden_path} ({golden_path.stat().st_size} bytes)")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
