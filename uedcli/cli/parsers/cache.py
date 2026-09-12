"""`cache` command-family parser registrar."""
from __future__ import annotations


def register(sub) -> None:
    cache = sub.add_parser(
        "cache", help="manage the per-user derivable caches under ~/.uedcli/cache")
    cachesub = cache.add_subparsers(dest="sub", required=True)
    cachesub.add_parser(
        "clear",
        help="delete BOTH persistent caches (~/.uedcli/cache/schema and .../pkg); both are pure "
             "derivable throwaway and rebuild on the next command. Use for the cache "
             "escape-hatch/paranoid case or to reclaim old decoder/cache-version (v<N>/) dirs.")
    gc = cachesub.add_parser(
        "gc",
        help="shrink BOTH caches without emptying them: delete the orphaned old "
             "decoder/cache-version (v<N>/) dirs, then evict current-version entries "
             "least-recently-used until each cache fits its size/count cap. Cached entries are "
             "derivable, so an evicted one simply re-decodes the next time it is needed. Runs "
             "automatically (best-effort) after a cache write; this is the on-demand surface.")
    gc.add_argument("--max-bytes", type=int, metavar="N", default=None,
                    help="evict until each cache holds at most N bytes (default per cache: the "
                         "built-in cap, 256 MiB, or its own $UEDCLI_*_CACHE_MAX_BYTES). "
                         "0 evicts everything.")
    gc.add_argument("--max-entries", type=int, metavar="N", default=None,
                    help="evict until each cache holds at most N blob files (default per cache: no "
                         "count cap unless its own $UEDCLI_*_CACHE_MAX_ENTRIES sets one). "
                         "0 evicts everything.")
