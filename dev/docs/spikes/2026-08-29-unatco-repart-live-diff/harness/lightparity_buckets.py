#!/usr/bin/env python3
"""Classify per-record `LightMap` divergences into the "three remaining gaps" buckets used by
`native-light-apply-bake-where-it-stands-and` (grid / run / bits / pan-scale), first-match priority:

  1. grid    -- u_size/v_size differ (not one of the three named gaps, separate & tiny)
  2. run     -- light run (set+order) differs -- gap 1, light runs / MergeWith
  3. bits    -- shadow bits differ, run+grid+pan+scale all agree -- per-lumel shadow-ray precision
  4. pan/scale -- pan/u_scale/v_scale differ, run+grid+bits all agree -- gap 3, Points/geometry residual

Reuses `lightparity.py`'s loaders so the classification is against the SAME data that produces its
own summary numbers.

Usage: lightparity_buckets.py NATIVE.dx EDITOR.dx
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "2026-08-27-native-light-apply-parity/harness"))
from lightparity import _load, level_model, light_names, runs, planes  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    native, editor = sys.argv[1], sys.argv[2]
    repo = str(Path(__file__).resolve().parents[5])
    upackage, umodel = _load(repo)
    npkg, nm = level_model(upackage, umodel, native)
    epkg, em = level_model(upackage, umodel, editor)
    nruns = runs(nm, light_names(npkg, nm))
    eruns = runs(em, light_names(epkg, em))

    common = min(len(nm.light_map), len(em.light_map))
    buckets = {"grid": 0, "run": 0, "bits": 0, "pan_scale": 0}
    total_bad = 0
    for k in range(common):
        a, b = nm.light_map[k], em.light_map[k]
        nr, er = nruns[k], eruns[k]
        grid = a.u_size != b.u_size or a.v_size != b.v_size
        run_bad = nr != er
        pan_scale = a.pan != b.pan or a.u_scale != b.u_scale or a.v_scale != b.v_scale
        bits_bad = planes(nm, a, len(nr)) != planes(em, b, len(er))
        if not (grid or run_bad or pan_scale or bits_bad):
            continue
        total_bad += 1
        if grid:
            buckets["grid"] += 1
        elif run_bad:
            buckets["run"] += 1
        elif bits_bad:
            buckets["bits"] += 1
        elif pan_scale:
            buckets["pan_scale"] += 1

    print(f"common records: {common}, bad records: {total_bad}, "
          f"identical: {common - total_bad} ({100.0 * (common - total_bad) / common:.1f}%)")
    for name in ("grid", "run", "bits", "pan_scale"):
        n = buckets[name]
        pct = 100.0 * n / total_bad if total_bad else 0.0
        print(f"  {name:10} {n:6}  ({pct:.1f}% of bad)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
