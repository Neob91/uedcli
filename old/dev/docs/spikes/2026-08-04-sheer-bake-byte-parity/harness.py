#!/usr/bin/env python3
"""Live sheer-bake byte-parity harness (spike 2026-08-04-sheer-bake-byte-parity).

Drives a REAL UnrealEd editor (a named container) over the corpus in
`uedcli.tests.test_scale_integration._CASES` — cube plus complex 16-gon / staircase brushes under
every SheerAxis and scale+sheer / rotation / prepivot combos — and, per case, checks BOTH:

  (a) world-vertex parity: `transform.bake` (offline) vs the editor's own `ACTOR APPLYTRANSFORM`
      (same corner count, worst |Δ| ≤ tol);
  (b) `emit_fscale` byte-match: the un-baked scaled brush's `MainScale`/`PostScale` re-export
      substring must appear verbatim in the editor's `MAP EXPORT`.

This is the runnable half; `test_scale_integration.py` pins the same corpus as a gated
(`-m integration`) regression. Run offline (build/bake only, no editor) to sanity-check the corpus:

    .venv/bin/python dev/docs/spikes/2026-08-04-sheer-bake-byte-parity/harness.py --offline

Or against an ephemeral editor container:

    .venv/bin/python dev/docs/spikes/2026-08-04-sheer-bake-byte-parity/harness.py \
        --container uned-sheer-XXX --json /path/out.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from decimal import Decimal

from uedcli import rotation as R, transform as T
from uedcli.builders import make_brush_actor
from uedcli.driver import Driver
from uedcli.emit import emit_map
from uedcli.model import parse_t3d
from uedcli.tests.test_scale_integration import _CASES

PARITY_TOL = 1e-4
D = Decimal


def _predicted(name: str):
    case = _CASES[name]
    a = make_brush_actor("ScaleIT", case.make_brush(), location=(D(0), D(0), D(0)))
    case.setup(a)
    baked = T.bake(a)
    verts = sorted({tuple(round(c, 6) for c in w) for w in R.world_vertices(baked)})
    return a, verts


def _emit_actor(name: str):
    case = _CASES[name]
    a = make_brush_actor("ScaleEmit", case.make_brush(), location=(D(0), D(0), D(0)))
    case.setup(a)
    return a


def _write(container: str, path: str, content: str) -> None:
    subprocess.run(["docker", "exec", "-i", container, "tee", path],
                   input=content, text=True, capture_output=True, check=True)


def _read(container: str, path: str) -> str:
    return subprocess.run(["docker", "exec", container, "cat", path],
                          text=True, capture_output=True, check=True).stdout


def _cpath(tag: str) -> str:
    return f"/work/sheerit_{tag}_{uuid.uuid4().hex}.t3d"


def _world_from_export(t3d: str, actor_name: str):
    ed = parse_t3d(t3d).actors.get(actor_name)
    if ed is None or ed.brush is None:
        return None, ed
    return sorted({tuple(round(c, 6) for c in w) for w in R.world_vertices(ed)}), ed


def _worst(pred, obs) -> float:
    if not pred or not obs:
        return float("inf")
    return max(min(max(abs(p[i] - o[i]) for i in range(3)) for p in pred) for o in obs)


def run_case(driver: Driver, name: str) -> dict:
    a, predicted = _predicted(name)
    ipath, opath = _cpath(name + "_in"), _cpath(name + "_out")
    _write(driver.container, ipath, emit_map([a]))
    driver.map_new()
    driver.set_grid(1, 1, 1)
    driver.map_importadd(ipath)
    driver.selectname("ScaleIT")
    driver.exec("ACTOR APPLYTRANSFORM")
    driver.map_export(opath)
    editor, ed = _world_from_export(_read(driver.container, opath), "ScaleIT")

    res: dict = {"name": name, "predicted_corners": len(predicted)}
    if editor is None:
        res.update(parity="FAIL", reason="no brush in editor export", editor_corners=0)
        return res
    res["editor_corners"] = len(editor)
    if len(editor) != len(predicted):
        res.update(parity="FAIL", reason=f"corner count {len(editor)} vs {len(predicted)}")
        return res
    err = max(_worst(predicted, editor), _worst(editor, predicted))
    res["worst_uu"] = err
    fields_reset = ((ed.main_scale is None or ed.main_scale.is_identity())
                    and (ed.post_scale is None or ed.post_scale.is_identity()))
    res["fields_reset"] = fields_reset
    res["parity"] = "PASS" if (err <= PARITY_TOL and fields_reset) else "FAIL"
    return res


def run_emit_case(driver: Driver, name: str) -> dict:
    a = _emit_actor(name)
    ipath, opath = _cpath(name + "_ein"), _cpath(name + "_eout")
    _write(driver.container, ipath, emit_map([a]))
    driver.map_new()
    driver.map_importadd(ipath)
    driver.map_export(opath)
    raw = _read(driver.container, opath)
    checks = []
    for field, fs in (("MainScale", a.main_scale), ("PostScale", a.post_scale)):
        if fs is not None and not fs.is_identity():
            want = f"{field}={T.emit_fscale(fs)}"
            checks.append((field, want, want in raw))
    ok = all(c[2] for c in checks)
    return {"name": name, "emit": "PASS" if ok else "FAIL",
            "checks": [{"field": f, "want": w, "found": found} for f, w, found in checks]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--container")
    ap.add_argument("--offline", action="store_true", help="build+bake only, no editor")
    ap.add_argument("--json")
    ap.add_argument("--only", help="comma-separated case names")
    args = ap.parse_args()

    names = sorted(_CASES) if not args.only else args.only.split(",")

    if args.offline:
        rows = []
        for name in names:
            a, verts = _predicted(name)
            rows.append((name, len(verts)))
            print(f"  {name:24s} corners={len(verts)}")
        print(f"offline: {len(rows)} cases built + baked OK")
        return 0

    driver = Driver(container=args.container)
    results = []
    worst_overall = 0.0
    fails = []
    for name in names:
        try:
            parity = run_case(driver, name)
            emit = run_emit_case(driver, name)
        except Exception as e:  # keep going; record the failure
            parity = {"name": name, "parity": "ERROR", "reason": repr(e)}
            emit = {"name": name, "emit": "ERROR"}
        row = {**parity, **{k: v for k, v in emit.items() if k != "name"}}
        results.append(row)
        w = row.get("worst_uu")
        if isinstance(w, float) and w != float("inf"):
            worst_overall = max(worst_overall, w)
        if row.get("parity") not in ("PASS",) or row.get("emit") not in ("PASS",):
            fails.append(name)
        print(f"  {name:24s} parity={row.get('parity'):5s} "
              f"worst={row.get('worst_uu', 'n/a')} emit={row.get('emit')}", flush=True)

    summary = {"total": len(results), "fails": fails, "worst_uu": worst_overall,
               "results": results}
    if args.json:
        with open(args.json, "w") as f:
            json.dump(summary, f, indent=2)
    print(f"\nDONE: {len(results)} cases, {len(fails)} fail, worst {worst_overall:.2e}uu")
    if fails:
        print("FAILS: " + ", ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
