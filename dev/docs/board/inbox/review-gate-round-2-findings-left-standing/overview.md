+++
priority = "p2"
kind = "chore"
summary = "Review-gate round-2 findings left standing (logged, not fixed)"
+++

# Review-gate round-2 findings left standing (logged, not fixed)

The 2026-07-25
gate-loosening batch's round 2 raised 14 findings; most were fixed in that batch, these were not.
Logged under the post-round-2 rule (fixed / logged / escalated / refuted), so they are deferred
legitimately rather than dropped:
1. **The trivial-tier backstop cannot fire as written.** `CLAUDE.md` says "if the Haiku pass shows
   the change was not trivial after all, it is re-gated from scratch" — but nothing requires the
   reviewer prompt to state the triviality claim or ask the reviewer to challenge it, so a
   reviewer given an ordinary "review this diff" prompt never volunteers a tier verdict. Fix: make
   the trivial-tier prompt quote the claim and demand an explicit trivial/not-trivial answer.
2. **Asymmetric loophole guard.** The plan round is explicitly nailed shut ("not writing a plan is
   NOT a way to skip this round") but the **spec** round has no counterpart, and the plan round is
   bound to "specced pipeline work" — so an agent that writes no spec skips both rounds and only
   faces the build round. Fix: mirror the guard onto moment 1.
3. **Five forward-looking docs still instruct the OLD gate** (the 2026-07-25 sweep missed them;
   each restates a reviewer count instead of citing `CLAUDE.md`, which the gate now forbids):
   `dev/docs/plans/2026-07-22-labels-granularity-plan.md:22-23`,
   `dev/docs/board/to-plan.md:75`,
   `dev/docs/specs/2026-07-19-leveldesign-docs-skills.md:319`,
   `Tools/uplayctl/docs/dev/plans/2026-07-12-…-place-ids-plan.md:249-250`,
   `Tools/uplayctl/docs/dev/specs/2026-07-02-navigation-exits-followpath-rooms-design.md:246-247`.
4. **Contradiction to reconcile:** `specs/2026-07-19-leveldesign-docs-skills.md:3` says its spec
   gate is "pending" while `board/to-plan.md:69` calls the same spec "cold-review-gated +
   revised". One is wrong, and either way it costs or skips a whole spec round.
5. **Both 2026-07-25 ledger entries were reworded in place after being pushed** (the plan-round
   trigger, the round-2 condition, the trivial definition and the uplayctl `Refs` note all
   changed), and only the "~15–25 %" arithmetic correction is disclosed in the text. Both ledgers'
   headers say an active decision is "never reworded, only superseded". Fix: either append a
   disclosure note to both entries, or add a header carve-out permitting in-place correction while
   an entry is still inside its own review gate. **Andrzej's call which.**
