+++
priority = "p3"
kind = "implement"
summary = "Texture classify lifecycle: list-outdated, prune --outdated, re-key across a pixel edit."
+++

# Texture classification lifecycle — outdated tracking, prune, and re-key

The deferred texture-classification lifecycle work: `classify list-outdated`, `classify prune
--outdated`, and a re-key path for a classification when a texture's pixels change (which re-keys its
identity and orphans the shard).

Gated on the re-key ruling in `questions/` — a pixel edit re-keys the classification and
`prune --outdated` would delete a still-accurate description, with no re-key path.

Split out of `unified-asset-catalog` (2026-08-02) so the texture arm's core slices are not blocked on
this lifecycle question. `list-outdated`/`prune` are themselves deferred engine work.
