# Review gates — the detail

`CLAUDE.md` "Review gates" carries the operative core: the three moments, the reviewer/model table,
the tier rules, the observability test, the two-round ceiling. **It is the only place the reviewer
counts live — never restate them here or anywhere else.** This doc holds the elaborations that do
not need to be resident in every session. Why the gate is shaped this way:
[`../direction/process.md`](../direction/process.md).

## Dispatching a round

- **Do not offer, propose, or "stand by to" run a round.** "Say the word and I'll review it" is a
  rule violation: the round should already have run.
- **Do not batch a gate behind a question.** If a decision is genuinely owed, ask it *and* run
  whatever round is already owed — they are independent.
- **Round 2 fires automatically too**, on its own trigger. It is not a separate permission.
- **Report the OUTCOME, not the intent.** The user should learn a round happened by reading its
  findings.
- **The ONE thing worth surfacing first is scale**: if a single moment would dispatch more than 3
  reviewers, or several rounds would fire at once, say what is about to run in one line and then run
  it. That is a notification, not a request.
- **A round's headcount IS its parallel width** — every reviewer in a round is dispatched in ONE
  message. This machine runs only ~2 concurrent subagents before the rest queue, so a wider round
  serialises.
- **Headcount buys breadth, not depth.** A one-reviewer round *will* miss what a wider one would
  have caught, because cold reviewers diverge sharply. When that matters, do **not** quietly
  re-widen a row: give the work a **spec** moment, or escalate to the owner.

## Which row a change takes

- **`build` is the DEFAULT row for anything non-trivial that is not a spec or a plan** — a code
  change, a chore sweep, a board reorganisation. "Build" means *work that is finished*, not *code
  was written*, so no non-trivial change is ever left without a row.
- **Specced pipeline work goes through a plan doc, so it gets a plan round**; only one-shot
  `chore`/`debug` items and one-file fixes have no plan and therefore no plan round. Not writing a
  plan is NOT a way to skip that round — an item reaches `to-build/` with a *reviewed* plan.
- **Docs-only** means it touches no code and no test: `CLAUDE.md`, `dev/docs/*`, `docs/*`, the board.
  Its failure mode is a stale sentence, not a silent defect. A **spec** or **plan** is a doc but
  keeps its own row — those two moments exist precisely to catch a design before it is built.
- **The trivial and docs-only rows are TIERS, not moments** — each replaces whichever row the change
  would otherwise have taken, and neither has a spec or plan round. **A batch takes its
  least-trivial member's row:** nine doc typos plus one code fix is a build review, not a docs-only
  or trivial one.
- **NO cheap reviewer rides along.** The trivial tier's single Haiku pass is the ONLY place a cheap
  reviewer appears, and its findings face exactly the same observability test — a finding is never
  discounted for having come from the cheap reviewer.
- **If the Haiku pass shows the change was not trivial after all**, it is re-gated from scratch at
  its real tier — the cheap pass does not count as that tier's round 1.

### What "trivial" excludes

A trivial change is one that changes no reader's understanding and no tool behavior: a typo, a
formatting fix, a comment, a test rename, a broken link.

- **NOT trivial, at any size:** anything that changes what a rule, doc, spec, plan, or engine-fact
  note *says* — every change to `CLAUDE.md`, `../direction/*.md`, `../rationale/*.md`, `../rules/*.md`,
  `../architecture.md`, `../unrealed/*.md`, a spec/plan, or a spike write-up is a real change,
  because a future agent will act on it.
- **NOT trivial:** anything that changes what the tool does, deletes anything, or changes executable
  behavior — including a one-line change to load-bearing code, exactly the case the cheap tier must
  not swallow. (A comment or a test rename does not change executable behavior; a `help=` string is
  user-visible output, so rewording one is **docs-only**, not trivial.)
- **The two NOT-trivial lists WIN over the examples above.** A typo or a broken link inside one of
  the rule/doc files named above is not trivial just because typos are listed as trivial.
- **When it is arguable, it is not trivial.**

## What reviewers are told

**Reviewers get CONTEXT but never PRIMING.** Only one of the two is forbidden.

- **Context is REQUIRED.** A reviewer who does not know the conventions cannot tell a deliberate
  choice from a defect. Give every reviewer `CLAUDE.md`, and for a **plan** or **build** review the
  spec (and plan) it implements — a build reviewer who has not read the spec cannot check
  conformance to it. **Name by path every doc the reviewer must read before acting**: a subagent
  does not inherit your reading, and one that has not read `../unrealed/t3d.md` will flag correct
  T3D handling as a bug.
- **Priming is FORBIDDEN.** Never show a reviewer the previous round's findings, never say what you
  expect them to find, never reuse a reviewer from an earlier round. A reviewer told what was
  already found stops looking for what wasn't.
