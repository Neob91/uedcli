# Docs restructure: `direction/` + `rationale/`, no ledger — Implementation Plan

> **For agentic workers:** implement task-by-task; each task ends green + committed. Steps use
> checkbox (`- [ ]`) syntax for tracking. This is a docs change, so "green" means the task's stated
> verification passes — plus `bin/test` from Task 5 onward, where code comments are edited.

**Goal:** Retire the append-only decisions ledger. Replace `dev/docs/decisions.md` (8,985 lines,
227 entries) and `dev/docs/direction.md` (382 lines, derived and drifting) with two **revised-in-place**
per-topic trees, and move three rule sections out of the always-loaded `CLAUDE.md`.

**Architecture:** Two trees split by **who decided**. `direction/<topic>.md` holds Andrzej's
decisions — product intent *and* process rulings — and **may never be written without his explicit
yes**. `rationale/<topic>.md` holds engineering decisions an agent made, keyed by module, and agents
maintain it freely. Both are revised in place: no supersession, no dated history, git keeps the past.
Every entry in both trees carries `Rejected` and `Refs`.

**Tech stack:** Markdown only. No code changes except retargeted comments in `uedctl/*.py`,
`bin/_venv.sh`, `pyproject.toml`. Verification by shell (`grep`/`awk`) + `bin/test`.

**Spec:** [`../specs/2026-07-25-docs-restructure.md`](../specs/2026-07-25-docs-restructure.md).

**Build split:** one gate after each of Tasks 1, 3, 4–6 (per group), 7, 8, 9. Per `CLAUDE.md`
"Review gates"; the whole is far past what one reviewer can read without skimming.

**Not a feature worktree.** This lands incrementally on the checked-out branch. A squash merge
would collapse 13 separate `Andrzej-confirmed:` trailers into one commit message, destroying the
audit trail that is the confirmation rule's only product. Deliberate exception, recorded in the
spec's R8.

**Conventions reminder:** commit only touched files by explicit pathspec (never `git add .`/`-a`);
one short imperative subject; no AI attribution; never rewrite history. Markdown tables pad every
column except the last.

---

## Ordering constraints (why this sequence and no other)

1. **Part 0 before everything.** It carries the confirmation rule, which governs the migration
   itself, and the ledger freeze. Writing a `direction/` topic before the rule exists is the exact
   thing the rule prohibits.
2. **Freeze before inventory.** Every count in the spec is a measurement-at-a-sha. Concurrent
   sessions mint new `decisions.md` refs until the freeze lands, so the inventory is re-run
   immediately after Task 1, not trusted from the spec.
3. **Part A before Part B's citations.** Part A creates `rules/*.md`, which some retargets point at.
4. **Both old files deleted last**, only after all 13 topics are confirmed and Andrzej signs the
   `dropped` list — never partially, so the target never lacks a home.

---

## Task 1: Part 0 — the rule, the two READMEs, the freeze

- [ ] Add a `### Direction docs — NEVER revise without confirmation` section to `CLAUDE.md`, placed
      immediately before `### Documentation`. Text is quoted verbatim in the spec §2. It must state
      that this is a **convention only** — no hook, the trailer is an audit marker — and must name
      `andrzej.md` and `2026-06-20-open-questions-for-andrzej.md` as untouchable.
- [ ] In `CLAUDE.md` "After every change", add the `direction/` carve-out to the *"no doc may be
      left stale"* bullet. Without it the resident rules simultaneously order and forbid the edit.
- [ ] In `CLAUDE.md` "The dev docs split by role", replace the `direction.md` and `decisions.md`
      bullets with `direction/<topic>.md` and `rationale/<topic>.md`, both revised-in-place.
- [ ] In `CLAUDE.md` Documentation, rewrite *"the decision itself goes in the durable, append-only
      `dev/docs/decisions.md`"* → route to the two trees, and state there is no ledger.
- [ ] **Rewrite the pruning rule** in the same section. It currently permits removing only *wholly
      superseded* entries and spike-"gate" notes; Task 7's `dropped` disposition is a third kind and
      is unauthorized until this lands.
- [ ] Create `dev/docs/direction/README.md` — short model statement + a 13-row index, each row
      carrying **migration state** (`(not yet migrated)` → points at `direction.md`). No topic
      content; no `@` import.
- [ ] Create `dev/docs/rationale/README.md` — model, the mandated `Why / Rejected / Refs` shape, and
      the history signpost (`git log --follow -- dev/docs/decisions.md`).
- [ ] Add a `> **FROZEN — DO NOT APPEND**` banner to the top of `dev/docs/decisions.md`.

**Verify:** `CLAUDE.md` contains the rule heading; `grep -rnE '@[A-Za-z0-9._/-]+\.md'
dev/docs/direction/README.md` is empty; both READMEs exist.

