#!/usr/bin/env python3
"""Split `Model.Lights` (UModel+0xe4) into its two regions and report each.

`Model.Lights` is not just the per-surface shadow runs. Per spike section 20 §21 (A) it has two:
region 1 = the per-LEAF permeating-light lists, indexed by `FLeaf.iPermeating`; region 2 = the
per-SURFACE shadow runs, indexed by `FLightMapIndex.iLightActors`. This walks both index sets and
prints the span each covers, so "how much of the array does native omit" is a measured number.

Usage: lights_regions.py MAP.dx [MAP.dx ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lightparity import _load, level_model  # noqa: E402


def run_span(names, start):
    """`(length)` of the NULL-terminated run at `start`."""
    i = start
    while i < len(names) and names[i] is not None:
        i += 1
    return i - start


def main() -> int:
    repo = str(Path(__file__).resolve().parents[5])
    upackage, umodel = _load(repo)
    for path in sys.argv[1:]:
        pkg, m = level_model(upackage, umodel, path)
        names = [None if r == 0 else pkg.name_of_ref(r) for r in m.lights]
        surf_starts = sorted({r.i_light_actors for r in m.light_map if r.i_light_actors >= 0})
        leaf_starts = sorted({lf.i_permeating for lf in m.leaves
                              if getattr(lf, "i_permeating", -1) >= 0})
        vol_starts = sorted({lf.i_volumetric for lf in m.leaves
                             if getattr(lf, "i_volumetric", -1) >= 0})

        def span(starts):
            if not starts:
                return (None, None, 0)
            end = max(s + run_span(names, s) + 1 for s in starts)   # +1 for the NULL
            return (min(starts), end, sum(run_span(names, s) for s in starts))

        print(f"\n{path}")
        print(f"  Lights entries: {len(m.lights)}   leaves: {len(m.leaves)}   "
              f"records: {len(m.light_map)}")
        for label, starts in (("per-leaf iPermeating", leaf_starts),
                              ("per-leaf iVolumetric", vol_starts),
                              ("per-surf iLightActors", surf_starts)):
            lo, hi, tot = span(starts)
            print(f"  {label:22} {len(starts):5} distinct starts, span [{lo},{hi}), "
                  f"{tot} run entries")
        print(f"  leaves with iPermeating >= 0: "
              f"{sum(getattr(lf, 'i_permeating', -1) >= 0 for lf in m.leaves)}/{len(m.leaves)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
