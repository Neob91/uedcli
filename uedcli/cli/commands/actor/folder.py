"""`actor folder set|unset|get` — the per-actor trunk folder sidecar. Pure, model-side (no editor).

Resolves the trunk level source (honouring `--tree` / `$UEDCLI_LEVEL`), then reads/writes. The
source-free `--tree stash|prefab` rejection (folders are trunk-only) runs in `routes.py` before this
module resolves anything. This module uses `cli.level_sources`/`cli.targets` and the `folderlib`/
`query` services; it never imports another command family or the router.
"""
from __future__ import annotations

import sys

from ... import level_sources
from ... import targets as target_names
from ...errors import CommandError
from .... import folderlib, query


def run(args) -> int:
    """`actor folder set|unset|get`. The path is on `--to` (set only); names are variadic (or `-`
    from stdin). Validate-all before any write (names resolve all-or-nothing, path grammar) so all
    sidecars land or none do (spec §4). `set`/`unset` are PRODUCERS — each touched Name to stdout, a
    human count to stderr — so they chain like the sibling `actor label` verbs (`find … | folder set
    - --to castle.tower | prop set - …`); the two organizational dimensions behave identically.
    `get` prints the folder per actor in argument order, `(none)` for an unfoldered one."""
    src = level_sources.resolve_level_source(args)
    raw = target_names.resolve_target_names(args.names)              # `-` → names from stdin (spec §4)
    if not raw:
        return 0                                          # empty stdin: no-op, exit 0
    if args.foldersub == "set":
        try:
            folderlib.validate_folder_path(args.to)       # grammar-check before touching the trunk
        except ValueError as e:
            raise CommandError(str(e))
    level = src.load()
    try:
        names = list(dict.fromkeys(query.resolve_actor_names(level, raw)))
    except KeyError as e:
        print(e.args[0], file=sys.stderr)
        return 2
    if args.foldersub == "get":
        if getattr(args, "json", False):
            import json
            # {name: folder|null} — an unfoldered actor maps to null, not the `(none)` sentinel a
            # script would otherwise have to special-case.
            print(json.dumps({n: level.actors[n].folder for n in names}, indent=2))
            return 0
        for n in names:
            f = level.actors[n].folder
            print(f if f is not None else "(none)")
        return 0
    new = args.to if args.foldersub == "set" else None
    for n in names:
        level.actors[n].folder = new
    src.save(verb="folder", args={"names": names, "folder": new}, level=level, touched=names)
    for name in names:                                    # PRODUCER: touched names → stdout (feed `| verb -`)
        print(name)
    summary = f"set folder {new} on" if args.foldersub == "set" else "unfoldered"
    print(f"{summary} {len(names)} actor(s)", file=sys.stderr)
    return 0
