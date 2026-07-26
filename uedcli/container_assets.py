"""Turn composed config **directories** into the docker mounts + `[Core.System] Paths` lines an
editor / game / build container needs. Host-fs reads only (it scans dir filenames for the present
extensions); NO docker/subprocess — those live in `editor.py`/`preview_game.py`.

The model (ONE uniform scheme — decisions.md 2026-07-14):
- The CALLER passes the **whole composed config dir set** (there is no code-vs-content dir split —
  `.u`/`.utx`/`.uax`/`.umx`/`.dx` are all the same Unreal package format, differing only by
  convention). Every dir is bind-mounted read-only at `/resources/<n>` via `resource_mounts`.
  Editor, preview game, `texture sync`, and stub-build all use this SAME mount scheme.
- The container search path (for the ONE `Paths` generator) is `[/stubs, /opt/UED22, /resources/r000,
  …]` — the v69 stub cache FIRST, then the baked UED22 substrate, then the mounts. Stubs-first means a
  v69 stub always shadows a same-named v68 `.u` a composed dir puts on Paths, so the editor never
  loads a v68 package it has stubbed. Each mount yields one line per package extension actually
  present in it (`Paths=<dir>/*.<ext>` — a bare `<dir>/*` with no extension STALLS the editor at boot,
  live-verified 2026-07-14). A v68 `.u` SOURCE for stub-build is read by explicit `/resources/<n>`
  path (`batchexport`/`umodel`), never via Paths.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# The five UnrealEngine-1 package extensions. The `CODE`/`CONTENT` grouping here is ONLY for ordering
# the `Paths` emit (code `.u` first) — NOT a dir-role split; a `.u` can hold textures and vice versa.
CODE_EXTS = (".u",)
CONTENT_EXTS = (".utx", ".dx", ".uax", ".umx")

# Fixed container roots that are NOT config-driven (baked into the image / host-cached), in Paths
# precedence order: game-class stubs win, then the UED22 substrate, then mounted content.
STUBS_CONTAINER_DIR = "/stubs"
UED22_CONTAINER_DIR = "/opt/UED22"


@dataclass(frozen=True)
class Mount:
    """One read-only bind mount: a host directory exposed to the container at `container_dir`."""
    host_dir: str
    container_dir: str


def resource_mounts(dirs: list[str]) -> list[Mount]:
    """One read-only bind mount per composed config dir at `/resources/r<NNN>` — a positional index
    over the composed order: deterministic, collision-free (distinct dirs never share an `<n>`),
    readable. `dirs` is the whole composed set (content AND code — one uniform scheme). The caller
    must dedup dirs first (a dir appearing twice would get two mounts)."""
    return [Mount(host_dir=d, container_dir=f"/resources/r{i:03d}")
            for i, d in enumerate(dirs)]


def container_search_dirs(mounts: list[Mount]) -> list[str]:
    """The ordered container-dir list the `Paths` generator emits over: stubs first, then the baked
    UED22 substrate, then the content mounts (decisions.md 2026-07-14, stubs-first)."""
    return [STUBS_CONTAINER_DIR, UED22_CONTAINER_DIR, *(m.container_dir for m in mounts)]


# The package extensions a mount may contribute to `Paths`, in canonical emit order: code `.u`
# first, then the content exts. A dir is scanned host-side and emits a line only for an ext it holds.
_PATHS_EXTS = (*CODE_EXTS, *CONTENT_EXTS)


def _present_exts(host_dir: str) -> list[str]:
    """The `_PATHS_EXTS` (in canonical order) that actually occur in `host_dir` (flat,
    case-insensitive). Keeps the emitted `Paths` lean — no line for an extension the dir lacks."""
    try:
        found = {os.path.splitext(n)[1].lower() for n in os.listdir(host_dir)}
    except OSError:
        found = set()
    return [e for e in _PATHS_EXTS if e in found]


def paths_ini_lines(mounts: list[Mount]) -> list[str]:
    """The complete `[Core.System] Paths` set — one line per (dir × extension). This REPLACES the
    baked Paths wholesale (UED22's own line is REGENERATED here, not preserved).

    UE1's `Paths` format is `<dir>/*.<ext>` where `*` is the package NAME and the extension is
    REQUIRED — a bare `<dir>/*` (no extension) matches only extension-less files and finds no
    packages, and the editor STALLS at boot (live-verified 2026-07-14, boot_diag: `Paths=/opt/UED22/*`
    hung the editor). So every line carries an extension. The code roots (`/stubs`, `/opt/UED22`) are
    v69 CODE → `*.u` and come FIRST, so a v69 package always wins over a same-named later mount. Each
    mount then emits a line per package ext actually present in it (`_present_exts`, scanned
    host-side) — content exts for a content-bearing dir, `*.u` for a dir holding v68 code. ALL
    containers now mount the whole composed set (one uniform scheme), so a v68 code dir's `*.u` DOES
    reach Paths here — but always AFTER `/stubs`+`/opt/UED22`, so a v69 stub always shadows it and
    neither `UCC make` nor the editor binds the v68 over its stub. The v68 SOURCE for stub-build is
    read by `batchexport`/`umodel` via its explicit `/resources/<n>` path, not via Paths. (An UNstubbed
    v68 code package a level references is refused by `packages.unloadable_v68_packages` before any
    `OBJ LOAD`, not loaded — so the shadow gap can't reach the editor.)"""
    lines = [f"Paths={STUBS_CONTAINER_DIR}/*.u", f"Paths={UED22_CONTAINER_DIR}/*.u"]
    for m in mounts:
        for ext in _present_exts(m.host_dir):
            lines.append(f"Paths={m.container_dir}/*{ext}")
    return lines


def docker_mount_args(mounts: list[Mount]) -> list[str]:
    """Flattened `docker run/compose -v` args for the content mounts (read-only). The `/stubs` and
    `/opt/UED22` roots are provided by the image/host-cache mount, not here."""
    args: list[str] = []
    for m in mounts:
        args += ["-v", f"{m.host_dir}:{m.container_dir}:ro"]
    return args


def remap(host_path: str, mounts: list[Mount]) -> str | None:
    """Translate a HOST file path to the path the container sees, using the SAME `mounts` list the
    caller mounted (never recomputed — decisions.md 2026-07-14). Returns the `/resources/<n>/…` path
    if `host_path` is under a mount's host dir, else `None` (the caller decides — e.g. a stub-cache or
    UED22 file is remapped by its own fixed root elsewhere). Longest host-dir match wins so a nested
    mount can't be shadowed by its parent."""
    hp = os.path.abspath(host_path)
    best: tuple[int, str] | None = None
    for m in mounts:
        root = os.path.abspath(m.host_dir)
        if hp == root or hp.startswith(root + os.sep):
            rel = os.path.relpath(hp, root)
            cand = m.container_dir if rel == "." else f"{m.container_dir}/{rel.replace(os.sep, '/')}"
            if best is None or len(root) > best[0]:
                best = (len(root), cand)
    return best[1] if best else None
