"""`serve` command parser registrar."""
from __future__ import annotations


def register(sub) -> None:
    p = sub.add_parser(
        "serve",
        help="serve a read-only browser GUI over a level's T3D trunk — navigate, inspect, and "
             "(later slices) audit AI changes. Binds localhost only, no auth; blocks until Ctrl-C")
    p.add_argument("level", help="the level to serve (a trunk under the project's maps dir)")
    p.add_argument("--host", default="127.0.0.1",
                   help="bind address (default 127.0.0.1 — localhost only; this is a local "
                        "single-user tool, not a network service)")
    p.add_argument("--port", type=int, default=8765, help="bind port (default 8765)")
