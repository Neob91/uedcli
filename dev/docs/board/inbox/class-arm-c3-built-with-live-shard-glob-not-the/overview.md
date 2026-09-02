+++
priority = "p3"
kind = "implement"
summary = "class arm C3 built with live shard-glob, not the shard-index roll-up cache"
+++

# class arm C3 built with live shard-glob, not the shard-index roll-up cache

The spec (§2, §9 C3 row) mentions a per-project `shard-index` roll-up, gated on
`(file count, max mtime_ns, total size)`, so a deletion is seen. C3 as built does **not** create
that cache: `class_catalog.classified_refs` / `load_all_shards` glob the shard tree live on each
invocation (`uedcli/class_catalog.py`). That is correct and simpler — a deletion is seen for free,
with no stale-cache risk — and fast enough at current corpus sizes (a few hundred shards).

**When to revisit:** if `classify status`/`tags`/`list` become slow on a large classified corpus,
add the gated roll-up as a pure performance cache behind the same functions. No behavior change; a
test would assert the roll-up and the live glob agree.
