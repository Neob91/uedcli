"""Offline UCC batchexport of a package's textures to PCX — no live editor. The in-editor
`OBJ EXPORT` console verb is a dead end; UCC `batchexport` is the only working path
(`unrealed/commands.md`). Decode/PNG/hash/colors are host-side in `texture_catalog.py`; this module
only crosses the container boundary. Batchexport writes GROUP-PREFIXED PCX names (`Metal.Wall.pcx`,
spikes/2026-06-21-deusex-package-stubbing-roundtrip.md)."""
from __future__ import annotations

import os
import subprocess

from . import xfer
from .driver import to_z_path


def batchexport_textures(container: str, package: str, host_dir: str) -> list[str]:
    """UCC `batchexport <package> Texture pcx` into a container `/work` dir, then `cp_out` each PCX
    to `host_dir` (created host-side). `package` is the BARE name (no extension) — UCC resolves it
    to a file via the container `[Core.System] Paths` (asset-wiring Part C, 2026-07-14: the crafted
    ini `ephemeral_build_container` bind-mounts wires the config CONTENT dirs at `/resources/<n>` +
    baked `/opt/UED22`+`/stubs`); a package NOT on the container Paths simply produces no PCX. The
    batchexport call is `check=False`: a textureless or unresolvable package may exit non-zero, and
    "textures present" is read from "PCX files produced", not the exit code (Task 0 spike). So this
    NEVER crashes the caller's sweep. Returns the sorted HOST pcx paths (empty if none). `/work`
    MUST be a wine `Z:\\` path (`to_z_path`)."""
    os.makedirs(host_dir, exist_ok=True)
    work = xfer.work_dir("tex")
    subprocess.run(["docker", "exec", container, "mkdir", "-p", work],
                   check=True, capture_output=True, text=True)
    try:
        subprocess.run(
            ["docker", "exec", container, "wine", "/opt/UED22/UCC.exe", "batchexport",
             package, "Texture", "pcx", to_z_path(work)],
            check=False, capture_output=True, text=True)             # textureless -> non-zero is OK
        listing = subprocess.run(
            ["docker", "exec", container, "find", work, "-maxdepth", "1", "-name", "*.pcx"],
            check=True, capture_output=True, text=True).stdout
        host_pcxs = []
        for pcx in sorted(line for line in listing.splitlines() if line):
            host_pcx = os.path.join(host_dir, os.path.basename(pcx))
            xfer.cp_out(container, pcx, host_pcx)
            host_pcxs.append(host_pcx)
        return host_pcxs
    finally:
        xfer.remove(container, work)