- **Round 2 is smaller in HEADCOUNT, not in reading.** Its reviewers get the full updated artifact
  *plus* the diff since round 1 — they are cold, and a finding anywhere in the updated work counts,
  not just inside that diff. Handing over the diff is not priming; what round 1 found is never
  disclosed.

## Dispositioning findings

The test is observability, and there is no severity scale — cold reviewers cannot apply one
consistently, and a scale invites arguing a real finding down a tier.

> A finding may be left standing ONLY if fixing it would change nothing anyone would ever observe —
> pure wording, formatting, or naming taste.

**A REVIEWER FLAGS ANY DOC THEY CANNOT FULLY UNDERSTAND, OR THAT IS AMBIGUOUS.** That is a real
finding, not wording taste, and the observability test does not excuse it: a doc a cold reader
cannot follow is a doc that will be acted on wrongly. Bloat is the same finding from the other side.
*(Owner ruling, 2026-07-27.)*

Everything else is **fixed**, **logged** (`bin/board new inbox`, with enough detail to act on),
**escalated to the owner** as an explicit decision, or **refuted** — the reviewer asserted something
the code or doc does not actually do.

- **A refutation is admissible ONLY with the check that disproves it recorded** (commit message or
  board). A round whose findings were all refuted is still a round that happened, with its evidence
  written down.
- **Nothing is waved through** because the round was otherwise clean, or because the problem is
  pre-existing.
- **A finding that is real but out of scope still blocks the round until it is logged** — logging is
  what makes deferring legitimate; "noted in chat" is not, because chat scrolls away.
- **The same standard applies to a finding you leave standing**: its stated reason goes in the commit
  message or on the board, never only in chat.

## The two-round ceiling

Round 2 exists for exactly one reason: **the fixes are themselves unreviewed.** So the trigger is
whether the artifact CHANGED.

- **Round 2 runs iff resolving round 1 changed the artifact.** If round 1 came back clean, or its
  findings were all dispositioned WITHOUT touching the artifact — logged, refuted, or escalated —
  there is no new, unreviewed text to look at, and the gate is passed at round 1. On small changes
  this is the common case.
- **"The artifact" = the files under review**, excluding the commit message and an item's **own
  board bookkeeping**: `../board/*/*/overview.md` and `../board/*/*/questions/`. Logging a finding to
  the board is therefore never itself the trigger, even when those files are part of the diff;
  changing a doc or adding a test to resolve a finding IS. **The exclusion is that narrow on
  purpose** — a `spec.md` or `plan.md` lives inside its board item too, so excluding the whole board
  would strip round 2 from every spec and plan review; editing a spec or plan to resolve a round-1
  finding is exactly the unreviewed change round 2 exists for.
- **This is NOT a licence to log instead of fix.** Logging is for a finding that is real but
  genuinely out of scope for *this* change. Choosing to log an in-scope defect so that round 2 never
  fires is gaming the gate, and the finding's stated reason — which the board or the commit message
  must carry anyway — is exactly where that shows.
- **Expect round 2 to find NEW things.** A fix can introduce a defect, and cold reviewers diverge.
  That is normal, not a signal that the ceiling is wrong.
- **After round 2, the gate is passed.** Anything still standing is fixed, logged, or escalated —
  all three outlets stay open — and the work is declared done. **There is no round 3.**
- **A STRUCTURAL finding STOPS the work, in EITHER round.** If a round's findings say the *design*
  is wrong rather than that a detail is wrong, stop and escalate to the owner. It **replaces** the
  remaining round — never licenses a third — and it does **NOT pass the gate**: the work is parked,
  not declared done and not merged, until the owner rules, after which the artifact re-enters the
  gate at round 1 of its tier. So a structural escalation is not a cheap "fix-free round 1".

## Batching

The unit of review is a coherent batch of work, not an individual edit. A round costs real tokens,
and reviewers see *more* this way: a batch diff exposes inconsistencies between sibling changes that
per-change rounds structurally cannot see.

- **Land the batch, then gate it.** Commit each small change as it is finished — **pushing
  deliberately does NOT wait for the gate.** The gate runs over the accumulated range before the
  batch is declared done, not before each commit.
- **Flush the open batch** before ending a session, before switching to unrelated work, or as soon
  as it is large enough to be worth a round — whichever comes first. A batch is never carried across
  a context boundary, and a lone trivial change with nothing to batch against is gated at that flush.
- **Split a batch when it stops being reviewable** — when the diff is large enough that a reviewer
  would skim, or when one risky change would hide among many safe ones. A subtle change to
  load-bearing code gets its own round even if it is one line; a hundred lines of mechanical rename
  does not.
- **Never batch across the three moments.** A spec review, a plan review and a build review are
  different questions over different artifacts.
