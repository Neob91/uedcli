"""`cache clear|gc` over the per-user package-schema cache. Needs no project or editor."""
from __future__ import annotations

from ... import config, schema_cache
from ..errors import CommandError


def run(args) -> int:
    """`uedcli cache clear|gc` over the per-user package-schema cache (`~/.uedcli/cache/schema`).

    - `clear` DELETES the whole cache. Pure derivable throwaway; a no-op (still exit 0) when the dir
      is already absent.
    - `gc` SHRINKS it: `schema_cache.sweep()` reclaims the orphaned `v<older>/` decoder-version dirs a
      `SCHEMA_CACHE_VERSION` bump left unreachable, then LRU-evicts current-version blobs (by atime)
      until the cache is under the byte/count cap. `--max-bytes`/`--max-entries` override the
      built-in/env defaults for this run only. Eviction has no correctness pressure — blobs are
      immutable and derivable, so an evicted one just re-decodes on next use — and `sweep()` never
      raises, so `gc` cannot fail on a racing writer or an unremovable file. The same sweep already
      runs best-effort after a cache write; this is the on-demand surface.

    Neither needs a project or an editor."""
    if args.sub == "clear":
        removed = schema_cache.clear()
        print(f"cleared {config.schema_cache_root()}" if removed
              else f"nothing to clear ({config.schema_cache_root()} does not exist)")
        return 0
    if args.sub == "gc":
        for flag, val in (("--max-bytes", args.max_bytes), ("--max-entries", args.max_entries)):
            if val is not None and val < 0:               # a negative cap is meaningless, not "unbounded"
                raise CommandError(f"cache gc {flag}: must be >= 0, got {val}")
        # `-1` is sweep()'s "use the env-or-constant default" sentinel; an explicit flag overrides it.
        stats = schema_cache.sweep(
            max_bytes=-1 if args.max_bytes is None else args.max_bytes,
            max_entries=-1 if args.max_entries is None else args.max_entries)
        print(f"{config.schema_cache_root()}: removed {stats['removed_version_dirs']} old version "
              f"dir(s), evicted {stats['evicted']} entries ({stats['freed_bytes']} bytes freed); "
              f"kept {stats['kept_entries']} entries ({stats['kept_bytes']} bytes)")
        return 0
    raise CommandError(f"unimplemented cache sub-verb: {args.sub}")
