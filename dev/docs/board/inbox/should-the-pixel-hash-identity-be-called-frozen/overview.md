+++
priority = "p2"
kind = "owner-question"
summary = "Should the pixel-hash identity be called FROZEN in `direction/`?"
+++

# Should the pixel-hash identity be called FROZEN in `direction/`?

The
topic already records texture identity as the exact pixel hash (`sha256` over w, h, raw RGB), which
is correct and needs no change. What it does *not* say is that the function is **frozen**: every
tracked shard's path IS that digest, so any change to what the decoder emits silently re-keys every
shard at once — all classifications read back "unclassified" and become prunable. That is the one
irreversibility in the design that can destroy authored work, and it currently lives only in
`specs/…-unified-asset-catalog.md` §3b and the plan. Proposed one-line addition to the same section:

> The identity function is **frozen** — `(w, h, RGB)` in that order, pinned by a committed golden.
> Changing what the decoder emits re-keys every shard and orphans every classification, so it moves
> only by an explicit migration that rewrites them. Adding a new *fact* about an asset is always
> safe; changing the *decoder* never is.
