+++
priority = "p1"
kind = "owner-question"
summary = "Docs restructure: Part A may be a net context LOSS"
+++

# Docs restructure: Part A may be a net context LOSS

Reviewers A+C: the
two biggest sections the spec moves (`review-gates` ~216, `documentation` ~96) are exactly the
ones "After every change" fires on *every* change, so most sessions re-read them as uncached
tool output; and R4 replaces the 382-line direction doc with a pointer to `architecture.md`
(2,157 lines / 189 KB, ~6.5x). Rare-trigger sections only (worktrees/spikes/background/board/
tests = 193 lines) may be the honest scope.
