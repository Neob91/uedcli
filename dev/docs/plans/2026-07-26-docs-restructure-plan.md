# Docs restructure: `direction/` + `rationale/`, no ledger — Implementation Plan

> **For agentic workers:** implement task-by-task; each task ends green + committed. Steps use
> checkbox (`- [ ]`) syntax for tracking. This is a docs change, so "green" means the task's stated
> verification passes — plus `bin/test` from **Task 4** onward, where code comments start being
> retargeted (`uedctl/brushcsg.py:93` is a `conventions`-topic citation, so `.py` files are in scope
> from the first Part B group).

**Goal:** Retire the append-only decisions ledger. Replace `dev/docs/decisions.md` (8,985 lines,
227 entries) and `dev/docs/direction.md` (**392** lines, derived and drifting) with two
**revised-in-place** per-topic trees, and move three rule sections out of the always-loaded
`CLAUDE.md`.

**Architecture:** Two trees split by **who decided**. `direction/<topic>.md` holds Andrzej's
decisions — product intent *and* process rulings — and **may never be written without his explicit
yes**. `rationale/<topic>.md` holds engineering decisions an agent made, keyed by module, and agents
maintain it freely. Both revised in place: no supersession, no dated history, git keeps the past.
Every entry in both trees carries `Rejected` and `Refs`.

**Tech stack:** Markdown only. No behaviour changes; the only code edits are retargeted comments in
`uedctl/*.py`, `bin/_venv.sh`, `pyproject.toml`. Verification by shell (`grep`/`awk`) + `bin/test`.

**Spec:** [`../specs/2026-07-25-docs-restructure.md`](../specs/2026-07-25-docs-restructure.md).

**Build split:** a gate after each of Tasks 1, 3, 4, 5, 6, 7, 8, 9, 10. Per `CLAUDE.md`
"Review gates"; the whole is far past what one reviewer can read without skimming. Task 2 is a
measurement task — it commits, but carries no gate of its own.

**Not a feature worktree.** This lands incrementally on the checked-out branch. A squash merge
collapses 13 separate `Andrzej-confirmed:` trailers into one commit message, destroying the audit
trail that is the confirmation rule's only product. Deliberate exception — and because the spec is
deleted at Task 10, **`direction/process.md` must record it** (Tasks 4–6).

**Conventions reminder:** commit only touched files by explicit pathspec (never `git add .`/`-a`);
one short imperative subject; no AI attribution; never rewrite history. Markdown tables pad every
column except the last.

---

## Ordering constraints (why this sequence and no other)

1. **Part 0 before everything.** It carries the confirmation rule, which governs the migration
   itself, and the ledger freeze. Writing a `direction/` topic before the rule exists is the exact
   thing the rule prohibits.
2. **Freeze before inventory.** Every count is a measurement-at-a-sha. Concurrent sessions mint new
   `decisions.md` refs until the freeze lands, so Task 2 re-measures and its numbers govern.
3. **Part A before Part B's citations.** Part A creates `rules/*.md`, which some retargets point at.
4. **Both old files deleted last**, only after all 13 topics are confirmed and Andrzej signs the
   `dropped` list — never partially, so the target never lacks a home.

### Concurrency — TWO worktrees exist, and one is NOT merged

| Worktree | State |
|-------------------------------|---
| `brush-profile-generators` | content merged at `6900e34`; no hazard |
| **`profile-generator-fixes`** | **5 commits, unmerged**, branched at `6900e34` |

`profile-generator-fixes` touches `dev/docs/board/inbox.md` (−82 lines), `architecture.md`,
`board/done.md`, `docs/leveldesign/*`, `docs/usage.md`, and `uedctl/{cli,dispatch,emit,model}.py`
plus two test files. **Every one of those is also edited by Tasks 8–10.**

- It introduces **no** new `decisions.md`/`direction.md` citations and does not touch
  `direction.md`, so the delete/modify hazard does not fire.
- **Merge it before Task 8**, or treat those four `uedctl/*.py` files and `inbox.md` as manual-merge
  points. Either way the reconciliation is stated, not assumed.
