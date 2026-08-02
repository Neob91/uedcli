"""`actor folder set|unset|get|rename` — the per-actor trunk folder sidecar. Pure, model-side (no editor).

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


def _run_rename(src, args) -> int:
    """`actor folder rename OLD NEW` — re-parent/rename a whole subtree by prefix rewrite. The set is
    the path, not a name list (no `-`/stdin). Validate both paths before any write; single model-side
    pass over the actors, matching `old` and its subtree case-insensitively (`f == old` or `f`
    startswith `old + "."`), preserving each tail's authored case. PRODUCER: touched Names to stdout,
    the count to stderr. `old` matching no actor is an error (exit 2, owner 2026-08-02) — it is an
    exact typed path, so a typo fails loudly rather than a silent no-op."""
    try:
        folderlib.validate_folder_path(args.old)
        folderlib.validate_folder_path(args.new)
    except ValueError as e:
        raise CommandError(str(e))
    old, new = args.old, args.new
    oldf = old.casefold()
    level = src.load()
    touched = []
    for name, actor in level.actors.items():
        f = actor.folder
        if f is None:
            continue
        ff = f.casefold()
        if ff == oldf:
            actor.folder = new
            touched.append(name)
        elif ff.startswith(oldf + "."):
            actor.folder = new + f[len(old):]              # keep the subtree tail's authored case
            touched.append(name)
    if not touched:
        raise CommandError(f"no actor is filed under folder {old!r}")   # exit 2 (owner, 2026-08-02)
    src.save(verb="folder", args={"old": old, "new": new}, level=level, touched=touched)
    for name in touched:                                   # PRODUCER: touched names → stdout
        print(name)
    print(f"renamed {old} → {new} on {len(touched)} actor(s)", file=sys.stderr)
    return 0


def run(args) -> int:
    """`actor folder set|unset|get`. The path is on `--to` (set only); names are variadic (or `-`
    from stdin). Validate-all before any write (names resolve all-or-nothing, path grammar) so all
    sidecars land or none do (spec §4). `set`/`unset` are PRODUCERS — each touched Name to stdout, a
    human count to stderr — so they chain like the sibling `actor label` verbs (`find … | folder set
    - --to castle.tower | prop set - …`); the two organizational dimensions behave identically.
    `get` prints the folder per actor in argument order, `(none)` for an unfoldered one."""
    src = level_sources.resolve_level_source(args)
    if args.foldersub == "rename":
        return _run_rename(src, args)
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
