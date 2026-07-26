"""The single offline UCC `.dx`→Level reader. Materialize, qualify, and post-verify all go
through here so the UCC↔model seam (M2
canonicalization via canonical_actor_t3d downstream, order capture, normalize) is applied
identically everywhere. UCC's `batchexport` reads the bytes on disk — no live editor (design
D-B/D-C). The subprocess is integration-only; mocked in unit tests."""
from __future__ import annotations

import posixpath
import subprocess

from .driver import DriverError, to_z_path
from .model import Level, parse_t3d
from .normalize import level_order, normalize_level

# UCC batchexport writes <outdir>/MyLevel.T3D regardless of the .dx stem (Task 13 spike).
_UCC_OUT_BASENAME = "MyLevel.T3D"

# Hard bounds on this module's three container `docker exec`s (`dev/docs/rules/background-work.md`
# — "never leave one on a single open-ended wait"). Two are trivial shell calls; the middle one runs
# wine, so it gets its own generous budget.
#   SHELL  — `mkdir -p` and `cat` inside the container: sub-second, so a minute is already dockerd
#            not answering rather than slow work.
#   EXPORT — one `UCC.exe batchexport` of a whole level under wine. Minutes for a large retail map,
#            so the bound must be well clear of the real worst case; it exists to catch a wedged
#            wine/dockerd, not to police a slow export.
_SHELL_TIMEOUT = 60.0
_EXPORT_TIMEOUT = 900.0


def _exec(container: str, argv: list[str], what: str, timeout: float) -> str:
    """One BOUNDED `docker exec` in `container`; returns stdout. A call that outlives `timeout`
    raises `DriverError` naming what it was doing — a `RuntimeError` subclass the materialize
    guard already turns into a clean exit 2, never a traceback and never an endless wait. (The one
    production chain into here is `apply.run_materialize` → `apply._save_and_swap_verified` →
    `verify.verify_dx_matches`; `qualify.py` does not call this module.)"""
    try:
        return subprocess.run(["docker", "exec", container, *argv],
                              check=True, capture_output=True, text=True,
                              timeout=timeout).stdout
    except subprocess.TimeoutExpired:
        raise DriverError(f"{what} did not finish within {timeout:.0f}s in container {container} "
                          f"— wine or dockerd is wedged") from None


def export_dx_t3d(container: str, dx_path: str) -> str:
    """Raw offline UCC export of the on-disk .dx to T3D text. Integration-only.

    The work dir is removed in a `finally:` so a failed or timed-out export does not strand a
    `/work/ucc_export-<uuid>` tree in the container (its sibling `texture.batchexport_textures`
    already did this). It is created BEFORE the `try:` on purpose — if `mkdir` itself failed there
    is nothing to clean up."""
    from . import xfer
    outdir = xfer.work_dir("ucc_export")
    _exec(container, ["mkdir", "-p", outdir], f"mkdir {outdir}", _SHELL_TIMEOUT)
    try:
        _exec(container,
              ["wine", "/opt/UED22/UCC.exe", "batchexport", dx_path, "Level", "T3D",
               to_z_path(outdir)],
              f"UCC batchexport of {dx_path}", _EXPORT_TIMEOUT)
        return _exec(container, ["cat", posixpath.join(outdir, _UCC_OUT_BASENAME)],
                     f"reading the exported T3D from {outdir}", _SHELL_TIMEOUT)
    finally:
        xfer.remove(container, outdir)


def export_dx_level(container: str, dx_path: str) -> Level:
    """Parse the offline export → Level with full `order` captured (pre-normalize) + normalized.
    M2 self-ref canonicalization rides canonical_actor_t3d downstream (the hash/blob path)."""
    level = parse_t3d(export_dx_t3d(container, dx_path))
    level.order = level_order(level)
    normalize_level(level)
    return level
