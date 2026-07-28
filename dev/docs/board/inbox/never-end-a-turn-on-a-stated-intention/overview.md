+++
priority = "p2"
kind = "owner-question"
summary = "Proposed CLAUDE.md rule: a turn ends on a result, a blocker or a question — never on an announced next step."
+++

# [OWNER — confirm] Never end a turn on a stated intention

The owner raised this on 2026-07-27 after work stalled twice while they were away. Both times the
agent wrote "starting that now" or "dispatching this now" and then **ended the turn without doing
it**. Announcing an intention reads like progress and is not: the work waits for the owner to come
back and say "go", which is the opposite of what they asked for.

`CLAUDE.md` already says **"Report the OUTCOME, not the intent"** — but only inside the review-gate
rules, about rounds. The same failure happens in ordinary work and nothing there forbids it.

**Proposed, awaiting a yes. Suggested home: `dev/docs/rules/` (it is operative procedure), with a
router line in `CLAUDE.md`:**

> **NEVER END A TURN ON A STATED INTENTION.** If the next action is known, take it — the tool call
> IS the report. A turn ends on a **result**, a **genuine blocker**, or a **question only the owner
> can answer**; never on "next I will…", "starting now", or "standing by to". This is the same rule
> as *report the outcome, not the intent*, applied to all work rather than to review rounds alone.
>
> **Long or multi-step work runs in a subagent briefed to completion**, not across a sequence of the
> main agent's turns. Each turn boundary is a place the work can stall waiting for the owner; a
> subagent has no such boundary. Brief it with the whole job, tell it to park blockers as board
> items and keep going, and let it report once at the end.

**Why the second half matters as much as the first:** the fix is not only "be more disciplined". A
turn boundary is a structural stall point. Handing a long job to a subagent removes the boundary
rather than relying on the agent to remember not to stop at it.

Say the word if you would rather this stayed a one-line addition to the existing review-gate
sentence instead of its own rule.
