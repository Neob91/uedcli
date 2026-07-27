+++
priority = "p2"
kind = "owner-question"
summary = "RESOLVED 2026-07-26 — was: Warm-editor materialize spike (SP-E) RAN 2026-07-19 and FOUND A BLOCKER"
+++

# RESOLVED 2026-07-26 — was: Warm-editor materialize spike (SP-E) RAN 2026-07-19 and FOUND A BLOCKER

The design decision is made (the two `[OWNER — confirm]`
items above); the spec is revised; the follow-up spike is `to-spike.md` SP-F. Kept below for its
evidence until SP-F lands, then delete. Original entry: Spike
`spikes/2026-07-18-warm-editor-materialize/results.md` (2-reviewer cold-gated; harnesses committed).
**Editor reuse itself works** (a warm editor builds the castle correctly, and a genuinely-reused
*successful* build is `canonical_level_hash`-identical to a fresh build), **but the H3 post-verify —
which today runs AGAINST the warm editor — breaks it: ~50% of reused builds fail** because the
verify leaves the editor in a state where a later build's `MAP SAVE` silently writes no file
(`no_verify` reuse is 0/4-clean; isolating only the UCC export does NOT fix it → the disruptor is
the in-editor qualify dump / editor-mid-verify racing the next fire-and-forget drive; §89 class).
So `specs/2026-07-18-warm-editor-materialize.md` §4.4's "H3 verify against the same live editor"
(D-Q3) must change. **DECISION FOR YOU (spec §8 SP-E RESULTS has the detail):** which fix —
(1) run the WHOLE H3 verify (export+qualify) against a SEPARATE throwaway editor (works regardless
of cause; but a cold verify editor costs ~15 s ≈ the entire ~16 s warm saving, so it'd need
warm-pooling); or (2) a robust editor CPU-idle barrier after verify (cheap, keeps the saving — but
only works if the cause is a transient race, which is NOT yet discriminated from durable state; gate
it behind a quick discriminator first). Then SP-E must be **re-run to confirm 0/N** before building.
Also surfaced: **SP-E.2 saw a possible REAL cross-level stale-pool residue** (a CASTLE `Bounce_`
actor leaked into an anchor build's verify) — inconclusive (flaky-editor run), re-test after the
fix; and **SP-E.7 (colliding names) not reached** (needs the fix + a fixture). The spec + `quirks.md`
are folded; the build is NOT green-lit as specced. **The warm-editor spec is otherwise ready — this
is the one gate.**