- **Do NOT retire the `board/inbox.md` concurrency item at Task 10** until this is actually true.
  Its text ("land only when no worktree is in flight, or state the manual reconciliation") is
  satisfied by the second clause — but only once this paragraph is the operative record.

---

## Task 1: Part 0 — the rule, the two READMEs, the freeze

- [ ] Add a `### Direction docs — NEVER revise without confirmation` section to `CLAUDE.md`,
      immediately before `### Documentation`. Text is quoted verbatim in the spec §2. It must say
      this is a **convention only** — no hook, the trailer is an audit marker — and must name
      `andrzej.md` and `2026-06-20-open-questions-for-andrzej.md` as untouchable.
- [ ] In "After every change", add the `direction/` carve-out to the *"no doc may be left stale"*
      bullet. Without it the resident rules simultaneously order and forbid the edit.
- [ ] In "The dev docs split by role", replace the `direction.md` and `decisions.md` bullets with
      `direction/<topic>.md` and `rationale/<topic>.md`, both revised-in-place.
- [ ] In Documentation, rewrite *"the decision itself goes in the durable, append-only
      `dev/docs/decisions.md`"* → route to the two trees; state there is no ledger.
- [ ] **Rewrite the pruning rule** in the same section. It currently permits removing only *wholly
      superseded* entries and spike-"gate" notes; Task 7's `dropped` disposition is a third kind and
      is **unauthorized until this lands**.
- [ ] Create `dev/docs/direction/README.md` — short model statement + a 13-row index, each row
      carrying migration state (`(not yet migrated)` → points at `direction.md`). No topic content;
      no `@` import.
- [ ] Create `dev/docs/rationale/README.md` — model, the mandated `Why / Rejected / Refs` shape, and
      the history signpost (`git log --follow -- dev/docs/decisions.md`).
- [ ] Add a `> **FROZEN — DO NOT APPEND**` banner to the top of `dev/docs/decisions.md`.

**Verify — mechanical, one per checkbox:**
```sh
grep -q 'NEVER revise without confirmation' CLAUDE.md          # the rule section
grep -q 'andrzej.md' CLAUDE.md                                 # the untouchables
grep -c 'append-only' CLAUDE.md            # -> 0  (ledger routing rewritten)
grep -c 'wholly.*supersed' CLAUDE.md       # -> 0  (pruning rule rewritten)
grep -q 'FROZEN — DO NOT APPEND' dev/docs/decisions.md
test -f dev/docs/direction/README.md && test -f dev/docs/rationale/README.md
grep -rnE '@[A-Za-z0-9._/-]+\.md' dev/docs/direction/README.md # -> empty
wc -l dev/docs/direction/README.md         # -> <= 25 (index rows only, no topic content)
```

**Note:** `CLAUDE.md` grows here (671 → ~715). Task 3 is what reduces it. Do not stop between the
two — mid-sequence the resident context is worse than at the start.

**Commit:** `Add the direction/ confirmation rule and freeze the decisions ledger` **→ gate.**

---

## Task 2: Re-measure everything Parts C–E depend on

Spec §5's commands cover only part of what later tasks consume. Measure **all** of it and record it
in `dev/docs/rationale/MIGRATION.md` under `## Inventory at <sha>`:

- [ ] Spec §5's commands (`CLAUDE.md`/`direction.md` line counts, the two citer counts, entry count,
      `Rejected` count, spikes count, section sizes).
- [ ] The `CLAUDE.md "<moved section>"` code sites — spec says 4; confirm no fifth.
- [ ] The `unrealed/*.md` **evidence** sites — spec says 7; **it is 6** (`package-format.md:65,88,184`,
      `rendering.md:127`, `quirks.md:262,443`). `commands.md:212` is a bare dated ref, counted in the
      next row.
- [ ] The bare-dated-ref files (no literal `decisions.md`) — spec's "~17–19" is a range, not a number.
- [ ] `specs/`+`plans/` citer counts and directory sizes — `plans/` holds **24** files, not 23.
- [ ] **Files linked directly from `to-build.md`** — spec says 13; **it is 11**. "Reachable" means
      *linked directly from `to-build.md`*, not transitively. This is an **exemption boundary**, so a
      wrong number means files are checked or skipped incorrectly.

