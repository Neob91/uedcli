# Spec — docs restructure: a mutable `direction/` tree, on-demand rules, no ledger

**Status:** v2, rewritten after round 1 returned a structural finding. Awaiting spec-gate review.
**Supersedes:** v1 of this file (git `cf21f54`), which proposed folding `direction.md` away and
keeping `decisions.md` as a pruned/sharded ledger. Round 1 (3 cold Opus, 2026-07-25) parked it.

---

## 1. What round 1 killed, and what replaced it

v1 proposed: split `CLAUDE.md` into on-demand rules, delete `direction.md` by folding its sections
into `architecture.md`, and keep `decisions.md` as an append-only ledger, pruned and sharded.

Two of three reviewers raised the same **structural** finding: `direction.md`'s own preamble states
it is written *"in the present tense even where the code doesn't match yet"*, so its sections are
not sortable into built/unbuilt at section granularity, and folding them into `architecture.md`
("what IS … never stale") would make that doc stale on the day it landed. Downstream of that,
deleting the doc removed the **"want" lane** from the three-lane model with nothing inheriting it.

Andrzej's resolution is a shape v1 never considered: **abolish the ledger model entirely and
replace both docs with a mutable, topic-sharded `direction/` tree.**

| | Old model | New model |
|-----------------|-------------------------------------------|---
| `direction.md` | one file, derived from the ledger, hand-reconciled | **gone** |
| `decisions.md` | 227 append-only entries, never reworded | **gone** |
| replacement | — | `dev/docs/direction/<topic>.md` — **revised in place**, no history, no supersession, no timestamps |

Git keeps the history. The docs keep the *current* answer.

**Why this dissolves v1's problems rather than solving them:** there is no never-reword rule to
collide with, so the ~410 relative paths and the 39 in-ledger `direction.md` references stop being
obstructions. There is no shard-axis question, because topic *is* the axis. There is no "want lane"
gap, because the tree is the want lane. And the doc stops being derived — with no ledger upstream,
`direction/` is a primary statement of intent, which was v1's actual complaint about `direction.md`.

## 2. The compensating control (this is the load-bearing part)

The append-only ledger had one safety property that was never its stated purpose: **immutability
made unauthorized rewriting structurally impossible.** An agent could only append. A mutable
`direction/` tree removes that, and would otherwise hand every agent write access to the statement
of Andrzej's intent — where a wrong edit is caught by nobody, because there is no code or editor to
contradict it.

So the rule below is not documentation hygiene bolted on afterwards; it is the control that
replaces immutability, and **it lands before any `direction/` content exists.**

```markdown
### Direction docs — NEVER revise without confirmation

`dev/docs/direction/<topic>.md` states what Andrzej wants. Unlike every
other doc it is MUTABLE — revised in place to match current intent, with
no history, no supersession, no timestamps (git keeps history).

That mutability is exactly why it is the ONE tree an agent may never
write unilaterally:

- **NEVER create, revise, reword, or delete anything under
  `dev/docs/direction/` — including a single `Rejected` bullet — without
  asking Andrzej and getting an explicit yes.** Propose the exact text
  and wait for confirmation. "It follows from what he said" does NOT
  satisfy this; he confirms the wording that actually lands.
- **When direction looks stale, ASK — never edit.** If the work suggests
  a direction doc no longer matches intent, surface it as a question.
- **Confirm proactively.** When working in a topic, ask whether its
  direction doc is still current rather than assuming it is.

Every other doc under `dev/docs/` an agent maintains on its own.
This tree it does not.
```

**Scope: `direction/` only** (Andrzej, 2026-07-25). `architecture.md`, `unrealed/*`, `spikes/`,
`board/`, `rules/` and `docs/` stay agent-maintained — they record facts, and a wrong fact is
contradicted by the code or the editor. A wrong statement of intent is contradicted by nothing.

## 3. Design

### Part 0 — the confirmation rule lands first

`rules/documentation.md` (or resident `CLAUDE.md`, per Part A) gains the rule above, and
`dev/docs/direction/README.md` states the model: mutable, topic-sharded, no history, confirmation
required. **No `direction/<topic>.md` is written before this is committed.** It governs the
migration itself, not just later edits.

### Part A — move only the rare-trigger rules out of `CLAUDE.md`

v1 moved 551 lines. Reviewers A and C both found that this is plausibly a **net context loss**: the
two largest sections it moved (`review-gates` ~216, `documentation` ~96) are precisely the ones
`CLAUDE.md` "After every change" fires on *every* change, so most sessions would re-read them as
uncached tool output instead of reading them as a cached prefix. Andrzej's call: move only the
sections whose trigger is genuinely rare.

**Moves to `dev/docs/rules/` (193 lines):**

