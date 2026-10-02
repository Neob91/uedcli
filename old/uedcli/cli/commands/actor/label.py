"""`actor label add|remove|clear|get` — the per-actor trunk labels sidecar. Pure, model-side.

Resolves the trunk level source (honouring `--tree` / `$UEDCLI_LEVEL`), then reads/writes. The
source-free `--tree stash|prefab` rejection (labels are trunk-only this slice) runs in `routes.py`
before this module resolves anything. This module uses `cli.level_sources`/`cli.targets` and the
`labellib`/`query` services; it never imports another command family or the router.
"""
from __future__ import annotations

import sys

from ... import level_sources
from ... import targets as target_names
from ...errors import CommandError
from .... import labellib, query


def run(args) -> int:
    """`actor label add|remove|clear|get`. Labels (the values) are on a repeatable `--label`
    (add/remove only); names are variadic (or `-` from stdin). Validate-all-then-apply: every
    `--label` is grammar-checked and every name resolves all-or-nothing BEFORE any write, so a bad
    value leaves the whole tree untouched (spec §4). `add` unions, `remove` subtracts (missing = a
    no-op), `clear` empties. The mutating verbs are PRODUCERS — each touched Name to stdout, a human
    count to stderr — so they chain (`find … | label add - --label lit | prop set - …`). `get` prints
    `Name<TAB>l1,l2` (sorted, comma-joined; unlabelled → `Name<TAB>(none)`), `--json` → `{name: […]}`."""
    src = level_sources.resolve_level_source(args)
    raw = target_names.resolve_target_names(args.names)              # `-` → names from stdin (spec §4)
    if not raw:
        return 0                                          # empty stdin: no-op, exit 0
    new_labels: frozenset[str] = frozenset()
    if args.labelsub in ("add", "remove"):
        for lbl in args.label:                            # grammar-check every value before any write
            try:
                labellib.validate_label(lbl)
            except ValueError as e:
                raise CommandError(str(e))
        new_labels = frozenset(args.label)
    level = src.load()
    try:
        names = list(dict.fromkeys(query.resolve_actor_names(level, raw)))
    except KeyError as e:
        print(e.args[0], file=sys.stderr)
        return 2
    if args.labelsub == "get":
        if getattr(args, "json", False):
            import json
            print(json.dumps({n: sorted(level.actors[n].labels) for n in names}, indent=2))
            return 0
        for n in names:
            labs = level.actors[n].labels
            print(f"{n}\t{','.join(sorted(labs)) if labs else '(none)'}")
        return 0
    for n in names:
        cur = level.actors[n].labels
        if args.labelsub == "add":
            level.actors[n].labels = cur | new_labels
        elif args.labelsub == "remove":
            level.actors[n].labels = cur - new_labels
        else:                                             # clear
            level.actors[n].labels = frozenset()
    src.save(verb="label", args={"names": names, "sub": args.labelsub}, level=level, touched=names)
    for name in names:                                    # PRODUCER: touched names → stdout (feed `| verb -`)
        print(name)
    summary = {"add": "labelled", "remove": "removed labels from",
               "clear": "cleared labels on"}[args.labelsub]
    print(f"{summary} {len(names)} actor(s)", file=sys.stderr)
    return 0