**Verify:** `MIGRATION.md` has an `## Inventory at <sha>` section with a number for every row above.
Any drift from the spec means a concurrent session moved something; **the measured numbers govern
from here, not the spec's.**

**Commit:** `Record the docs-restructure inventory` *(no gate — measurement only)*

---

## Task 3: Part A — move three rule sections out of `CLAUDE.md`

- [ ] Create `dev/docs/rules/spikes.md` (29 body lines), `tests.md` (21), `background-work.md` (21)
      — verbatim moves, no rewording.
- [ ] Create `dev/docs/rules/README.md` indexing the three.
- [ ] **Router lines fold into the existing `### UnrealEd navigation — docs are READ-ON-DEMAND`
      bullet list** (`CLAUDE.md:591-599`) — that is already the established router; do not leave
      three orphan `###` stubs. Each line triggers the read at a specific moment and names the file.
      It need not carry the content; it must fire reliably.
- [ ] **Sweep the moved 74 lines for position-relative language**: "above", "below", "this file",
      "two levels up", bold/italic section names, and doc-relative paths (`CLAUDE.md:393` cites
      `unrealed/quirks.md "Stability"`). All become false one directory deeper.
- [ ] Replace `@dev/docs/direction.md` with `@dev/docs/direction/README.md`, and give `direction.md`
      an ordinary (non-`@`) router row so un-migrated topics stay reachable.
- [ ] Fix `dev/docs/dev-runtime.md`, which still documents the Docker `uedctl-dev` image and
      `bin/_dev-run.sh` (retired 2026-07-14). Until now the correct text was resident and won by
      default; after this move an agent could read the stale one first.

**`worktrees.md` does NOT move.** Its router line cannot carry the `git diff --cached --quiet` check
before `git merge --squash` (a data-loss trap) or "ask before `git branch -D`".

**Verify:** `grep -rnE '@[A-Za-z0-9._/-]+\.md' CLAUDE.md dev/docs/direction/README.md` → exactly one
line; position-relative sweep clean across `CLAUDE.md` **and** `dev/docs/rules/*.md`;
`wc -l CLAUDE.md` ≈ 644; `wc -l dev/docs/direction/README.md` ≤ 25.

**Commit:** `Move the spike, test and background rules to dev/docs/rules/` **→ gate.**

---

## Tasks 4–6: Part B — 13 `direction/` topics, each confirmed

### The section → topic map (all 16 sections claimed, exactly once)

| `direction.md` section | → topic |
|-------------------------------------------------|---
| `:1-22` **preamble** (three-doc lane table + maintenance rule) | `process.md` |
| `:23` Scope: a generic UnrealEngine-1 tool | `scope.md` |
| `:31` Projects, substrates, and the global CLI | `projects-and-config.md` |
| `:87` The T3D trunk is the source of truth | `trunk-and-editor.md` |
| `:114` The trunk: a git-committed T3D tree | `trunk-and-editor.md` |
| `:139` Terminology | `terminology.md` |
| `:160` Folders: hierarchical actor organization | `organization.md` |
| `:174` Labels: flat, multi-valued classification | `organization.md` |
| `:191` Materializing the map file | `materialize.md` |
| `:247` Lighting, BSP and runtime state are build output | `materialize.md` |
| `:224` Safety: never irretrievably clobber | `safety.md` |
| `:263` Container isolation / substrate split | `containers.md` |
| `:272` Generator pattern | `generators.md` |
| `:301` One package-format core | `packages.md` |
| `:319` The asset catalog | `asset-catalog.md` |
| `:348` No back-compat cruft | `conventions.md` |
| `:365` Explicit, discoverable, model-side | `conventions.md` |

Line numbers are as of `10ef91e`; match on **heading text**, not position.

