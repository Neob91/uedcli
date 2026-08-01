"""`event` command-family parser registrar."""
from __future__ import annotations

from ._arguments import _tree_flag


def register(sub) -> None:
    event = sub.add_parser(
        "event",
        help="analyse the level's Tag<->Event trigger wiring (who-triggers-whom). Offline, "
             "model-side, no editor. Sub-verbs: graph")
    evsub = event.add_subparsers(dest="sub", required=True)
    egraph = evsub.add_parser(
        "graph",
        help="print $UEDCLI_LEVEL's trigger wiring — one edge per line "
             "'Src (Class) --Event--> Dst (Class)' — plus a lint (dangling wires, unreachable "
             "movers, cycles) on stderr. An edge A->B means actor A's Event property equals actor "
             "B's Tag property (A fires the event B listens for). Reads the trunk model-side; exits "
             "0 even with lint findings (a query verb — lint is advisory)")
    egout = egraph.add_mutually_exclusive_group()
    egout.add_argument(
        "--dot", action="store_true",
        help="emit the graph as Graphviz DOT to stdout (pipe into `dot -Tpng -o wiring.png`) "
             "instead of the one-edge-per-line text; the lint still goes to stderr")
    egout.add_argument(
        "--json", action="store_true",
        help="emit a structured {nodes, edges, lint} JSON object to stdout (lint folded IN, not "
             "on stderr) instead of the text wiring — for scripts")
    _tree_flag(egraph)    # analyse a named tree explicitly instead of $UEDCLI_LEVEL
