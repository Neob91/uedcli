"""`event` command family — read-only Tag<->Event trigger-wiring analysis over the current level.

`cli.dispatch` enters through `run(args)`, which resolves the level source (honouring `--tree` /
`$UEDCLI_LEVEL`) before building the graph — the same order the transitional monolith used. Pure and
model-side (no editor). This module uses `cli.resources`/`cli.level_sources` and the `eventgraph`
service; it never imports another command family or the router.
"""
from __future__ import annotations

import sys

from .. import level_sources, resources
from ..errors import CommandError


def run(args) -> int:
    """Route one `event` invocation. Resolves the level source (no project ⇒ clean exit 2), then
    runs the requested subverb."""
    if args.sub == "graph":
        return _event_graph(args, level_sources.resolve_level_source(args))
    raise CommandError(f"unimplemented event sub-verb: {args.sub}")


def _event_graph(args, src) -> int:
    """`event graph` — print the current level's Tag<->Event trigger wiring + lint. Pure,
    model-side (no editor). Default: one edge per line to stdout, lint + counts to stderr.
    `--dot`: Graphviz DOT to stdout (lint to stderr). `--json`: {nodes,edges,lint} to stdout (lint
    folded in). Exit 0 on any successful scan — a query/producer verb; lint is advisory (decision
    2026-07-18 20:54 UTC). Real errors (no project/level) still exit 2 via the standard guards."""
    from ... import eventgraph
    level = src.load()
    graph = eventgraph.build_graph(level, resources.mover_index(args, "event graph"))
    findings = eventgraph.lint_graph(graph, level)
    if getattr(args, "json", False):
        import json
        print(json.dumps(eventgraph.to_json_obj(graph, findings), indent=2))
        return 0
    if getattr(args, "dot", False):
        print(eventgraph.format_dot(graph))
    else:
        text = eventgraph.format_text(graph)
        if text:
            print(text)
    # Human summary + lint → stderr (never pollutes the stdout wiring pipe).
    print(f"{len(graph.nodes)} eventing actor(s), {len(graph.edges)} wire(s), "
          f"{len(findings)} lint finding(s)", file=sys.stderr)
    for f in findings:
        print(f"lint[{f.kind}]: {f.message}", file=sys.stderr)
    return 0
