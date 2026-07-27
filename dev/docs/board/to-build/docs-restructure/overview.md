+++
priority = "p1"
kind = "implement"
summary = "Retire the append-only decisions ledger; replace it and direction.md with two revised-in-place per-topic trees."
+++

# Docs restructure — `direction/` + `rationale/`, no ledger

Plan: board item `docs-restructure-is-complete`.
Spec: board item `docs-restructure-is-complete`.
Five review rounds total — three on the spec (two of which returned structural findings and were
resolved by the owner's rulings), two on the plan; all findings folded or logged to the inbox.

**The split is by WHO DECIDED, not by subject.** `direction/<topic>.md` holds what the owner
decided — product intent *and* process rulings — and an agent may **never** write it without their
explicit yes on the exact wording. `rationale/<topic>.md` holds what an agent decided (a
tolerance, a scope limit, a format choice), keyed by module, and agents maintain it freely. Both
are revised in place: no supersession, no dated history, git keeps the past. Every entry in both
trees carries `Rejected` (so nobody re-proposes a killed design) and `Refs`.

**This has no `decisions.md` entry, deliberately** — it is the change that abolishes that file.
Its own rulings land in `direction/process.md` at Task 4, before anything is deleted.

**Scale:** 227 ledger entries dispositioned, ~173 files' citations retargeted, 13 topic docs each
gated on a separate confirmation from the owner, `CLAUDE.md` 671 → ~644, resident context 1,063 →
~653. Ten tasks, a gate after each of 3–10.

**Three things a builder must not get wrong.** (1) The `@` import swap happens at the **end of
Task 6**, not in Part A — swapping early leaves every session without the compiled target for the
whole 13-confirmation stretch. (2) **Task 3 writes the link checker**; there is none in the repo,
so until it exists every "verify" in the plan is prose. (3) The inventory numbers are
measurements-at-a-sha and have already drifted once (citers 171→173, 45→46) — **Task 2 re-measures
and its numbers govern.**

**Blocked on:** `profile-generator-fixes` (6 unmerged commits touching five `uedcli/*.py` files
and the inbox, all in Task 8's scope) merging first, or those files being treated as manual-merge
points.

**Partly overtaken:** the link checker of Task 3 now exists (`uedcli/tests/test_doc_links.py`) and
`direction/` + `rationale/` are populated, so Task 2 must re-measure before anything else — the
plan predicted exactly this.