**Note:** `CLAUDE.md` grows here (671 → ~715). Task 3 is what reduces it. Do not stop between the
two — mid-sequence the resident context is worse than at the start.

**Commit:** `Add the direction/ confirmation rule and freeze the decisions ledger`
**→ gate.**

---

## Task 2: Re-run the inventory (no commit)

- [ ] Run every command in the spec §5 and record the actual numbers in
      `dev/docs/rationale/MIGRATION.md` under a `## Inventory at <sha>` heading.
- [ ] Diff against the spec's figures. Any drift means a concurrent session added refs after the
      spec was written; the *measured* numbers govern from here, not the spec's.

**Verify:** `MIGRATION.md` exists with an inventory section.

---

## Task 3: Part A — move three rule sections out of `CLAUDE.md`

- [ ] Create `dev/docs/rules/spikes.md` (29 body lines), `tests.md` (21), `background-work.md` (21)
      — verbatim moves, no rewording.
- [ ] Create `dev/docs/rules/README.md` indexing the three.
- [ ] Replace each moved section in `CLAUDE.md` with a router line that **triggers the read at a
      specific moment** and names the file — not a bare pointer. It does not need to carry the
      content; it needs to fire reliably.
- [ ] **Sweep the moved 74 lines for position-relative language**: "above", "below", "this file",
      "two levels up", bold/italic section names, and doc-relative paths (`CLAUDE.md:393` cites
      `unrealed/quirks.md "Stability"`). All become false once the text lives one directory deeper.
- [ ] Replace `@dev/docs/direction.md` at `CLAUDE.md:591` with `@dev/docs/direction/README.md`, and
      give `direction.md` an ordinary (non-`@`) router row so the un-migrated topics stay reachable.
- [ ] Fix `dev/docs/dev-runtime.md`, which still documents the Docker `uedctl-dev` image and
      `bin/_dev-run.sh` (retired 2026-07-14). Until now the correct text was resident and won by
      default; after this move an agent could read the stale one first.

**`worktrees.md` does NOT move.** Its router line cannot carry the `git diff --cached --quiet` check
before `git merge --squash` (a data-loss trap) or "ask before `git branch -D`".

**Verify:** `grep -rnE '@[A-Za-z0-9._/-]+\.md' CLAUDE.md dev/docs/direction/README.md` returns
exactly one line; the position-relative sweep is clean across `CLAUDE.md` and `rules/*.md`;
`wc -l CLAUDE.md` ≈ 644.

**Commit:** `Move the spike, test and background rules to dev/docs/rules/`
**→ gate.**

---

## Tasks 4–6: Part B — 13 `direction/` topics, each confirmed

**Three groups, one gate each.** Group 1 (Task 4): `scope`, `terminology`, `conventions`,
`process`. Group 2 (Task 5): `trunk-and-editor`, `organization`, `materialize`, `safety`,
`generators`. Group 3 (Task 6): `projects-and-config`, `containers`, `packages`, `asset-catalog`.

**Per topic — this loop is the whole task, and it is not optional:**

- [ ] Draft *What we want* from that topic's `direction.md` section(s).
- [ ] Sweep `decisions.md` for that topic's still-relevant **`Rejected`** alternatives, **and any
      live decision `direction.md` never reconciled** — criterion: any entry postdating the newest
      one `direction.md` reconciles (10:18 on 2026-07-25). Do not use a hard-coded list; re-derive.
- [ ] Collect `Refs` (spike/code pointers) from the entries' `**Refs:**` lines.
- [ ] **Put the full proposed text to Andrzej and wait for an explicit yes.** Not a summary — the
      wording that will land. "It follows from what he said" does not satisfy the rule.
- [ ] On his yes, in ONE commit: write `direction/<topic>.md`; delete that section from
      `direction.md`; flip its `direction/README.md` row out of *(not yet migrated)*; retarget that
      topic's citations.
- [ ] Commit trailer: `Andrzej-confirmed: <topic>`.

**`process.md` additionally carries this restructure's own rulings** — the who-decided axis,
`direction/`-only scope, revise-in-place, no hook, deleting the ledger. Otherwise they survive
nowhere: this plan and the spec are both deleted at Task 10.

**Verify per group:** each landed topic has `What we want` + `Rejected` + `Refs`; its `direction.md`
section is gone; its README row is flipped; `git log --grep='Andrzej-confirmed'` shows one commit
per topic.

**→ gate after each group.**

---

## Task 7: Part C — `rationale/` and the disposition table

- [ ] For every `^## \d{4}-` entry in `decisions.md`, add a row to
      `dev/docs/rationale/MIGRATION.md`: `<date> <title> -> direction/<t>.md | rationale/<t>.md |
      superseded-dead | dropped`.
- [ ] `dropped` **and** `superseded-dead` each need a named reason; `superseded-dead` must name the
      superseding entry. Neither is a free bucket.
