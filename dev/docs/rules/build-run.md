# Running the build queue

Process a set of ready `to-build/` items to completion in one unattended run. This is the loop on
top of the per-item mechanics — [`building-features.md`](building-features.md) (build one item) and
[`worktrees.md`](worktrees.md) (worktree + squash-merge commands). Read both first.

## Before starting — clear the questions up front

The run is unattended, so resolve everything owner-facing before the first build. Confirm each item
is genuinely buildable: a reviewed `plan.md`, every design fork already ruled. An item that still
needs a decision, a spike, or a re-spec is NOT buildable — surface those to the owner now and skip
the item rather than guess mid-run. A one-shot `chore`/`debug` item needs no plan.

## The loop — one item at a time

Serialize the merges: each item lands on fresh `master` before the next starts.

1. Worktree off current `master` (`worktrees.md` §1).
2. Build + verify + one subagent review (`building-features.md`) — one subagent per item.
3. Squash-merge onto fresh `master` and push (`worktrees.md` §4: `pull --ff-only` → `merge
   --squash` → `commit` → `push`), then remove the worktree (§5).

Build subagents may run in parallel across worktrees, but merge them one at a time, in sequence.

## New items arriving mid-run

An item that lands in `to-build/` after the run starts is picked up LAST, after the items already
queued — never ahead of them.

## When an item won't build cleanly

If verification fails or the item hits a documented go/no-go "stop and re-plan" gate: retry once
with a fresh subagent. If it still won't land, write the finding INTO the board item (its
`questions/` if it needs an owner ruling, else a note), leave it in `to-build/`, and continue with
the rest. Do not force it, lower a bar, or merge a partial result.
