"""The single offline UCC `.dx`→Level reader. Materialize, qualify, and post-verify all go
through here so the UCC↔model seam (M2
canonicalization via canonical_actor_t3d downstream, order capture, normalize) is applied
identically everywhere. UCC's `batchexport` reads the bytes on disk — no live editor (design
D-B/D-C). The subprocess is integration-only; mocked in unit tests."""
from __future__ import annotations

import posixpath
import subprocess

from .driver import to_z_path
from .model import Level, parse_t3d
from .normalize import level_order, normalize_level

# UCC batchexport writes <outdir>/MyLevel.T3D regardless of the .dx stem (Task 13 spike).
_UCC_OUT_BASENAME = "MyLevel.T3D"


def export_dx_t3d(container: str, dx_path: str) -> str:
    """Raw offline UCC export of the on-disk .dx to T3D text. Integration-only."""
    from . import xfer
    outdir = xfer.work_dir("ucc_export")
    subprocess.run(["docker", "exec", container, "mkdir", "-p", outdir],
                   check=True, capture_output=True, text=True)
    subprocess.run(
        ["docker", "exec", container, "wine", "/opt/UED22/UCC.exe", "batchexport",
         dx_path, "Level", "T3D", to_z_path(outdir)],
        check=True, capture_output=True, text=True)
    txt = subprocess.run(
        ["docker", "exec", container, "cat", posixpath.join(outdir, _UCC_OUT_BASENAME)],
        check=True, capture_output=True, text=True).stdout
    xfer.remove(container, outdir)
    return txt


def export_dx_level(container: str, dx_path: str) -> Level:
    """Parse the offline export → Level with full `order` captured (pre-normalize) + normalized.
    M2 self-ref canonicalization rides canonical_actor_t3d downstream (the hash/blob path)."""
    level = parse_t3d(export_dx_t3d(container, dx_path))
    level.order = level_order(level)
    normalize_level(level)
    return level
