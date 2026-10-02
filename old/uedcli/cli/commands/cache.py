"""`cache clear|gc` over the two per-user derivable package caches: the schema cache and the
on-disk decoded-package cache. Needs no project or editor."""
from __future__ import annotations

from ... import config, pkg_cache, schema_cache
from ..errors import CommandError


def run(args) -> int:
    """`uedcli cache clear|gc` over BOTH per-user caches (`~/.uedcli/cache/schema` and
    `~/.uedcli/cache/pkg`) — one line of output per cache, both always acted on.

    - `clear` DELETES each cache. Pure derivable throwaway; a no-op (still exit 0) per cache
      already absent.
    - `gc` SHRINKS each cache: reclaims orphaned `v<older>/` version dirs a decoder/cache-version
      bump left unreachable, then LRU-evicts current-version blobs (by atime) until under the
      byte/count cap. `--max-bytes`/`--max-entries` override the built-in/env defaults for this
      run, applied to both caches. Eviction has no correctness pressure — blobs are immutable and
      derivable, so an evicted one just re-decodes on next use.

    Neither needs a project or an editor."""
    if args.sub == "clear":
        for mod, root in ((schema_cache, config.schema_cache_root()),
                          (pkg_cache, config.pkg_cache_root())):
            removed = mod.clear()
            print(f"cleared {root}" if removed else f"nothing to clear ({root} does not exist)")
        return 0
    if args.sub == "gc":
        for flag, val in (("--max-bytes", args.max_bytes), ("--max-entries", args.max_entries)):
            if val is not None and val < 0:               # a negative cap is meaningless, not "unbounded"
                raise CommandError(f"cache gc {flag}: must be >= 0, got {val}")
        # `-1` is sweep()'s "use the env-or-constant default" sentinel; an explicit flag overrides it.
        max_bytes = -1 if args.max_bytes is None else args.max_bytes
        max_entries = -1 if args.max_entries is None else args.max_entries
        for mod, root in ((schema_cache, config.schema_cache_root()),
                          (pkg_cache, config.pkg_cache_root())):
            stats = mod.sweep(max_bytes=max_bytes, max_entries=max_entries)
            print(f"{root}: removed {stats['removed_version_dirs']} old version dir(s), evicted "
                  f"{stats['evicted']} entries ({stats['freed_bytes']} bytes freed); "
                  f"kept {stats['kept_entries']} entries ({stats['kept_bytes']} bytes)")
        return 0
    raise CommandError(f"unimplemented cache sub-verb: {args.sub}")
