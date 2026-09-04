#!/usr/bin/env python3
"""Incremental first-N-ACTORS full-structural parity (owner ruling 2026-09-04).

The lockstep-ladder tool: for a level and an actor count N, build the first N actors (trunk order,
ANY type) BOTH ways and full-package byte-diff them. Unlike `subset_parity.py` (brush prefix + count
comparison), this subsets by ACTOR prefix and compares the FULL package structure.

- native  = `parity_compare.build_native_lit_dx` on the N-actor subset (its own dummy builder).
- ued22   = `build_ued_import_built_golden.py --import-verb "MAP IMPORT"` (whole-file replace) on the
            same subset, with a sacrificial dummy builder prepended at Actors[1] (default on).
- compare = `structure_diff.py` (header + name/import/export tables set+order + per-export body bytes
            matched by identity) — the full structural view. The GUID is already excluded there; the
            other ruled per-save-random masks (save timestamps / TimeSeconds, StateFrame LatentAction,
            Camera viewport bodies) are named in the report so they can be judged, not silently passed.

Usage (venv python):
  actor_parity.py --dx <shipped.dx> subset N       # make the N-actor subset trunk
  actor_parity.py --dx <shipped.dx> native N        # build native's N-actor package
  actor_parity.py --dx <shipped.dx> ref N           # editor reference (MAP IMPORT + dummy), N actors
  actor_parity.py --dx <shipped.dx> diff N          # build both (if absent) + structure_diff

Scratch under `_scratch/actor-parity/<level>/`. The editor `ref` build is the slow half (BOUNDED bg).
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
REPORT_HARNESS = ROOT / "dev/docs/spikes/2026-08-31-native-parity-report/harness"
UNBUILT_HARNESS = ROOT / "dev/docs/spikes/2026-09-02-unbuilt-structure-parity/harness"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(REPORT_HARNESS))
sys.path.insert(0, str(HERE))

import parity_compare as pc     # noqa: E402
import parity_pipeline as pp    # noqa: E402
import parity_lib as pl         # noqa: E402
from uedcli import trunk        # noqa: E402

PYTHON = ROOT / ".venv/bin/python"
REF_BUILDER = HERE / "build_ued_import_built_golden.py"
STRUCTURE_DIFF = UNBUILT_HARNESS / "structure_diff.py"
ROOT_SCRATCH = ROOT / "_scratch/actor-parity"


def _resolve_trunk(dx_path: Path, game: str) -> tuple[Path, str]:
    name = pp.level_name(dx_path)
    h = pl.content_hash(dx_path)
    trunk_dir = pp.build_root(h) / "maps" / name
    if not pp.trunk_is_complete(trunk_dir):
        pp.extract_trunk(dx_path, trunk_dir, game=game,
                         log_path=pl.cache_layout(pl.CACHE_ROOT_DEFAULT, h).root / "extract.log",
                         timeout=1800.0)
    return trunk_dir, name


def make_subset(full_trunk: Path, name: str, n: int) -> Path:
    """`<scratch>/<level>/N<n>/maps/<level>/` holding the first N actors in trunk order (any type)."""
    level, _ = trunk.read_level(full_trunk)
    keep = level.order[:n]
    proj = ROOT_SCRATCH / name / f"N{n}"
    dst = proj / "maps" / name
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "actors").mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\nmaps = "maps"\n')
    for an in keep:
        shutil.copytree(full_trunk / "actors" / an, dst / "actors" / an)
    return dst


def native_path(name: str, n: int) -> Path:
    return ROOT_SCRATCH / name / f"native_N{n}.dx"


def ref_path(name: str, n: int) -> Path:
    return ROOT_SCRATCH / name / f"ref_N{n}.dx"


def build_native(subset: Path, name: str, n: int) -> Path:
    dx, warn = pc.build_native_lit_dx(subset, subset.parent.parent)
    out = native_path(name, n)
    out.write_bytes(dx)
    if warn:
        print(f"[native N={n}] warnings: {warn[:3]}", file=sys.stderr)
    return out


def build_ref(subset: Path, name: str, n: int, *, timeout: float) -> Path:
    out = ref_path(name, n)
    cmd = [str(PYTHON), str(REF_BUILDER), "--trunk", str(subset), "--out", str(out),
           "--import-verb", "MAP IMPORT", "--overwrite", "--timeout", str(timeout)]
    print(f"[ref N={n}] editor-building (MAP IMPORT + dummy) ...", flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        sys.stderr.write(r.stdout[-3000:] + "\n" + r.stderr[-3000:] + "\n")
        raise SystemExit(f"ref build N={n} FAILED (rc={r.returncode})")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--dx", required=True)
    ap.add_argument("--game", default="deusex")
    ap.add_argument("--timeout", type=float, default=3600.0)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("subset", "native", "ref", "diff"):
        s = sub.add_parser(c); s.add_argument("n", type=int)
    args = ap.parse_args()

    dx_path = Path(args.dx).resolve()
    full_trunk, name = _resolve_trunk(dx_path, args.game)
    total = len(trunk.read_level(full_trunk)[0].order)
    if args.n < 1 or args.n > total:
        raise SystemExit(f"N must be 1..{total} (level {name} has {total} actors)")

    if args.cmd == "subset":
        print(make_subset(full_trunk, name, args.n)); return 0
    subset = make_subset(full_trunk, name, args.n)
    if args.cmd == "native":
        print(build_native(subset, name, args.n)); return 0
    if args.cmd == "ref":
        print(build_ref(subset, name, args.n, timeout=args.timeout)); return 0
    if args.cmd == "diff":
        nat = build_native(subset, name, args.n)
        ref = ref_path(name, args.n)
        if not ref.exists():
            ref = build_ref(subset, name, args.n, timeout=args.timeout)
        print(f"\n=== structure_diff  native={nat.name}  ref={ref.name}  (level {name}, N={args.n}) ===",
              flush=True)
        subprocess.run([str(PYTHON), str(STRUCTURE_DIFF), str(nat), str(ref), "--bodies", "8"])
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
