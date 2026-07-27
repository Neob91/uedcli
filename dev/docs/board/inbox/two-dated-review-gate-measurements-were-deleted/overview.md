+++
priority = "p3"
kind = "owner-question"
summary = "Two dated review-gate measurements were deleted from CLAUDE.md and live in no durable doc"
+++

# Two dated review-gate measurements were deleted from CLAUDE.md and live in no durable doc

The 2026-07-27 de-bloat restructure of `CLAUDE.md` cut two dated measurements from "Review
gates", on the premise that `dev/docs/direction/process.md` already carried them. **It does
not** — `process.md` says only that "cold readers diverge sharply", with no numbers. So these
are now recorded nowhere:

1. **"In a 2026-07-25 round the two Opus reviewers overlapped on only two of eight findings, and
   the single most severe finding of the whole run appeared in one reviewer's report and not the
   other's."** This was the evidence for *why headcount buys breadth, not depth* — the surviving
   rule that says when a one-reviewer round feels thin you give the work a spec moment or
   escalate, rather than quietly re-widening a row. Without the number, a future agent arguing to
   re-widen has nothing to argue against.
2. **"On 2026-07-25 a round found that the previous round's own fixes had shipped three wrong
   measurements and an unpinned spike finding."** This was the evidence for *expect round 2 to
   find new things*. Its citation was **already dangling before the restructure** — the old text
   pointed at `dev/docs/direction/process.md` as the evidence and that file never contained it.

`grep -rn 'two of eight\|three wrong measurements'` now hits only
`dev/docs/board/inbox/andrzej-the-two-claude-md-files-now-give/overview.md`, which records the
"two of eight" figure while noting the citation was already broken.

**Why this is an owner question, not an agent fix.** The durable home for both is
`dev/docs/direction/process.md`, which an agent may never write without an explicit yes
(`CLAUDE.md` "Direction docs"). The proposed addition, for the owner to approve or reject, is a
bullet under that doc's existing "Every change is read cold before it is declared done" entry:

> Measured 2026-07-25: two cold Opus reviewers over one artifact overlapped on only two of eight
> findings, and the run's single most severe finding appeared in one report and not the other.
> The same day, a round found that the previous round's own fixes had shipped three wrong
> measurements and an unpinned spike finding — which is why round 2 is expected to find new
> things.

The second sentence's original evidence pointer was already broken, so it may be worth dropping
rather than re-pinning if nobody can re-verify it. Surfaced by the review round on the
restructure.