| New file | From | Lines | Trigger |
|-------------------------|--------------------------|-------|---
| `worktrees.md` | Feature worktrees | 84 | starting a feature |
| `board.md` | TODOs / board | 38 | touching the backlog |
| `spikes.md` | Spikes | 29 | running a spike |
| `tests.md` | Tests | 21 | running tests |
| `background-work.md` | Background / long-running | 21 | starting a background job |

**Stays resident:** Review gates (216), Documentation (96), Code & CLI conventions (63), UnrealEd
navigation (31), repo-this-lives-in (22), Commits (16), After every change (14).

Router lines carry the load-bearing fact, not just a pointer — `Run tests via bin/test, never
pytest directly → dev/docs/rules/tests.md`, so an agent that never opens the file still gets the
part that matters.

**Router lines are plain backticked paths, NEVER `@` imports.** `direction.md` is auto-loaded today
solely because `CLAUDE.md:591` writes it `@dev/docs/direction.md`. One `@dev/docs/rules/…` row
silently negates the entire saving while the file still looks correct. Gated: `grep -n '@dev/docs/'
CLAUDE.md` must return empty.

### Part B — replace both docs with `direction/`, one topic at a time

Eleven topics, seeded from `direction.md`'s 16 sections:

| `direction/<topic>.md` | Seeded from |
|--------------------------|---
| `scope.md` | Scope: a generic UE1 tool |
| `projects-and-config.md` | Projects, substrates, and the global CLI |
| `trunk-and-editor.md` | T3D trunk is source of truth + the git-committed T3D tree |
| `organization.md` | Folders + Labels |
| `materialize.md` | `level materialize` + lighting/BSP as build output |
| `safety.md` | Safety: never irretrievably clobber |
| `containers.md` | Container isolation / code-content substrate split |
| `generators.md` | Generator pattern |
| `packages.md` | One package-format core |
| `asset-catalog.md` | The asset catalog |
| `terminology.md` | Terminology |
| *(not a direction topic)* | No back-compat cruft + Explicit/discoverable/model-side → `CLAUDE.md` "Code & CLI conventions" (stays resident per Part A) |

**Each topic doc has two sections:** *What we want*, and *Rejected* — what we deliberately are not
doing and why. `Rejected` is forward-looking (it stops a future session re-proposing a killed
design), which is why it survives a model that drops history. It is revised in place like
everything else: when something stops being rejected, the bullet is edited or deleted.

**The migration is an interview, not a distillation.** Per Part 0, every topic doc's content needs
Andrzej's explicit confirmation. For each topic, in order:

1. Draft *What we want* from that topic's `direction.md` section(s).
2. Sweep `decisions.md` for that topic's still-relevant **rejected alternatives** and draft the
   `Rejected` bullets. (Only rejected alternatives are harvested — decision *history* is not.)
3. Put both to Andrzej for confirmation, as text, and wait.
4. Write only what he confirms; commit.

`direction.md` and `decisions.md` are deleted only after **all eleven** topics are confirmed —
never partially, so the tree is never in a state where the target has no home.

### Part C — citation migration

Both deleted files are heavily cited. Corrected counts (v1's were wrong by ~4x; re-verified
2026-07-25, repo-wide, excluding `.git/` and `.claude/worktrees/`):

| Cited file | Citing files | Composition |
|-----------------|--------------|---
| `decisions.md` | **171** | 122 `.md`, **45 `.py`**, 3 `.sh`, `pyproject.toml` |
| `direction.md` | **45** | 40 `.md`, **5 `.py`** |

Policy per class:

- **Code comments** (`uedctl/*.py`, `bin/_venv.sh`, `pyproject.toml`, spike harnesses) — retargeted.
  `CLAUDE.md` requires findings to be back-referenced from code comments, so these are load-bearing
  by house rule, not incidental. **This is what makes the batch a `build` row, not docs-only, and
  `bin/test` must run.**
- **Durable dev docs** (`architecture.md` alone cites `decisions.md` 46 times, plus `spikes/`,
  `board/`, `unrealed/`) — retargeted to the owning `direction/<topic>.md` or rules file.
- **Ephemeral `specs/` + `plans/`** (62 + 18 files) — **not** retargeted. They are deleted when
  their work lands; rewriting them is churn with a short half-life. Stated explicitly so the link
  check can exempt them.

### Part D — rule text the restructure forces

v1 claimed "relocation, not a rewrite" and all three reviewers falsified it. Enumerated here so
each is reviewed now rather than improvised at build time:

- `CLAUDE.md` "The dev docs split by role" — the three-lane `direction.md`/`decisions.md`/
  `architecture.md` description and the "reconcile `direction.md`" maintenance rule are replaced by
  the `direction/` model.
- `CLAUDE.md` NOT-trivial list — drops `dev/docs/direction.md`/`decisions.md`, gains
  `dev/docs/direction/*.md` and **`dev/docs/rules/*.md`**. Without the latter, a one-line edit to a
  relocated rule becomes classifiable as trivial — an observable weakening of the gate caused by
  the move itself.
