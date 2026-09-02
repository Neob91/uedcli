#!/usr/bin/env python3
"""Corpus-wide native-materialize parity sweep -- runs `parity_report.py` (via `sweep_worker_shim.py`)
across the 18-level OG Deus Ex breadth corpus (`sweep_lib.CORPUS`) with LOW, bounded concurrency and a
real hang-detector, and writes one structured JSON result file (`sweep_lib.SweepRun`) that a separate
step (`sweep_to_xlsx.py`) loads into the tracking workbook -- the sweep logic here never touches
`openpyxl`.

Exists because two independent agents this session swept this same corpus from scratch and both hit
`TimeoutError: editor not idle after 1800s [obj-load]` at 87-96% CPU running 3 concurrent Wine/docker
editor instances -- a driver-level CONCURRENCY problem, not a `parity_report.py` bug -- and because
trunk extraction (offline UCC batchexport, no live editor, but still slow) was being redone from
scratch on every sweep even for levels a PRIOR run had already extracted: `parity_pipeline.build_root()`
deliberately keys the trunk cache under the CALLING worktree's own `_scratch/` (a bind-mount
constraint, see that function's docstring), which a fresh disposable worktree never shares with
whatever worktree an earlier sweep happened to run from. `sweep_worker_shim.py` fixes the second half
by redirecting to `sweep_lib.shared_trunk_cache_root()`, a fixed location shared by every worktree on
this box; the self-built-golden half (`/tmp/uedcli-parity-cache/`) was already correctly shared and
needed no fix -- `parity_report.py` calls it unmodified.

Usage:
  .venv/bin/python sweep_corpus.py [--concurrency N] [--levels L1.dx,L2.dx,...] [--out FILE]
                                    [--rebuild-timeout SECONDS] [--hang-timeout SECONDS]
                                    [--work-dir DIR] [--game deusex]

Default concurrency is 1 -- the contention that caused the 1800s timeouts was observed even at 3-way
concurrency (each editor instance is a full Wine/docker VM-ish process; 3 of them saturated the host
at 87-96% CPU). Raise `--concurrency` deliberately, not as a default, once host headroom is confirmed.
"""
from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sweep_lib as sl  # noqa: E402

SHIM = HERE / "sweep_worker_shim.py"
DEFAULT_EXTRACT_TIMEOUT = 1800.0  # mirrors parity_pipeline.ensure_golden's own hardcoded bound
DEFAULT_REBUILD_TIMEOUT = 3600.0  # mirrors parity_report.py's own --rebuild-timeout default


def default_hang_timeout(rebuild_timeout: float) -> float:
    """The outer per-level hang-detector bound: extraction's own hardcoded 1800s ceiling, plus the
    golden rebuild's own timeout, plus a margin for offline comparison work and process startup. This
    is a SEPARATE detection layer, not a retry on top of the pipeline's own bounds -- in the normal
    case `parity_pipeline._run`'s `subprocess.run(timeout=...)` already raises a clean `PipelineError`
    well inside this bound, and the shim exits cleanly; this only fires if something inside the
    pipeline hangs WITHOUT raising (an unbounded `docker exec` -- `architecture.md`'s "Most `Driver`
    methods have no uedcli-command caller" section names several that stay unbounded on purpose)."""
    return DEFAULT_EXTRACT_TIMEOUT + rebuild_timeout + 900.0


def build_command(dx_path: Path, *, cache_root: Path, rebuild_timeout: float, game: str) -> list[str]:
    return [sys.executable, str(SHIM), str(dx_path), "--json", "--game", game,
            "--cache-root", str(cache_root), "--rebuild-timeout", str(rebuild_timeout)]


def _tail(path: Path, n: int = 40) -> str:
    try:
        return "\n".join(path.read_text(errors="replace").splitlines()[-n:])
    except OSError:
        return ""


