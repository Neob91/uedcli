"""Run the two advisory BSP health checks after a SUCCESSFUL materialize build+save.

Contract (owner design 2026-08-03): these are advisory health on an already-good build. They
NEVER change materialize's result — a check that raises, or a log/parse that fails, is caught here
and reported as a one-line "skipped" note; materialize still succeeds (rc 0, map written). Findings
go to stderr via the returned lines; the caller prints them and keeps exit 0.
"""
from __future__ import annotations

from . import builtmodel
from .editorlog import flush_and_parse_since
from ..doctor import Finding


def _finding_line(f: Finding) -> str:
    loc = f" @{f.coord}" if f.coord else ""
    return f"  [{f.severity.value.upper():5}] {f.category}{loc}: {f.message}"


def _build_output_check(driver, log_offset: int) -> list[str]:
    """The editor's `MAP REBUILD` warning counts (dropped faces, unlinked T-points, sliver nodes)."""
    try:
        log = flush_and_parse_since(driver, log_offset)
        found = log.findings()
        if not found:
            return []
        return ["  build-output warnings:", *[f"    {line}" for line in found]]
    except Exception as e:                       # never fail materialize on the health check
        return [f"  build-output check skipped ({type(e).__name__}: {e})"]


def _built_model_check(dx_path: str) -> list[str]:
    """Located defects in the saved built `.dx`: invisible walls (near-zero-area BSP nodes)."""
    try:
        from pathlib import Path
        model = builtmodel.load_model_from_dx(Path(dx_path).read_bytes())
        findings = builtmodel.analyze_built(model)
        if not findings:
            return []
        return ["  built-model defects:", *[_finding_line(f) for f in findings]]
    except Exception as e:
        return [f"  built-model check skipped ({type(e).__name__}: {e})"]


def run_bsp_checks(driver, *, log_offset: int | None, dx_path: str) -> list[str]:
    """Both checks, each independently guarded. Returns stderr lines (empty = both clean and ran
    without incident). `log_offset` None ⇒ the build-output check is skipped (offset capture failed)."""
    lines: list[str] = []
    if log_offset is None:
        lines.append("  build-output check skipped (could not read the editor log offset)")
    else:
        lines += _build_output_check(driver, log_offset)
    lines += _built_model_check(dx_path)
    if not lines:
        return []
    return ["materialize: BSP health check (advisory; build succeeded):", *lines]