- `CLAUDE.md` "record every decision I make … in the durable, append-only `decisions.md`" — replaced
  by the confirmation rule; there is no append-only ledger to record into.
- `CLAUDE.md` "Never point a durable doc at a spec for the rationale and rejected alternatives;
  point it at a `decisions.md` entry" — retargeted to `direction/<topic>.md` "Rejected".
- `CLAUDE.md` internal `see **X** below/above` cross-references at 8 sites, wherever the target
  section moved out.
- `dev/docs/README.md` — **five** `direction.md` sites (the table row, the is/want gap paragraph
  ×2, the Context-loading paragraph, and "See `direction.md` + the board"), plus a new `rules/` row
  and a new `direction/` row. That table is authoritative on which doc owns what.

## 4. Risks

| # | Risk | Mitigation |
|----|---------------------------------------------------------|---
| R1 | **A mutable direction tree is silently rewritable** — the exact protection the append-only ledger provided for free | Part 0's confirmation rule, landed **before** any `direction/` content exists. This is the whole reason Part 0 is first |
| R2 | Migration drops a live decision that `direction.md` never reconciled (its reconcile rule was known to lag) | The `decisions.md` sweep in Part B step 2 is per-topic and reviewed by Andrzej; the ledger is deleted only after all 11 topics are confirmed |
| R3 | 171 + 45 citing files leave dangling references | Link check **repo-wide** — `uedctl/`, `bin/`, `pyproject.toml`, `pytest.ini`, not just the doc trees. Plus a string check, because the dominant citation form is prose (`` `CLAUDE.md` "Review gates" ``) which a link checker passes silently |
| R4 | A live worktree (`brush-profile-generators`) holds the pre-restructure tree; git cannot auto-merge an append into a deleted file | Land only when no worktree is in flight, or reconcile by hand and say so in the commit message |
| R5 | Part A's saving evaporates via an `@` import | Gated: `grep -n '@dev/docs/' CLAUDE.md` empty |
| R6 | Confirmation traffic makes the migration slow enough to stall half-done | Topics are independent and committed individually; a stalled migration leaves confirmed topics landed and both old files still present, which is a valid resting state |

## 5. Verification

- **Repo-wide link check** — no reference in any tracked file resolves to a missing file.
- **Prose-citation check** — no file cites `` `CLAUDE.md` "<moved section>" ``, `direction.md`, or
  `decisions.md` outside the exempted ephemeral `specs/`+`plans/`.
- **`bin/test` passes** — code comments are in scope, so this is a build row.
- **`grep -n '@dev/docs/' CLAUDE.md`** returns empty.
- **No `see **X**` in `CLAUDE.md`** points at a section it no longer holds.
- **Topic coverage** — all 16 `direction.md` sections are accounted for by the Part-B table, and
  both old files are deleted only after all 11 topics are confirmed and committed.
- **`docs/` house rule** — no user-facing doc references `dev/docs/`. Currently clean; keep it.

## 6. Out of scope — log to `board/inbox.md`

- **`CLAUDE.md` "The repo this tool lives in" is factually wrong in this checkout** — it says
  uedctl lives at `Tools/uedctl/` inside `dx_lum` with `_scratch/` "two levels up"; the git toplevel
  is `/home/neob91/Documents/Dev/uedcli` and there is no `Tools/`. Part A keeps this section
  resident, so the error stays in the most privileged position in every session's context.
- **`CLAUDE.md` "Feature worktrees" asserts this repo's `.claude/settings.json` sets
  `worktree.baseRef: "head"`** — that file does not exist. Part A moves this text into
  `rules/worktrees.md`, where it would be equally wrong.
- **`Tools/uplayctl/CLAUDE.md`** mirrors these rules by hand and is in a **different repository** —
  this restructure silently desynchronises it.
- `dev/docs/README.md`'s table already omits ~8 docs; `board/inbox.md` (2,602 lines) and
  `board/done.md` (1,125) are unpruned.

## 7. Sequencing

Per `CLAUDE.md`, specced pipeline work takes a **plan round** — v1 skipped it and reviewer C caught
that. This spec is gated, then a plan doc is written and gated, then the parts are built.

1. This spec → **spec gate**.
2. **Plan doc** → plan gate.
3. Part 0 (confirmation rule + `direction/README.md`) → build gate. **Nothing under `direction/`
   is written before this lands.**
4. Part A (rules split, 193 lines) → build gate.
5. Part B, topic by topic, each confirmed by Andrzej before it is written.
6. Part C + D (citations, forced rule text), then delete `direction.md` + `decisions.md`.
7. Update `dev/docs/README.md`; log §6 items to `board/inbox.md`; delete this spec.