**Groups, one gate each.** Task 4: `scope`, `terminology`, `conventions`, `process`.
Task 5: `trunk-and-editor`, `organization`, `materialize`, `safety`, `generators`.
Task 6: `projects-and-config`, `containers`, `packages`, `asset-catalog`.

### Per topic — this loop is the task, and none of it is optional

- [ ] Draft *What we want* from that topic's section(s) per the map above.
- [ ] Sweep `decisions.md` for that topic's still-relevant **`Rejected`** alternatives, **and any
      live decision `direction.md` never reconciled** — criterion: any entry postdating the newest
      one `direction.md` reconciles. Re-derive it; do not use a hard-coded list.
- [ ] Collect `Refs` from those entries' `**Refs:**` lines.
- [ ] **Put the full proposed text to Andrzej and wait for an explicit yes.** Not a summary — the
      wording that will land. "It follows from what he said" does not satisfy the rule.
- [ ] On his yes, in ONE commit: write `direction/<topic>.md`; delete its section(s) from
      `direction.md`; flip its `direction/README.md` row; retarget that topic's citations; **and
      append a `direction/<topic>.md` disposition row to `MIGRATION.md` for every ledger entry
      consumed** — otherwise Task 7 must reconstruct them by re-reading 13 commits against 227
      entries.
- [ ] Commit trailer: `Andrzej-confirmed: <topic>`.

**`process.md` additionally carries this restructure's own rulings** — the who-decided axis,
`direction/`-only scope, revise-in-place, no hook, deleting the ledger, **and that this work ran
outside a feature worktree and why**. Otherwise they survive nowhere: spec and plan are both deleted
at Task 10.

**Verify per group:** each landed topic has `What we want` + `Rejected` + `Refs`; its `direction.md`
section is gone; its README row is flipped; `wc -l dev/docs/direction/README.md` still ≤ 25;
`git log --grep='Andrzej-confirmed'` shows one commit per topic; every consumed entry has a
`MIGRATION.md` row.

**Coverage gate, at Task 6:** every `^## ` heading in `direction.md` has been claimed by exactly one
topic, and the preamble's lane model is in `process.md`. Nothing may reach Task 10 unread.

---

## Task 7: Part C — `rationale/` and the rest of the disposition table

- [ ] For every remaining `^## \d{4}-` entry in `decisions.md` (Tasks 4–6 already filed theirs), add
      a `MIGRATION.md` row: `<date> <title> -> direction/<t>.md | rationale/<t>.md |
      superseded-dead | dropped`.
- [ ] `dropped` **and** `superseded-dead` each need a named reason; `superseded-dead` must name the
      superseding entry. Neither is a free bucket.
- [ ] Fold `rationale`-dispositioned entries into `dev/docs/rationale/<topic>.md` keyed by
      module/subsystem, each in the mandated `Why / Rejected / Refs` shape. The ledger holds **83
      `**Rejected:**` blocks**; losing them is the failure this tree exists to prevent.
- [ ] Put the `dropped` list to Andrzej for sign-off.

**Verify:** no `^## \d{4}-` entry lacks a `MIGRATION.md` row; every `rationale/*.md` entry has all
three parts; `bin/test` passes.

**Commit:** `Populate dev/docs/rationale/ and record every ledger entry's disposition` **→ gate.**

---

## Task 8: Part D — citation migration

Use **Task 2's** numbers, not the spec's.

- [ ] `decisions.md` / `direction.md` by name — retarget per each entry's disposition row.
- [ ] The 4 `CLAUDE.md "<moved section>"` code sites → `rules/<file>.md`.
- [ ] Bare dated refs → topic path + `#anchor`.
- [ ] The `unrealed/*.md` evidence sites → the `spikes/` file, **never** a mutable doc.
- [ ] The 31 `spikes/` files → retarget. Durable evidence, not ephemeral.
- [ ] `specs/`+`plans/` exempt, **except the 11 linked directly from `to-build.md`**.
- [ ] Two board sites cite sections that now **stay resident** — they need *editing*, not
      retargeting. Cite them **by item title, not line range** (`inbox.md` is 2,786 lines and the
      in-flight branch deletes 82 of them): the `[debug]` item about the repo layout and
      `.claude/settings.json`, and `board/README.md`'s "a spike happens when a spec flags a live
      unknown".

