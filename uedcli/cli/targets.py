"""Cross-family name/stdin target resolution.

`resolve_target_names` is the CLI's one reader for the newline-list stdin convention (`find → mutate
-`): the name-source seam shared by every name-taking verb across families (actor delete/rotate/prop/
show, brush poly targets, docs show). Family-specific selector parsing (polygon/surface selectors)
stays in `surface.py`. Callers use module-qualified lookup (`targets.resolve_target_names(...)`) so an
owner-module patch reaches them. Imports only `errors` and lower services, never a command family
(spec "Dependency rules" rules 4-5).
"""
from __future__ import annotations

import sys

from .errors import CommandError


def resolve_target_names(tokens: list[str]) -> list[str]:
    """The name-source seam for name-taking verbs (`actor delete/rotate/prop/show`): return the RAW
    list of actor names to operate on (canonical resolution + dedup are the CALLER's — spec
    2026-07-18 §8).

    The single token ``-`` reads a newline-separated name list from stdin (exactly `actor find`'s
    output): blank lines dropped, each entry stripped. Empty stdin → ``[]`` (the caller treats that
    as a no-op, exit 0 — a filter that matched nothing is not an error). ``-`` is the SOLE names
    source: mixing it with actual names on the command line raises `CommandError` (exit 2).

    This is the CLI's ONE reader for the newline-list stdin convention, so every verb taking it
    inherits the same blank-line and BOM handling — `docs show -` reads its topic keys through it
    too, passing ``["-"]`` (it has no command-line-names branch to conflict with).
    """
    if "-" in tokens:
        if tokens != ["-"]:
            raise CommandError(
                "`-` reads actor names from stdin and cannot be combined with actor "
                "names on the command line")
        data = sys.stdin.read()
        if data.startswith("﻿"):                   # drop a leading UTF-8 BOM (str.strip
            data = data[1:]                              # doesn't — it isn't whitespace) so the
        return [ln.strip() for ln in data.splitlines() if ln.strip()]   # first name resolves
    return list(tokens)
