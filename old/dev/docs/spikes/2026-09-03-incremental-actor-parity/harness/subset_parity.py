#!/usr/bin/env python3
"""Incremental first-N-brush parity — the generalized, level-agnostic, full geometry+lighting
version of `2026-07-15-native-materialize/harness/unatco_subset.py`.

The method (owner request 2026-09-03): build the first N world-CSG brushes of a level BOTH ways —
UnrealEd (`build_ued_lit_golden`: `MAP NEW` -> `EDIT PASTE` -> `MAP REBUILD` -> `LIGHT APPLY`) and
native (`uedcli_native.build_geometry_bspcsg` + `assemble_unbuilt`) — and compare full geometry
(nodes/surfs/leaves/verts/points/vectors counts + index-for-index node/surf/leaf CONTENT) AND
lighting (per-record LightMap + shadow bits). Ramp N (or bisect) to isolate the first brush at which
native diverges from the editor, then fix, then continue.

"First N actors" from the owner's request means the first N WORLD-CSG brushes: non-brush actors
(LevelInfo, lights, point actors) don't participate in CSG, and Movers keep a private model the world
BSP never sees — so the subset keeps EVERY non-(world-CSG-brush) actor (lights included, so lighting
is well defined) and only truncates the world-CSG brush tail. This mirrors what both build sides
already filter to at whole-level scale (native `build_native_model` / `build_native_lit_dx` and the
editor `build_ued_lit_golden`), so a subset row is directly comparable to a whole-level
`parity_report.py` row.

Unlike `unatco_subset.py` (surf-multiset only, UNATCO trunk hardcoded), this reuses the maintained
`parity_compare` + `build_ued_lit_golden` code paths, so its numbers match `parity_report.py`'s for
the same trunk+golden, and it works for any level whose trunk `parity_pipeline` can extract.

Usage (venv python):
  subset_parity.py --dx <shipped.dx> build N          # editor-build the N-brush subset golden (cached)
  subset_parity.py --dx <shipped.dx> diff  N          # native-vs-golden full parity for N (builds golden if absent)
  subset_parity.py --dx <shipped.dx> bisect LO HI     # first N in [LO,HI] where geometry diverges
  subset_parity.py --dx <shipped.dx> count            # how many world-CSG brushes the level has

`--trunk <dir>` overrides trunk extraction (use an already-extracted trunk). The editor golden build
is the slow, crash-prone half — run under a bounded background job. Goldens cache under
`_scratch/subset-parity/<level>/goldenN.dx`; subset trunks under `_scratch/subset-parity/<level>/N<n>/`.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
REPORT_HARNESS = ROOT / "dev/docs/spikes/2026-08-31-native-parity-report/harness"
NATIVE_MAT_HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
LIT_GOLDEN = (ROOT / "dev/docs/spikes/2026-08-27-native-light-apply-parity/harness"
              / "build_ued_lit_golden.py")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(REPORT_HARNESS))
sys.path.insert(0, str(NATIVE_MAT_HARNESS))

import parity_compare as pc   # noqa: E402
import parity_pipeline as pp  # noqa: E402
import parity_lib as pl       # noqa: E402
from uedcli import trunk      # noqa: E402
from uedcli.native import brush_marshal as BM  # noqa: E402

PYTHON = ROOT / ".venv/bin/python"
SUBSET_ROOT = ROOT / "_scratch/subset-parity"


def _resolve_trunk(dx_path: Path, trunk_override: str | None, *, game: str) -> tuple[Path, str]:
    """(full trunk dir, level name). Reuse the parity cache's extracted+qualified trunk unless
    `--trunk` overrides it — the cached trunk is already fully class-qualified, which LIGHT APPLY and
    the native lighting bake both require. Extracts the trunk only; never triggers a whole-level
    golden build."""
    if trunk_override:
        t = Path(trunk_override).resolve()
        if not (t / "actors").is_dir():
            raise SystemExit(f"not a trunk dir: {t}")
        return t, t.name
    name = pp.level_name(dx_path)
    h = pl.content_hash(dx_path)
    trunk_dir = pp.build_root(h) / "maps" / name
    if not pp.trunk_is_complete(trunk_dir):
        pp.extract_trunk(dx_path, trunk_dir, game=game,
                         log_path=pl.cache_layout(pl.CACHE_ROOT_DEFAULT, h).root / "extract.log",
                         timeout=1800.0)
    return trunk_dir, name


def _world_brush_order(level, ci) -> list[str]:
    """Names of the world-CSG brushes in trunk order — exactly native's own CSG input set
    (`build_native_model`: brush present AND `_in_world_csg`)."""
    return [n for n in level.order
            if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]


def _make_subset_trunk(full_trunk: Path, name: str, n: int, ci) -> Path:
    """`<SUBSET_ROOT>/<level>/N<n>/maps/<level>/` holding every non-(world-CSG-brush) actor plus the
    first N world-CSG brushes (trunk order). A project `uedcli.toml` is written at the subset root so
    `UEDCLI_PROJECT` resolves for the native side."""
    level, _ = trunk.read_level(full_trunk)
    brushes = _world_brush_order(level, ci)
    drop = set(brushes[n:])
    proj = SUBSET_ROOT / name / f"N{n}"
    dst = proj / "maps" / name
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "actors").mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\nmaps = "maps"\n')
    for an in level.order:
        if an in drop:
            continue
        shutil.copytree(full_trunk / "actors" / an, dst / "actors" / an)
    return dst


def golden_path(name: str, n: int, world_only: bool) -> Path:
    return SUBSET_ROOT / name / f"golden{'_wo' if world_only else ''}{n}.dx"


def build_editor_subset(full_trunk: Path, name: str, n: int, ci, *, world_only: bool,
                        force: bool = False, timeout: float = 3600.0) -> Path:
    out = golden_path(name, n, world_only)
    if out.exists() and not force:
        return out
    subset = _make_subset_trunk(full_trunk, name, n, ci)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(PYTHON), str(LIT_GOLDEN), "--trunk", str(subset), "--out", str(out),
           "--overwrite", "--quiet-reads", "30", "--rebuild-timeout", str(timeout)]
    if world_only:
        # World BSP only: keep just the CSG brushes + LevelInfo, skip the light bake. Isolates the
        # geometry (vert/point/node/surf) divergence with a far cheaper build (no OBJ LOAD of the
        # light packages, no 700 point-actor adds, no LIGHT APPLY).
        cmd += ["--keep-classes", "Brush,LevelInfo", "--no-light"]
    print(f"[subset] editor-building N={n} world_only={world_only} ...", flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        sys.stderr.write(r.stdout[-3000:] + "\n" + r.stderr[-3000:] + "\n")
        raise SystemExit(f"editor subset build N={n} FAILED (rc={r.returncode})")
    print(f"[subset] N={n} -> {out}", flush=True)
    return out


def diff(full_trunk: Path, name: str, n: int, ci, *, world_only: bool, force: bool = False) -> dict:
    gold = build_editor_subset(full_trunk, name, n, ci, world_only=world_only, force=force)
    subset = _make_subset_trunk(full_trunk, name, n, ci)  # cheap; re-materialize for native read
    geo = pc.compare_geometry(subset, gold)
    geo_exact = geo.native == geo.golden
    if world_only:
        # Counts-only geometry probe. Content/lighting need native's assembled+lit .dx, whose surf
        # light-map refs would spuriously differ from an unlit golden — verified in full mode.
        return {"n": n, "geo": geo, "content": None, "lighting": None,
                "geo_exact": geo_exact, "content_exact": None, "parity": geo_exact}
    native_dx, _warn = pc.build_native_lit_dx(subset, subset.parent.parent)
    content = pc.compare_content(native_dx, gold)
    lighting = pc.compare_lighting(native_dx, gold)
    content_exact = content.nodes.exact and content.surfs.exact and content.leaves.exact
    return {"n": n, "geo": geo, "content": content, "lighting": lighting,
            "geo_exact": geo_exact, "content_exact": content_exact,
            "parity": geo_exact and content_exact}


def _print_row(d: dict) -> None:
    g = d["geo"]
    c = d["content"]
    L = d["lighting"]
    nv, gv = g.native, g.golden
    verdict = "PARITY" if d["parity"] else "DIVERGES"
    def mark(x, y):
        return f"{x}/{y}" + ("" if x == y else f"(d{x - y:+d})")
    line = (f"N={d['n']:>4}  "
            f"nodes {mark(nv.nodes, gv.nodes)}  surfs {mark(nv.surfs, gv.surfs)}  "
            f"leaves {mark(nv.leaves, gv.leaves)}  verts {mark(nv.verts, gv.verts)}  "
            f"pts {mark(nv.points, gv.points)}  vecs {mark(nv.vectors, gv.vectors)}")
    if c is not None:
        line += (f"  | content nodes={'=' if c.nodes.exact else 'X'} "
                 f"surfs={'=' if c.surfs.exact else 'X'} leaves={'=' if c.leaves.exact else 'X'}")
    if L is not None:
        line += (f"  | light {L.identical_records}/{L.total_records} rec "
                 f"{(100.0*L.shadow_bits_same/L.shadow_bits_total) if L.shadow_bits_total else 0:.1f}% bits")
    print(line + f"  {verdict}", flush=True)
    if c is None:
        return
    for arr in (c.nodes, c.surfs, c.leaves):
        if not arr.exact and arr.diffs:
            fd = arr.diffs[0]
            print(f"    first {arr.array_name} diff @ index {fd.index}: {fd.field} "
                  f"native={fd.native!r} golden={fd.golden!r}  "
                  f"(len native/golden {arr.native_len}/{arr.golden_len}, "
                  f"{arr.indices_differ} indices differ)", flush=True)
        elif not arr.exact:
            print(f"    {arr.array_name} length differs: native/golden "
                  f"{arr.native_len}/{arr.golden_len}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--dx", required=True, help="path to the shipped .dx level")
    ap.add_argument("--trunk", default=None, help="override: use this already-extracted trunk dir")
    ap.add_argument("--game", default="deusex")
    ap.add_argument("--timeout", type=float, default=3600.0)
    ap.add_argument("--world-only", action="store_true",
                    help="fast GEOMETRY-only probe: golden keeps Brush+LevelInfo, skips LIGHT APPLY; "
                         "compares geometry COUNTS only (the vert/point/node/surf divergence). Full "
                         "content+lighting parity is checked without this flag.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("count")
    b = sub.add_parser("build"); b.add_argument("n", type=int); b.add_argument("--force", action="store_true")
    d = sub.add_parser("diff"); d.add_argument("n", type=int); d.add_argument("--force", action="store_true")
    s = sub.add_parser("bisect"); s.add_argument("lo", type=int); s.add_argument("hi", type=int)
    args = ap.parse_args()

    dx_path = Path(args.dx).resolve()
    full_trunk, name = _resolve_trunk(dx_path, args.trunk, game=args.game)
    os.environ["UEDCLI_PROJECT"] = str(full_trunk.parent.parent)
    from spike_classindex import class_index
    ci = class_index()
    level, _ = trunk.read_level(full_trunk)
    brushes = _world_brush_order(level, ci)

    if args.cmd == "count":
        print(f"{name}: {len(level.actors)} actors, {len(brushes)} world-CSG brushes")
        return 0
    if args.cmd == "build":
        print(build_editor_subset(full_trunk, name, args.n, ci, world_only=args.world_only,
                                  force=args.force, timeout=args.timeout))
        return 0
    if args.cmd == "diff":
        _print_row(diff(full_trunk, name, args.n, ci, world_only=args.world_only, force=args.force))
        return 0
    if args.cmd == "bisect":
        lo, hi = args.lo, args.hi
        cache: dict[int, dict] = {}
        def diverges(n: int) -> bool:
            if n not in cache:
                cache[n] = diff(full_trunk, name, n, ci, world_only=args.world_only)
                _print_row(cache[n])
            return not cache[n]["parity"]
        # invariant: dv(lo) clean, dv(hi) diverges. find first N that diverges.
        if diverges(lo):
            print(f"\n*** N={lo} already diverges (lower LO) ***"); return 0
        if not diverges(hi):
            print(f"\n*** N={hi} still clean (raise HI) ***"); return 0
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if diverges(mid):
                hi = mid
            else:
                lo = mid
        print(f"\n*** FIRST DIVERGENCE at N={hi} (N={lo} clean) ***")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
