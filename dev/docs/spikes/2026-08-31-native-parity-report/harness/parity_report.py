#!/usr/bin/env python3
"""Native-materialize parity report -- the single canonical entry point for "is this OG Deus Ex
level at full geometry+lighting byte parity with a self-built UED22 golden yet?"

Input: path to an ORIGINAL (unmodified, shipped) Deus Ex `.dx` level file. Content-hashes it and
caches the expensive self-built UED22 golden under `/tmp/uedcli-parity-cache/<hash>/`, so a repeat
run against the same input skips the whole Wine/Docker MAP REBUILD+LIGHT APPLY round-trip.

The golden is ALWAYS self-built by the real editor (`MAP NEW` -> `EDIT PASTE` -> `MAP REBUILD` ->
`LIGHT APPLY` -> `MAP SAVE`) from a T3D trunk extracted from the input `.dx` -- NEVER produced by
`MAP LOAD`-ing the shipped file directly (the shipped originals are stale/differently-dated builds,
not a valid comparison target -- `dev/docs/native-materialize-findings.md`, "Golden .dx
provenance -- CONFIRMED, closed").

Compares geometry (nodes/surfs/leaves/verts/points/vectors -- exact counts, native
`build_geometry_bspcsg` vs the golden), CONTENT (nodes/surfs/leaves -- index-for-index field comparison,
`native[i]` vs `golden[i]` for every `i`; catches a genuinely different tree that happens to share
every count with the golden, which the count-only check above cannot), and lighting (`LightMap`
byte-identical record count/percentage + grid+run-matched shadow-bit agreement). Prints a top-line
`FULL PARITY: YES/NO` verdict -- YES only if EVERY geometry count, EVERY node/surf field at every
index, and EVERY `LightMap` record is byte-identical (stricter than `breadth_gate.py`'s
node/surf/leaf-only "EXACT" label, which checks neither a verts/points/vectors delta nor content).

Usage:
  .venv/bin/python parity_report.py <path/to/level.dx> [--json] [--game deusex]
                                    [--cache-root DIR] [--rebuild-timeout SECONDS]

Only levels whose trunk-extraction + self-build pipeline actually completes are supported -- an
untested level surfaces a clear, named pipeline error (never a raw traceback) rather than a silent
partial result. So far UNATCO and Wanchai are proven end to end (see `spike.md` alongside this
script); anything else is a live bet on the same generic mechanism.

Exit codes: 0 = FULL PARITY: YES, 1 = report completed and says NO, 2 = the tool itself failed
(bad input, pipeline error, comparison error) -- named on stderr, never a raw traceback.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import parity_lib as pl        # noqa: E402
import parity_pipeline as pp   # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dx_path", help="path to the ORIGINAL, unmodified, shipped .dx level file")
    ap.add_argument("--json", action="store_true",
                    help="machine-readable JSON report on stdout instead of the human-readable text report")
    ap.add_argument("--game", default="deusex",
                    help="substrate game key in ~/.uedcli/config.toml (default: deusex)")
    ap.add_argument("--cache-root", default=str(pl.CACHE_ROOT_DEFAULT),
                    help=f"cache directory root (default: {pl.CACHE_ROOT_DEFAULT})")
    ap.add_argument("--rebuild-timeout", type=float, default=3600.0,
                    help="max seconds to wait for the self-built golden's MAP REBUILD+LIGHT APPLY "
                         "(default 3600)")
    args = ap.parse_args(argv)

    dx_path = Path(args.dx_path).resolve()
    if not dx_path.is_file():
        print(f"parity report: not a file: {dx_path}", file=sys.stderr)
        return 2

    try:
        layout, level_name, trunk_dir, cache_hit = pp.ensure_golden(
            dx_path, cache_root=Path(args.cache_root), game=args.game,
            rebuild_timeout=args.rebuild_timeout)
    except pp.PipelineError as e:
        print(f"parity report: could not build a self-built golden for {dx_path}:\n{e}",
              file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 -- never let a raw traceback reach the user (e.g. a
        # malformed ~/.uedcli/config.toml raises uedcli.config.ConfigError, not PipelineError)
        print(f"parity report: could not build a self-built golden for {dx_path}: {e}",
              file=sys.stderr)
        return 2

    if cache_hit:
        print(f"[parity] cache hit: {layout.root} (skipping trunk extraction + golden build)",
              file=sys.stderr)
    else:
        print(f"[parity] built fresh golden: {layout.root}", file=sys.stderr)
    meta = pl.read_meta(layout) or {}

    import parity_compare as pc
    try:
        geometry = pc.compare_geometry(trunk_dir, layout.golden)
        native_dx, build_warnings = pc.build_native_lit_dx(trunk_dir, trunk_dir.parent.parent)
        content = pc.compare_content(native_dx, layout.golden)
        lighting = pc.compare_lighting(native_dx, layout.golden)
    except Exception as e:  # noqa: BLE001 -- never let a raw traceback reach the user
        print(f"parity report: comparison failed for {dx_path}: {e}", file=sys.stderr)
        return 2

    report = pl.ParityReport(source_dx=str(dx_path), content_hash=pl.content_hash(dx_path),
                             level_name=level_name, cache_hit=cache_hit,
                             built_at=meta.get("built_at"), geometry=geometry, content=content,
                             lighting=lighting, warnings=tuple(build_warnings))
    print(pl.format_json(report) if args.json else pl.format_text(report))
    return 0 if report.full_parity else 1


if __name__ == "__main__":
    raise SystemExit(main())
