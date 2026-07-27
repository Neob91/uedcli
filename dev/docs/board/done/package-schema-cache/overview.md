+++
priority = "p?"
kind = "implement"
summary = "Persistent per-package decoded-schema cache — a warm `class list`/`class show` is 2.4x-6x faster (v1 shipped)"
+++

# Persistent package-schema cache

Decoding a `.u` package's class schema and property defaults costs 38-211 ms per big package on
every cold run. v1 caches the decode under the per-user cache root, keyed by the package file's
`(realpath, size, mtime_ns)`. `uedcli/config.py`'s `schema_cache_root()` and `schema_cache.py` own
the layout. v2 (cached defaults) is a separate board item.

This item exists to hold the spec and plan, which no board entry owned.
