"""`cache` command-family parser registrar."""
from __future__ import annotations


def register(sub) -> None:
    cache = sub.add_parser(
        "cache", help="manage the per-user derivable caches under ~/.uedcli/cache")
    cachesub = cache.add_subparsers(dest="sub", required=True)
    cachesub.add_parser(
        "clear",
        help="delete the persistent package-schema cache (~/.uedcli/cache/schema); it is pure "
             "derivable throwaway and rebuilds on the next command. Use for the schema-cache "
             "escape-hatch/paranoid case or to reclaim old decoder-version (v<N>/) dirs.")
    gc = cachesub.add_parser(
        "gc",
        help="shrink the package-schema cache without emptying it: delete the orphaned old "
             "decoder-version (v<N>/) dirs, then evict current-version entries least-recently-used "
             "until the cache fits its size/count cap. Cached entries are derivable, so an evicted "
             "one simply re-decodes the next time it is needed. Runs automatically (best-effort) "
             "after a cache write; this is the on-demand surface.")
    gc.add_argument("--max-bytes", type=int, metavar="N", default=None,
                    help="evict until the cache holds at most N bytes (default: the built-in cap, "
                         "256 MiB, or $UEDCLI_SCHEMA_CACHE_MAX_BYTES). 0 evicts everything.")
    gc.add_argument("--max-entries", type=int, metavar="N", default=None,
                    help="evict until the cache holds at most N blob files (default: no count cap "
                         "unless $UEDCLI_SCHEMA_CACHE_MAX_ENTRIES sets one). 0 evicts everything.")
