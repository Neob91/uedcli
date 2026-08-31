# cache

- **`cache clear`** — delete the persistent package-schema cache (`~/.uedcli/cache/schema`); it is
  pure derivable throwaway and rebuilds on the next command (escape-hatch / reclaim old
  decoder-version dirs).
- **`cache gc [--max-bytes N] [--max-entries N]`** — *shrink* that cache instead of emptying it:
  delete orphaned old decoder-version (`v<N>/`) dirs, then evict least-recently-used entries until
  the cache fits its cap (default 256 MiB, no count cap; `N=0` evicts everything). Evicted entries
  just re-decode when next needed. A GC runs automatically after a cache write — reach for this verb
  only to reclaim disk on demand. Prints a one-line summary; a negative cap exits 2.

See also: [`substrate`](substrate.md).
