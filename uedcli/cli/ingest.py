"""Cross-family T3D input and author-time validation.

The seams here read T3D text for the verbs that ingest it (`--from-t3d`, `--set`, `level import`) and
run the shared author-time class/texture gate every ingest path funnels through. They are used by
more than one command family (actor, stash, prefab, level, the generators) — family-specific ingest
(stash capture, actor's own add flow) stays with its family. Callers use module-qualified lookup
(`ingest.read_t3d_input(...)`, `ingest.validate_ingest_actors(...)`) so an owner-module patch reaches
them. See spec "Cross-family orchestrators". Imports only earlier owners (`resources`, `errors`) and
lower services, never a command family (spec "Dependency rules" rules 4-5).
"""
from __future__ import annotations

import sys

from .. import classindex
from ..classindex import ClassRefError
from . import resources
from .errors import CommandError


def read_t3d_input(path_or_dash: str) -> str:
    """Read T3D text from a file path (or `-` for stdin). An unreadable/missing path is a clean
    error (exit 2) naming the path, never a `FileNotFoundError` traceback."""
    if path_or_dash == "-":
        return sys.stdin.read()
    try:
        with open(path_or_dash) as fh:
            return fh.read()
    except OSError as e:
        raise CommandError(f"cannot read T3D file {path_or_dash!r}: {e.strerror or e}")


def read_t3d_files(paths: list[str]) -> str:
    """The unified `--from-t3d <FILE…|->` reader: concatenate T3D text from one-or-more files (or
    `-` for a stdin snippet), in order. `-` is the SOLE value if present — no mixing stdin with
    files (the `-` convention). Shared by `actor preview` (T3D mode) and `stash capture`."""
    if "-" in paths and paths != ["-"]:
        raise CommandError("`-` reads a T3D snippet from stdin and cannot be combined with files")
    return "\n".join(read_t3d_input(p) for p in paths)


def validate_ingest_actors(actors, args) -> None:
    """The DRY author-time ingest gate: qualify bare class names → FQCN and existence-validate
    qualified ones (in place), then validate every brush poly's texture ref EXISTS on the package
    path. Shared by every T3D ingest/emit seam (actor add, stash capture/apply/promote, prefab
    apply, the generators). Raises `CommandError` (exit 2) on an unknown class/texture or an empty
    package path — never a traceback. Call AFTER builder-brush filtering (qualifying `Brush`→
    `Engine.Brush` before the filter would let the transient builder brush escape it)."""
    if not actors:
        return
    project, user_config, files = resources.package_path_or_exit(args)
    try:
        classindex.ClassIndex.from_project(project, user_config).qualify_and_validate(actors)
    except ClassRefError as e:
        raise CommandError(str(e))
    from .. import utexture
    resolver = utexture.TextureResolver(files)
    for a in actors:
        if a.brush is None:
            continue
        for p in a.brush.polys:
            if p.texture is not None and not resolver.exists(p.texture):
                raise CommandError(f"texture not found: {p.texture} — no Texture of that name on "
                                     f"the package path (author-time validation)")
