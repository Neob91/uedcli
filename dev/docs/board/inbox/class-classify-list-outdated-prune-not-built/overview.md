+++
priority = "p2"
kind = "implement"
summary = "class classify list-outdated / prune not built (deferred from C3 slice)"
+++

# class classify list-outdated / prune not built (deferred from C3 slice)

The spec §7 verb table lists `class classify list-outdated` and `class classify prune [--outdated]`
(shards whose class no longer resolves on the composed path). The §9 C3 delivery row does **not**
list them, and the C3 build task scoped them out, so they are **not built**.

Consequence today: a shard whose class has left the path (renamed/removed) is an **outdated entry**
with no CLI surface to list or remove it. `classify unset --all <ref>` still works on it (unset
validates shard shape + existence, not class-on-path existence — deliberate, so a shard can outlive
its class), but there is no *discovery* of which shards are outdated.

**To finish (a later slice):**
- `list-outdated` — for each shard, resolve its `ref` against the class index; print those that miss.
- `prune [--outdated]` — remove outdated shards (or, with an explicit ref set on stdin, those).

The store already keeps the write-once `ref` these need (`direction/asset-catalog.md`: change is a
derived query; outdated = a shard whose identity no longer resolves). Engine support is in place —
`class_catalog.load_all_shards` yields every shard's `ref`.
