+++
priority = "p3"
kind = "chore"
summary = "`actor order --after/--before REF` can write a stale-computed rank when REF is concurrently re-ranked — a stale-READ ordering anomaly, out of the same-actor lost-update scope"
+++

# `actor order --after/--before REF` can write a stale-computed rank when REF is concurrently re-ranked — a stale-READ ordering anomaly, out of the same-actor lost-update scope

`compute_reorder_ranks` derives the moved actor M's new rank from the load-snapshot positions of REF
and its neighbor. If another process re-ranks REF and commits first, M's save has `changed = {M}` (REF
∉ changed), so the trunk-write-safety D3 conflict check never inspects REF — M is written relative to
REF's now-stale position and may sort to the wrong side of REF or collide. This is NOT a lost update
(REF's write survives; only M's ordering is stale) and is **pre-existing** to delta-writes — D3 neither
introduces nor worsens it; collisions stay harmless via the (order_value, name) tiebreak, `level
doctor`'s duplicate-order check flags them, and re-running `actor order` heals it. Logged so D3's
"airtight/100%" framing isn't mistaken for a global ordering-consistency guarantee (it is scoped to
same-actor lost updates over `changed ∪ deleted`). (From the D3 spec review, 2026-07-25.)
