#!/usr/bin/env python3
"""UNATCO N-brush subset differential — the §92 stage-1 pin tool (the UNATCO analog of the castle's
`subset_diff.py`).

Bisects the SMALLEST brush-prefix N at which native's `build_geometry_bspcsg` surf set first diverges
from UnrealEd's build of the SAME N-brush prefix — the concrete first-diverging brush the §92 §3
+82-surf residual is born at.

Why the FINAL surf set (not the Model.Polys soup): on UNATCO a full editor rebuild DISCARDS the brush
Polys soup (the golden's `Model.Polys` export is a near-empty 78 — unlike the castle's 853), so
`soup_cmp.py`'s soup key cannot bisect here. But surfs are ALLOCATED in the incremental CSG phase and
KEPT by any `BSP REBUILD` (`EmptyModel(0,0)`, §82 §10.16 / §92 §3), so the golden's FINAL `Model.Surfs`
IS the incremental-CSG surf set. We compare the order-independent surf multiset under the same geo key
`surf_class_diff.surf_geokey` = (normal@1e-3, plane-offset@1e-2, polyflag-class).

  * NATIVE — `uedcli_native.build_geometry_bspcsg` over the first N brush inputs (trunk order),
             serialized + re-parsed (identical to soup_cmp `_brushes(n)`), its `Model.surfs`.
  * EDITOR — a subset trunk (LevelInfo + first N brush actors) editor-materialized to `golden{N}.dx`
             via `build_ued_golden.py` (bare `MAP REBUILD` default — retains surfs, fast, less
             crash-prone than a ZONES rebuild), its largest-`Model` surfs.  CACHED.

The editor build is the expensive, crash-prone part — build_ued_golden's generous idle barrier
(`--quiet-reads 30`) is REQUIRED at UNATCO scale (§92 stage 0: an 8-read barrier mis-detects an
inter-phase rebuild lull as idle and corrupts/loses the save).  Cached under `_scratch/unatco-subset/`.

Usage:
  unatco_subset.py build N          # editor-materialize the N-brush subset -> golden{N}.dx (cached)
  unatco_subset.py diff N           # native N-brush surfs vs cached golden{N}.dx (build golden if absent)
  unatco_subset.py bisect LO HI     # binary-search the first-divergence N in [LO,HI]
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]      # Tools/uedcli (harness/ -> spike/ -> spikes/ -> docs/ -> dev/ -> root)
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HARNESS))

from spike_classindex import class_index  # noqa: E402  (schema-aware mover gate's index)
from uedcli import trunk  # noqa: E402
from uedcli.native import materialize as M, umodel as UM  # noqa: E402
from uedcli.native import brush_marshal as BM  # noqa: E402  (_in_world_csg/_build_brush_input live here now)
import uedcli_native  # noqa: E402
import surf_class_diff as SCD  # noqa: E402

FULL_TRUNK = Path(os.environ.get("UEDCLI_UNATCO_TRUNK", ROOT / "_scratch/unatco/uedcli/maps/unatco"))
SUBSET_ROOT = ROOT / "_scratch/unatco-subset"
BUILDER = HARNESS / "build_ued_golden.py"
PYTHON = ROOT / ".venv/bin/python"


def _brush_order(level):
    return [n for n in level.order if level.actors[n].brush is not None]


def golden_path(n: int) -> Path:
    return SUBSET_ROOT / f"golden{n}.dx"


def _make_subset_trunk(n: int) -> Path:
    """Subset project dir `<SUBSET_ROOT>/trunk{n}` with maps/unatco holding LevelInfo + first N
    brush actors (non-brush point actors are dropped: --world-only keeps only Brush+LevelInfo)."""
    level, _ = trunk.read_level(FULL_TRUNK)
    brushes = _brush_order(level)
    keep = set(brushes[:n])
    proj = SUBSET_ROOT / f"trunk{n}"
    dst = proj / "maps" / "unatco"
    if dst.exists():
        shutil.rmtree(dst)
    dst_actors = dst / "actors"
    dst_actors.mkdir(parents=True)
    src_actors = FULL_TRUNK / "actors"
    for name in level.order:
        a = level.actors[name]
        cls = a.cls.split(".")[-1]
        if a.brush is not None and name not in keep:
            continue
        if a.brush is None and cls != "LevelInfo":
            continue
        shutil.copytree(src_actors / name, dst_actors / name)
    return dst


def build_editor_subset(n: int, force: bool = False, quiet_reads: int = 30) -> Path:
    out = golden_path(n)
    if out.exists() and not force:
        return out
    subset_trunk = _make_subset_trunk(n)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(PYTHON), str(BUILDER), "--trunk", str(subset_trunk), "--out", str(out),
           "--world-only", "--no-light", "--no-obj-load", "--overwrite",
           "--quiet-reads", str(quiet_reads), "--rebuild-min-seconds", "20"]
    print(f"[subset] editor-building N={n} ...", flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    tail = "\n".join(r.stdout.splitlines()[-6:])
    if r.returncode != 0 or not out.exists():
        print(tail); print(r.stderr[-2000:], file=sys.stderr)
        raise SystemExit(f"editor subset build N={n} FAILED (rc={r.returncode})")
    print(f"[subset] N={n} -> {out}\n    {tail.splitlines()[-1] if tail else ''}", flush=True)
    return out


def native_surfs(n: int):
    level, _ = trunk.read_level(FULL_TRUNK)
    # Mirror the real materialize world-CSG input: the trunk (and the editor golden's subset trunk)
    # carries all N brush actors including Movers, but ONLY non-mover ("world") brushes feed the CSG
    # core — UnrealEd keeps a Mover's brush as the Mover's own private Model and never CSGs it into
    # the world (materialize._in_world_csg / spike §92).  Feeding the 28 DeusExMovers into world CSG
    # was the harness confound: it over-produced surfs the editor golden never had (leftover-only-
    # native ~170 at N=396, purely the mover contribution), contradicting the real build.  Take the
    # first N brush actors in trunk order, then drop the movers — matching the editor's own exclusion.
    brushes = [nm for nm in _brush_order(level)[:n] if BM._in_world_csg(level.actors[nm], class_index())]
    bs = [BM._build_brush_input(nm, level.actors[nm]) for nm in brushes]
    m = uedcli_native.build_geometry_bspcsg(bs)
    body = uedcli_native.serialize_model(m)
    return UM.parse_model_body(body, 0, len(body))


def _reduce_key(k):
    """Collapse a full surf geokey (normal@1e-3, plane-offset@1e-2, class) down to the
    OFFSET-INDEPENDENT key (normal, class) — so surfs on parallel/near-coincident planes of the
    same facing + polyflag-class become one bucket."""
    return (k[0], k[2])


def leftover_only(kn: Counter, kg: Counter):
    """The leftover-only-native / leftover-only-editor metric (§92 §12).

    Cancel each only-native surf 1:1 against an only-editor surf sharing the SAME rounded normal +
    polyflag-class REGARDLESS of plane offset (parallel near-coincident planes are "precision twins"
    of one intended face). What survives that cancellation is GENUINE over-/under-production:

      * leftover-only-native  — native emits more surfs of a (normal,class) than the editor keeps
        (structural OVER-fragmentation / over-production).
      * leftover-only-editor  — the editor keeps more (native UNDER-produces).

    Cancelling exact-offset matches first (kn-kg) then cancelling across offset is equivalent to
    cancelling by the reduced (normal,class) key over the FULL surf multisets, so we do the latter
    directly. Returns (Counter leftover_onlyN, Counter leftover_onlyE) keyed by (normal, class)."""
    rn, rg = Counter(), Counter()
    for k, c in kn.items():
        rn[_reduce_key(k)] += c
    for k, c in kg.items():
        rg[_reduce_key(k)] += c
    lo_n, lo_e = Counter(), Counter()
    for r in set(rn) | set(rg):
        d = rn[r] - rg[r]
        if d > 0:
            lo_n[r] = d
        elif d < 0:
            lo_e[r] = -d
    return lo_n, lo_e


def diff(n: int, force: bool = False):
    ed_path = build_editor_subset(n, force=force)
    native = native_surfs(n)
    golden = SCD.load_model(str(ed_path))
    kn = Counter(SCD.surf_geokey(native, s) for s in native.surfs)
    kg = Counter(SCD.surf_geokey(golden, s) for s in golden.surfs)
    onlyN, onlyE = kn - kg, kg - kn
    lo_n, lo_e = leftover_only(kn, kg)
    return {
        "n": n, "nat_surfs": len(native.surfs), "ed_surfs": len(golden.surfs),
        "shared": sum((kn & kg).values()), "onlyN": sum(onlyN.values()),
        "onlyE": sum(onlyE.values()), "onlyN_set": onlyN, "onlyE_set": onlyE,
        "leftover_onlyN": sum(lo_n.values()), "leftover_onlyE": sum(lo_e.values()),
        "leftover_onlyN_set": lo_n, "leftover_onlyE_set": lo_e,
    }


def _print_row(d):
    print(f"N={d['n']:>4}  natSurf={d['nat_surfs']:>5} edSurf={d['ed_surfs']:>5}  "
          f"shared={d['shared']:>5}  only-native={d['onlyN']:>4}  only-editor={d['onlyE']:>4}"
          f"  |  leftover-onlyN={d['leftover_onlyN']:>4} leftover-onlyE={d['leftover_onlyE']:>4}"
          f"  {'DIVERGES' if (d['onlyN'] or d['onlyE']) else 'MATCH'}", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("n", type=int); b.add_argument("--force", action="store_true")
    d = sub.add_parser("diff"); d.add_argument("n", type=int); d.add_argument("--force", action="store_true")
    d.add_argument("--top", type=int, default=15)
    s = sub.add_parser("bisect"); s.add_argument("lo", type=int); s.add_argument("hi", type=int)
    s.add_argument("--metric", choices=["onlyN", "any", "leftover"], default="onlyN",
                   help="onlyN (DEFAULT): first N where native OVER-produces a surf the editor lacks "
                        "(the unconfounded +82 origin; only-editor under-production early is the "
                        "subtract-into-void convention artifact — §92 stage 1). any: first N with any diff. "
                        "leftover: first N where leftover-only-native (1:1 normal+class cancel across "
                        "plane offset — genuine axis-aligned over-production, §92 §12) first exceeds 0. "
                        "The plain onlyN bisect is DEGENERATE over [105,762] (nonzero floor). NOTE: the "
                        "old leftover(396)=170 was the MOVER CONFOUND (native fed the 28 DeusExMovers "
                        "into world CSG while the editor golden excludes them); native_surfs now drops "
                        "movers to mirror materialize._in_world_csg, so leftover(396)=0 and the CSG-core "
                        "residual vs the world golden is small (native 3609 vs golden 3616 at N=762).")
    args = ap.parse_args()

    if args.cmd == "build":
        print(build_editor_subset(args.n, force=args.force))
    elif args.cmd == "diff":
        res = diff(args.n, force=args.force)
        _print_row(res)
        if res["onlyN"]:
            print("  top only-native (normal, offset, class):")
            for k, c in res["onlyN_set"].most_common(args.top):
                print(f"    {k}  x{c}")
        if res["onlyE"]:
            print("  top only-editor (normal, offset, class):")
            for k, c in res["onlyE_set"].most_common(args.top):
                print(f"    {k}  x{c}")
        if res["leftover_onlyN"]:
            print("  leftover-only-native (normal, class) [1:1 offset-cancelled — genuine over-prod]:")
            for k, c in res["leftover_onlyN_set"].most_common(args.top):
                print(f"    {k}  x{c}")
        if res["leftover_onlyE"]:
            print("  leftover-only-editor (normal, class) [genuine under-prod]:")
            for k, c in res["leftover_onlyE_set"].most_common(args.top):
                print(f"    {k}  x{c}")
    elif args.cmd == "bisect":
        lo, hi = args.lo, args.hi
        results = {}
        def dv(n):
            if n not in results:
                results[n] = diff(n)
                _print_row(results[n])
            r = results[n]
            if args.metric == "leftover":
                return bool(r["leftover_onlyN"])
            return bool(r["onlyN"]) if args.metric == "onlyN" else bool(r["onlyN"] or r["onlyE"])
        # invariant: dv(lo) False (no over-production yet), dv(hi) True. find first N with over-production.
        dv(lo); dv(hi)
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if dv(mid):
                hi = mid
            else:
                lo = mid
        print(f"\n*** FIRST {args.metric} DIVERGENCE at N={hi} (N={lo} clean) ***")
        if results.get(hi):
            if args.metric == "leftover":
                print("  leftover-only-native (normal, class) at first-divergence N:")
                for k, c in results[hi]["leftover_onlyN_set"].most_common(20):
                    print(f"    {k}  x{c}")
            else:
                print("  over-produced (only-native) surfs at first-divergence N:")
                for k, c in results[hi]["onlyN_set"].most_common(20):
                    print(f"    {k}  x{c}")


if __name__ == "__main__":
    main()