**Verify:** repo-wide link, prose-citation, and **anchor-existence** checks clean (exempting
`specs/`+`plans/` save the 11); `bin/test` passes.

**Commit:** `Retarget decisions.md and direction.md citations to the topic trees` **→ gate.**

---

## Task 9: Parts E + F — forced rule text and three false statements

**Match on quoted text, not line numbers** — Tasks 1 and 3 shift every line in `CLAUDE.md`, and the
four hardest sites straddle line breaks so no line-oriented grep finds them:

| Must-fix site | Match on |
|--------------------|---
| bare dated ref | `"decision 2026-07-24 21:58"` |
| lane prose | `"architecture, direction, decisions, spikes, board"` |
| user-doc prose | `"decisions, architecture, etc."` |
| dev-doc prose | `"spikes/decisions/each other"` |

Plus every `decisions.md`/`direction.md` mention a plain grep *does* find. Final check:
`grep -c 'decisions\.md\|direction\.md' CLAUDE.md` → **0**.

- [ ] NOT-trivial list: drop the two deleted docs; add `direction/*`, `rationale/*`, `rules/*`.
- [ ] Sweep the **≥12 internal cross-references**, both directions. Do not key on `see **X**` — that
      form misses six of them.
- [ ] **F1** — `CLAUDE.md` claims `.claude/worktrees/` is gitignored; it is not. Add
      `.claude/worktrees/` to `.gitignore` (making the sentence true). **Andrzej's call** — log to
      `board/inbox.md` if he declines.
- [ ] **F2** — rewrite the repo-layout paragraph: toplevel is `/home/neob91/Documents/Dev/uedcli`,
      there is no `Tools/`, `_scratch/` is at that root. Same false label in `dev/docs/README.md`.
- [ ] **F3** — the `.claude/settings.json` claim references a file that does not exist. **Andrzej
      chooses:** create it, or delete the sentence and accept `EnterWorktree` branching from
      `origin/<default>`. Behavioural, not wording.

**`dev/docs/README.md` belongs to Task 10, not here** — Task 10 deletes the very rows this task
would reword. Leave it alone.

**Verify:** `grep -c 'decisions\.md\|direction\.md' CLAUDE.md` → 0; `git check-ignore
.claude/worktrees` exits 0 if F1 was taken; `bin/test` passes.

**Commit:** `Reconcile the rule text and fix three false CLAUDE.md statements` **→ gate.**

---

## Task 10: Delete the old docs and close out

- [ ] **Andrzej's explicit confirmation** that both files may go — confirming 13 topic docs is not
      the same as confirming nothing else in 227 entries was worth keeping.
- [ ] `git rm dev/docs/direction.md dev/docs/decisions.md`.
- [ ] Record the removal sha in `rationale/README.md`'s history signpost.
- [ ] **`dev/docs/README.md`, entirely** — drop both rows; add `direction/`, `rationale/`, `rules/`;
      fix the "A gap between `direction.md` and `architecture.md`" paragraph, the Context-loading
      paragraph (only `direction/README.md` is auto-loaded now), the "See `direction.md` + the board"
      line, and the `Tools/uedctl/CLAUDE.md` label.
- [ ] Retire the resolved `board/inbox.md` items **by title, not line range** — the `@`-gate item
      Task 3 overrides, the `[debug]` item Task 9 fixes. **Not** the concurrency item unless the
      second worktree has actually merged.
- [ ] **Delete this plan's entry from `board/to-build.md`** — that file's own rule.
- [ ] **Add the short `done.md` tail entry** — `CLAUDE.md` "TODOs".
- [ ] Delete this plan and the spec.

**Verify:** neither deleted file is referenced by any tracked file outside `specs/`+`plans/`;
`bin/test` passes; `docs/` still references nothing under `dev/docs/`; `to-build.md` has no
docs-restructure entry.

**Commit:** `Delete the decisions ledger and direction.md; the topic trees replace them` **→ gate.**