def _collect_result(*, level: str, dx_path: str, rc: int, elapsed: float, out_json: Path,
                    err_log: Path) -> sl.LevelResult:
    if rc in (0, 1):
        try:
            report = json.loads(out_json.read_text())
        except (OSError, json.JSONDecodeError) as e:
            return sl.LevelResult(level=level, dx_path=dx_path, status="ERROR", elapsed_s=elapsed,
                                  notes=f"exit {rc} but could not parse {out_json}: {e}")
        return sl.level_result_from_report_json(level=level, dx_path=dx_path, elapsed_s=elapsed,
                                                 report=report)
    if rc == 2:
        return sl.LevelResult(level=level, dx_path=dx_path, status="PIPELINE_ERROR", elapsed_s=elapsed,
                              notes=_tail(err_log))
    return sl.LevelResult(level=level, dx_path=dx_path, status="ERROR", elapsed_s=elapsed,
                          notes=f"exit {rc} -- see {err_log}\n{_tail(err_log)}")


def run_sweep(levels: list[str], *, concurrency: int, cache_root: Path, rebuild_timeout: float,
             hang_timeout: float, game: str, work_dir: Path,
             command_builder=build_command, poll_interval: float = 2.0,
             popen=subprocess.Popen) -> list[sl.LevelResult]:
    """The scheduler: never more than `concurrency` levels build at once, and any single level whose
    subprocess runs past `hang_timeout` gets `kill()`ed and recorded TIMED_OUT while the rest of the
    sweep continues -- a single wedged editor never blocks the whole corpus.

    `command_builder`/`popen` are injectable so this scheduling logic (concurrency bound + hang
    detection) can be tested with a fake, instant "editor" (`test_sweep_corpus.py`) instead of a real
    one -- the same reason `parity_pipeline`'s own docker-touching calls are exercised only through
    `parity_report.py` end to end, never unit tested directly."""
    work_dir.mkdir(parents=True, exist_ok=True)
    results: list[sl.LevelResult] = []
    pending = list(levels)
    jobs: list[dict] = []

    def _launch(dx_name: str) -> None:
        dx_path = sl.maps_dir(HERE) / dx_name
        if not dx_path.is_file():
            results.append(sl.LevelResult(level=dx_name, dx_path=str(dx_path), status="ERROR",
                                          notes=f"map file not found: {dx_path}"))
            return
        out_json = work_dir / f"{dx_name}.stdout.json"
        err_log = work_dir / f"{dx_name}.stderr.log"
        cmd = command_builder(dx_path, cache_root=cache_root, rebuild_timeout=rebuild_timeout,
                              game=game)
        out_fh = out_json.open("w")
        err_fh = err_log.open("w")
        proc = popen(cmd, stdout=out_fh, stderr=err_fh)
        jobs.append({"level": dx_name, "dx_path": str(dx_path), "proc": proc, "out_json": out_json,
                    "err_log": err_log, "out_fh": out_fh, "err_fh": err_fh,
                    "started": time.monotonic()})

    while pending or jobs:
        while pending and len(jobs) < concurrency:
            _launch(pending.pop(0))
        if not jobs:
            continue
        time.sleep(poll_interval)
        for job in list(jobs):
            rc = job["proc"].poll()
            elapsed = time.monotonic() - job["started"]
            timed_out = rc is None and elapsed > hang_timeout
            if rc is None and not timed_out:
                continue
            if timed_out:
                job["proc"].kill()
                rc = job["proc"].wait()
            job["out_fh"].close()
            job["err_fh"].close()
            if timed_out:
                results.append(sl.LevelResult(
                    level=job["level"], dx_path=job["dx_path"], status="TIMED_OUT", elapsed_s=elapsed,
                    notes=f"exceeded hang-timeout {hang_timeout:.0f}s, killed -- see {job['err_log']}"))
            else:
                results.append(_collect_result(level=job["level"], dx_path=job["dx_path"], rc=rc,
                                               elapsed=elapsed, out_json=job["out_json"],
                                               err_log=job["err_log"]))
            jobs.remove(job)
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--concurrency", type=int, default=1,
                    help="max concurrent editor-driving builds (default 1 -- see module docstring "
                         "for why the default is this conservative)")
    ap.add_argument("--levels", default=None,
                    help="comma-separated subset of sweep_lib.CORPUS filenames to run (default: all "
                         "18); unknown names are a clean error naming the offender")
    ap.add_argument("--rebuild-timeout", type=float, default=DEFAULT_REBUILD_TIMEOUT,
                    help=f"per-level MAP REBUILD+LIGHT APPLY timeout, seconds (default "
                         f"{DEFAULT_REBUILD_TIMEOUT:.0f})")
    ap.add_argument("--hang-timeout", type=float, default=None,
                    help="outer per-level hang-detector bound, seconds (default: derived from "
                         "--rebuild-timeout, see default_hang_timeout())")
    ap.add_argument("--game", default="deusex", help="substrate game key (default: deusex)")
    ap.add_argument("--cache-root", default=None,
                    help="self-built-golden cache root (default: parity_lib.CACHE_ROOT_DEFAULT, "
                         "/tmp/uedcli-parity-cache -- already shared across worktrees)")
    ap.add_argument("--work-dir", default=None,
                    help="per-level stdout/stderr capture dir (default: a fresh timestamped dir "
                         "under _scratch/parity-sweep-runs/)")
    ap.add_argument("--out", default=None,
                    help="sweep JSON output path (default: <work-dir>/sweep.json)")
    args = ap.parse_args(argv)

    if args.concurrency < 1:
        print(f"sweep_corpus: --concurrency must be >= 1, got {args.concurrency}", file=sys.stderr)
        return 2

    if args.levels:
        requested = [x.strip() for x in args.levels.split(",") if x.strip()]
        unknown = [x for x in requested if x not in sl.CORPUS and x not in sl.SKIPPED]
        if unknown:
            print(f"sweep_corpus: unknown level(s), not in the corpus: {', '.join(unknown)}",
                  file=sys.stderr)
            return 2
    else:
        requested = list(sl.CORPUS) + list(sl.SKIPPED)

    hang_timeout = args.hang_timeout if args.hang_timeout is not None else default_hang_timeout(
        args.rebuild_timeout)
    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    stamp = started_at.replace(":", "").replace("+00:00", "Z")
    work_dir = Path(args.work_dir) if args.work_dir else sl.repo_root(HERE) / "_scratch" / \
        "parity-sweep-runs" / stamp
    cache_root = Path(args.cache_root) if args.cache_root else Path("/tmp/uedcli-parity-cache")
    out_path = Path(args.out) if args.out else work_dir / "sweep.json"

    to_run = [lv for lv in requested if lv in sl.CORPUS]
    skipped = [lv for lv in requested if lv in sl.SKIPPED]

    results: list[sl.LevelResult] = [
        sl.LevelResult(level=lv, dx_path=str(sl.maps_dir(HERE) / lv), status="SKIPPED",
                       notes=sl.SKIPPED[lv])
        for lv in skipped
    ]
    print(f"[sweep] {len(to_run)} level(s) to run, {len(skipped)} skipped, concurrency="
         f"{args.concurrency}, hang_timeout={hang_timeout:.0f}s, work_dir={work_dir}", file=sys.stderr)

    results += run_sweep(to_run, concurrency=args.concurrency, cache_root=cache_root,
                        rebuild_timeout=args.rebuild_timeout, hang_timeout=hang_timeout,
                        game=args.game, work_dir=work_dir)

    order = {lv: i for i, lv in enumerate(requested)}
    results.sort(key=lambda r: order.get(r.level, 999))

    run = sl.SweepRun(started_at=started_at, concurrency=args.concurrency,
                      rebuild_timeout=args.rebuild_timeout, hang_timeout=hang_timeout,
                      results=tuple(results))
    sl.write_sweep_json(run, out_path)

    ok = sum(1 for r in results if r.status == "OK")
    full = sum(1 for r in results if r.full_parity)
    print(f"[sweep] done: {ok}/{len(to_run)} measured, {full} at FULL PARITY, "
         f"{sum(1 for r in results if r.status == 'TIMED_OUT')} timed out -- wrote {out_path}",
         file=sys.stderr)
    for r in results:
        print(f"  {r.level:35} {r.status:15} {r.notes[:80]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
