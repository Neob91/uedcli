+++
priority = "p2"
kind = "chore"
summary = "15 files cite CLAUDE.md sections that moved into dev/docs/rules; only the two in the owner's tree are tracked."
+++

# Sweep the citations of `CLAUDE.md` sections that moved into `dev/docs/rules/`

`CLAUDE.md` was trimmed 689 → 331 lines on 2026-07-27 by moving detail into `dev/docs/rules/`
(`worktrees.md`, `review-gates.md`, `documentation.md`, and the pre-existing `tests.md`,
`spikes.md`, `background-work.md`). The section titles those files replaced no longer exist.

**15 files still cite them by the old title:**

```
git grep -l 'CLAUDE\.md.*"Feature worktrees"\|CLAUDE\.md.*"Review gates"\|CLAUDE\.md.*"Documentation"' \
    -- . ':!dev/docs/rules'
```

Heaviest: `dev/docs/decisions.md` (5 — **FROZEN, do not edit**), `direction/process.md` (2 — the
owner's tree), then board items and specs at 1–2 each.

**Two are already handled and must not be swept blindly:** `direction/process.md`'s two pointers are
board item `direction-process-md-points-at-claude-md`, awaiting an explicit yes; and `decisions.md`
is frozen, so its five stay as historical text.

That leaves **13 files** tracked by nothing. None of them reddens `bin/test` — the citations are
prose, and the doc-link check only follows markdown links and backticked paths into
`direction/`/`rationale/`/`rules/`. A citation naming a section title that no longer exists is
invisible to it, so this rots silently.

Worth deciding while sweeping: whether a citation should name the rules file rather than a
`CLAUDE.md` section at all, since that is what just went stale.
