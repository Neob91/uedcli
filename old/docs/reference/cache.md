# cache

- **`cache clear`** — delete the persistent package-schema cache (`~/.uedcli/cache/schema`); it is
  pure derivable throwaway and rebuilds on the next command (escape-hatch / reclaim old
  decoder-version dirs).
- **`cache gc [--max-bytes N] [--max-entries N]`** — *shrink* that cache instead of emptying it:
  delete orphaned old decoder-version (`v<N>/`) dirs, then evict least-recently-used entries until
  the cache fits its cap (default 256 MiB, no count cap; `N=0` evicts everything). Evicted entries
  just re-decode when next needed. A GC runs automatically after a cache write — reach for this verb
  only to reclaim disk on demand. Prints a one-line summary; a negative cap exits 2.
- **`UEDCLI_SCHEMA_CACHE=off`** disables the persistent cache entirely (any other value, or unset, is
  on) — every command re-decodes packages from scratch instead of reading/writing
  `~/.uedcli/cache/schema`. The escape hatch for a cache dir that can't be written (e.g. root-owned
  after a container run): an unwritable cache is a hard `CacheWriteError` (exit 2) rather than a
  silent slowdown, and its message names this variable alongside the `chown` fix.

See also: [`substrate`](substrate.md).