- [ ] Fold the `rationale`-dispositioned entries into `dev/docs/rationale/<topic>.md` files keyed by
      module/subsystem, each entry in the mandated `Why / Rejected / Refs` shape. The ledger holds
      **83 `**Rejected:**` blocks**; losing them is the failure this tree exists to prevent.
- [ ] Put the `dropped` list to Andrzej for sign-off.

**Verify:** no `^## \d{4}-` entry in `decisions.md` lacks a `MIGRATION.md` row; every
`rationale/*.md` entry has all three parts.

**Commit:** `Populate dev/docs/rationale/ and record every ledger entry's disposition`
**→ gate.**

---

## Task 8: Part D — citation migration

Work the classes in the spec's Part D table, using the Task 2 numbers, not the spec's.

- [ ] `decisions.md` / `direction.md` by name — retarget per each entry's disposition row.
- [ ] The 4 `CLAUDE.md "<moved section>"` code sites → `rules/<file>.md`.
- [ ] Bare dated refs (files with no literal `decisions.md`) → topic path + `#anchor`. **Count these
      in the build**; the spec's range is not authoritative.
- [ ] The 7 `unrealed/*.md` evidence sites → the `spikes/` file, **never** a mutable doc.
- [ ] The 31 `spikes/` files → retarget. Durable evidence, not ephemeral.
- [ ] `specs/`+`plans/` exempt, **except the 13 reachable from `to-build.md`**, which are about to
      be executed.
- [ ] `inbox.md:74-83` and `board/README.md:43` cite sections that now **stay resident** — they need
      *editing*, not retargeting. The inbox item even names `rules/worktrees.md`, which Task 3 does
      not create.

**Verify:** repo-wide link check, prose-citation check, and **anchor-existence** check all clean
(exempting `specs/`+`plans/` save the 13); `bin/test` passes — code comments are in scope, so this
is a `build` row.

**Commit:** `Retarget decisions.md and direction.md citations to the topic trees`
**→ gate.**

---

## Task 9: Parts E + F — forced rule text and three false statements

- [ ] Work the **hand list** in the spec's Part E. The grep is a floor, not the driver — four sites
      (`CLAUDE.md:428`, `:493`, `:496`, `:499`) straddle line breaks and no line-oriented grep finds
      them. Use `rg -U` as an assist only.
- [ ] NOT-trivial list: drop the two deleted docs; add `direction/*`, `rationale/*`, `rules/*`.
- [ ] Sweep the **≥12 internal cross-references**, both directions (resident→moved and
      moved→resident). Do not key on `see **X**` — that form misses six of them.
- [ ] **F1** — `CLAUDE.md:290` claims `.claude/worktrees/` is gitignored; it is not. Add
      `.claude/worktrees/` to `.gitignore` (making the sentence true). **Andrzej's call** — log to
      `board/inbox.md` if he declines.
- [ ] **F2** — rewrite `CLAUDE.md:3-19` to the real layout: toplevel is
      `/home/neob91/Documents/Dev/uedcli`, there is no `Tools/`, `_scratch/` is at that root. Same
      false label at `dev/docs/README.md:45`.
- [ ] **F3** — `CLAUDE.md:293-297` claims a `.claude/settings.json` that does not exist. **Andrzej
      chooses:** create it, or delete the sentence and accept `EnterWorktree` branching from
      `origin/<default>`. Behavioural, not wording.

**Verify:** `git check-ignore .claude/worktrees` exits 0 if F1 was taken; no false statement remains
in resident or moved text.

**Commit:** `Reconcile the rule text and fix three false CLAUDE.md statements`
**→ gate.**

---

## Task 10: Delete the old docs and close out

- [ ] **Andrzej's explicit confirmation** that both files may go — confirming 13 topic docs is not
      the same as confirming nothing else in 227 entries was worth keeping.
- [ ] `git rm dev/docs/direction.md dev/docs/decisions.md`.
- [ ] Record the removal sha in `rationale/README.md`'s history signpost.
- [ ] Update `dev/docs/README.md`: drop both rows, add `direction/`, `rationale/`, `rules/`; fix the
      Context-loading paragraph (only `direction/README.md` is auto-loaded now).
- [ ] Retire the resolved `board/inbox.md` items **by title, not line range** — the concurrency item,
      the `@`-gate item Task 3 overrides, the `[debug]` item Task 9 fixes. Cite titles because
      concurrent sessions append to that file and line numbers drift.
- [ ] Delete this plan and the spec.

**Verify:** neither deleted file is referenced by any tracked file outside `specs/`+`plans/`;
`bin/test` passes; `docs/` still references nothing under `dev/docs/`.

**Commit:** `Delete the decisions ledger and direction.md; the topic trees replace them`
**→ gate.**
