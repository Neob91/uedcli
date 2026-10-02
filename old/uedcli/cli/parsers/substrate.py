"""`substrate` command-family parser registrar."""
from __future__ import annotations


def register(sub) -> None:
    substrate = sub.add_parser("substrate", help="substrate build utilities (package stubbing)")
    subsub = substrate.add_subparsers(dest="sub", required=True)
    stub = subsub.add_parser(
        "stub", help="convert a Deus Ex v68 code package into a UED22-loadable v69 stub `.u`")
    stub.add_argument("package", nargs="?",
                      help="Deus Ex v68 code package to stub (bare name, no .u), e.g. DeusExItems")
    stub.add_argument("--force", action="store_true",
                      help="rebuild even if a current cache entry exists (bypass the cache hit)")
    stub.add_argument("--list", action="store_true",
                      help="print the stub cache manifest and exit (no build)")
