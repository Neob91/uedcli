# P2 editing: persistence model, transactions, and whether it shifts direction

## Context

P1 is read-only and needs no answer here. This blocks **P2 (editing)** only — parked so P1 can
proceed.

Three linked decisions:

1. **Human edit persistence.** AI edits hit the trunk instantly (each verb is a discrete mutation).
   For a human dragging/nudging in the GUI, two models were discussed:
   - **instant** — every edit-commit (mouse-up) writes the trunk directly (like the AI); `git
     status` is the "unsaved" layer.
   - **staging + explicit Save** — edits accumulate in a model-side staging snapshot (on disk, not
     the AI-visible trunk); **Save** promotes them into the trunk via the model-side write path.
     Matches the "editors don't persist until you Save" expectation and keeps half-finished human
     fiddling out of the AI's view.

   The owner leaned toward staging+Save earlier but has not ruled.

2. **Atomic chained commands (owner idea).** A uedcli command that runs a set of chained verbs as
   one transaction — all-or-nothing, under one flock hold. Useful for both CLI and GUI. Owner
   principle: **the GUI and CLI must share one concurrency behavior** — the GUI uses the same
   model-side write path + flock, no GUI-specific concurrency. Standing rule stays **flock +
   refuse-same-actor-concurrent-edit** (`safety.md`); no merge UI.

   Open: do we add a transaction verb? What is its shape (stdin list of verbs? a named batch?), and
   how does refuse-on-conflict compose across a chain (roll back the whole chain)?

3. **Does P2 editing shift `direction/trunk-and-editor.md`?** That topic says a level is edited on a
   git feature branch and merged with `git merge`, with no session store. A GUI editing a shared
   checkout live, alongside instant AI writes, is a different working style. If P2 rises to a
   topic-level intent change it needs a `direction/` edit (owner yes + `Confirmed:` trailer); if it
   folds into this item's spec + `rationale/`, it does not. Owner to judge when P2 is picked up.

## Answer

**Decision 1 (human edit persistence): staging + explicit Save.** Ruled 2026-09-14 — edits are
NOT written to the trunk directly; they accumulate in a model-side staging area, and Save is the
only path that promotes them into the trunk via the model-side write path. Decisions 2 and 3 stay
open.
