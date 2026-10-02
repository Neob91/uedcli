+++
priority = "p3"
kind = "implement"
summary = "effective-props resolution ~15-47% slower per-actor after struct-member default fix"
+++

# effective-props resolution ~15-47% slower per-actor after struct-member default fix

Found during the final whole-branch review's fix-round re-review for
`gui-inspector-effective-props-search-show-all` (2026-09-23), measured directly (`_scratch/rr_perf.py`
in that review's worktree — not committed, gitignored scratch), not estimated.

## What changed

Commit `dc1b1aa1` fixed a real correctness bug: every unstated struct member's `default_value` was
showing `"0"` instead of the true class-default member value (see that plan's `progress.md`, "Critical
1"). The fix threads a real member-chain `ResolvedPath` through `propedit.effective_value` for every
struct member, instead of a bare top-level lookup.

Measured cost, old vs. new resolution time for one actor (same warm `ClassCtx`, `uned/UED22`):

| class | old (ms) | new (ms) | delta |
|---|---|---|---|
| `DeusEx.Karkian` | 13.06 | 17.84 | +37% |
| `DeusEx.ComputerSecurity` | 14.30 | 16.32 | +14% |
| `DeusEx.MedKit` | 2.50 | 3.41 | +36% |
| `Engine.Light` | 1.80 | 2.64 | +47% |

Part of this delta is legitimate — the fixed code now correctly resolves MORE leaves than before (16
more for Karkian, 12 more for ComputerSecurity — a byproduct of Critical 2's array-of-struct cache
bug also being fixed in the same round, which previously silently dropped some struct members
entirely). But the review traced a real, fixable inefficiency too: every leaf now calls
`propedit._stored_map(actor)` (rebuilds the actor's WHOLE stored-property dict from scratch) AND
`propedit.effective_value`, which calls `_stored_map` again internally, and for a struct-typed base,
re-runs `structtext.full_struct_text`'s full zero+default+stored merge — ONCE PER MEMBER. A 7-member ×
4-element struct array therefore re-merges the same struct text 28 times instead of once.

## Likely fix, not attempted here

Hoist `_stored_map(actor)` to be computed ONCE per actor (at the top of `resolve_actor_props`) and
threaded down, instead of being rebuilt on every leaf's `effective_value` call. Whether
`full_struct_text`'s per-member re-merge can similarly be hoisted to once-per-struct-array (rather than
once-per-member) wasn't investigated — read `uedcli/propedit/edit.py`'s `effective_value`/
`structtext.full_struct_text` and `uedcli/effective_props.py`'s struct/array resolution before
attempting a fix.

## Why not fixed in the same pass

Correctness rightly won over performance in that fix round — this is a real but non-blocking cost,
flagged by the review as "worth a board item rather than a blocker." No user-facing report of slowness
motivated this; it's a measured cost from fixing the correctness bug, worth revisiting if `/scene`
build time on a large actor count (a full retail level) turns out to matter in practice — which may
also be affected by the separate payload-redesign work in progress
(`dev/docs/board/to-spec/gui-inspector-props-payload-redesign/` once filed, or check `to-spec`/
`to-plan` for its current stage) that changes how/when `default_value` is resolved at all.
