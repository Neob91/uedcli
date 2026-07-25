# Spec — docs restructure: on-demand rules, `direction.md` removal, `decisions.md` prune + shard

**Status:** drafted, awaiting spec-gate review (`CLAUDE.md` "Review gates")
**Author:** agent session, 2026-07-25, on Andrzej's decisions recorded below
**Ledger:** the decisions below MUST land in `decisions.md` before this work is declared done —
this spec is ephemeral and must not be the only record (`CLAUDE.md` "Documentation")

---

## 1. Problem

Two documents are injected into **every** uedctl agent session before any work starts:

| Doc | Lines | Bytes | Approx tokens | How it is loaded |
|-----------------|-------|--------|---------------|---
| `CLAUDE.md` | 671 | 40 KB | ~10k | project instruction file |
| `direction.md` | 382 | 29 KB | ~7k | the literal `@dev/docs/direction.md` import in `CLAUDE.md` "UnrealEd navigation"

That is **~17k tokens of always-on context**, and it grows every time a rule is clarified. Three
separate problems hide inside it:

1. **Most of `CLAUDE.md` is procedure, not trigger.** A session needs to *know a review gate
   exists*; it does not need the 224 lines of gate rationale resident until it is actually
   running one. Same for worktrees, spikes, board flow, test invocation.
2. **`direction.md` is a derived doc.** It is defined as "synthesized from `decisions.md`", which
   makes it a second copy of the truth plus a standing reconciliation chore that `CLAUDE.md` has
   to spend a maintenance rule policing. A derived doc that must be hand-reconciled is a doc that
   is periodically wrong.
3. **`decisions.md` has never been pruned.** 8,985 lines / 694 KB / **229 entries**, with 135
   supersession mentions — despite its own preamble permitting two classes of pruning since it
   was created. It is the largest file in the tree by a factor of three.

**Measured facts this spec depends on** (gathered 2026-07-25, re-verify before building):

- `CLAUDE.md` section sizes: Review gates 224, Documentation 96, Feature worktrees 84, Code & CLI
  conventions 63, TODOs/board 38, UnrealEd navigation 31, Spikes 29, repo-this-lives-in 22,
  Tests 21, Background work 21, Commits 16, After every change 14.
- `decisions.md` is cited by **120 files**, led by `architecture.md` (46 citations),
  `board/inbox.md` (32), `board/done.md` (27).
- `direction.md` is cited by 10 files outside itself, led by `decisions.md` (39 citations).
- **`decisions.md` is NOT auto-loaded** — it has never cost a single context token. Its cost is
  navigation and maintenance only.

## 2. Andrzej's decisions

Recorded as made, per `CLAUDE.md` ("record every decision I make — the choice, the alternatives
rejected, and the reason"). Each becomes a `decisions.md` entry.

### D1 — `CLAUDE.md`'s rules split into `dev/docs/rules/`, loaded on demand

The agent decides when to load a rule; `CLAUDE.md` retains only triggers and pointers.

- **Rejected:** leaving `CLAUDE.md` monolithic. It is simple and self-enforcing, but it taxes
  every session for rules most sessions never exercise.

### D2 — Review gates: the **trigger only** stays resident

`CLAUDE.md` keeps ~8 lines: that every change gets reviewed, that nothing ships unlooked-at, the
pointer to `rules/review-gates.md`, and the never-restate-the-counts prohibition. The tier table,
reviewer counts, context-vs-priming rule, round-2 trigger, disposition rule and structural-escalation
rule all move.

- **Rejected:** keeping the tier table resident (~40 lines) so a session can classify a change
  without a read — the agent's own recommendation. Andrzej chose maximum extraction; the table
  is the bulkiest resident candidate and a session that is about to review can afford one `Read`.
- **Consequence, stated plainly:** a session must `Read` `rules/review-gates.md` before it can
  tell a trivial change from a build one. See risk R1.

### D3 — `direction.md` is REMOVED, its live content folded into other docs

- **Rejected:** keeping it auto-loaded (it is the single largest always-on cost after `CLAUDE.md`,
  and it is derived). **Rejected:** merely dropping the `@` to make it read-on-demand — that
  leaves the reconciliation chore and the duplicate-truth problem untouched.

### D4 — `decisions.md` is KEPT, pruned and sharded — not deleted

- **Rejected:** deleting it and folding each live decision's rationale into the topic doc it
  governs (Andrzej's initial instinct). Reversed on two findings surfaced during speccing:
  (a) 120 files cite it, so folding converts the evidence graph into dangling references or
  forces a 120-file rewrite; (b) **nothing else in the tree has a home for rejected
  alternatives** — `architecture.md` is "what IS", `unrealed/*` is "what the engine does", and
  `CLAUDE.md` explicitly forbids parking rationale in ephemeral specs. Deleting it would let a
  future agent re-propose an already-killed design. Git history is not adequate preservation:
  nobody greps deleted files.
- **Rejected:** pruning only, leaving one file (zero citation churn, but still a 9k-line file).

### D5 — Spec first, gated, then build

This work touches 120+ files; a structural mistake is expensive to undo. It gets the **spec**
moment — the one round that still opens wide.

## 3. Design

### Part A — `CLAUDE.md` → `dev/docs/rules/`

**The cut rule.** Not section-by-section — *within* each section:

> **The trigger and the single most load-bearing fact stay resident. The procedure and the
> rationale move out.**

A router line must carry the fact, not just the pointer. `Run tests via bin/test, never pytest
directly — full rules: dev/docs/rules/tests.md` survives an agent that never opens the file;
`see rules/tests.md` does not.

**Stays resident** (target: ~120 lines total):

| Section | Lines | Why it cannot move |
|-------------------------------|-------|---
| The repo this tool lives in | 22 | The `_scratch/` rule fires on *any* temp file in *any* session — the trigger is unpredictable, so a router line would have to be as long as the rule |
| After every change | 14 | This section *is* the master router; everything else hangs off it |
| Commits | 16 | Fires on every single change; cheaper to keep resident than to page in each time |
| UnrealEd navigation | 31 | Already a router — it becomes the model for, and absorbs, the new `rules/` rows |
| Review gates (trigger only) | ~8 | Per D2 |

**Moves to `dev/docs/rules/`:**

| New file | From | Lines | Router trigger in `CLAUDE.md` |
|--------------------------|--------------------------|-------|---
| `review-gates.md` | Review gates (body) | ~216 | before declaring any work done |
| `documentation.md` | Documentation | 96 | before writing or updating any doc |
| `worktrees.md` | Feature worktrees | 84 | before starting a feature |
| `code-cli-conventions.md` | Code & CLI conventions | 63 | before changing uedctl code or adding a verb |
| `board.md` | TODOs / board | 38 | before touching the backlog |
| `spikes.md` | Spikes | 29 | before running a spike |
| `tests.md` | Tests | 21 | before running tests |
| `background-work.md` | Background / long-running | 21 | before starting a background job |

Net: **671 → ~120 lines** resident (~8k tokens returned per session).

`dev/docs/rules/README.md` indexes the set and states the load-on-demand contract.

### Part B — `direction.md` removal

Every section gets an explicit destination. **This table is the completion checklist** — the work
is not done until every row is discharged and `direction.md` is deleted.

| `direction.md` section | Destination | Kind |
|-------------------------------------------|--------------------------------------|---
| Scope: a generic UnrealEngine-1 tool | `architecture.md` (scope preamble) | is |
| Projects, substrates, and the global CLI | `architecture.md`; unbuilt parts → `board/to-spec.md` | mixed |
| T3D trunk is source of truth | `architecture.md` | is |
| The trunk: git-committed T3D tree | `architecture.md` | is |
| Terminology | `architecture.md` (terminology section) | is |
| Folders | `architecture.md` | is |
| Labels | `architecture.md` | is |
| Materializing: `level materialize` | `architecture.md` | is |
| Safety: never irretrievably clobber | `architecture.md` | is |
| Lighting/BSP are build output | `architecture.md` + `unrealed/t3d.md` | is |
| Container isolation / substrate split | `architecture.md` | is |
| Generator pattern | `architecture.md` + `rules/code-cli-conventions.md` | mixed |
| One package-format core | `architecture.md` | is |
| The asset catalog | `board/to-spec.md` (largely unbuilt) | want |
| No back-compat cruft | `rules/code-cli-conventions.md` | rule |
| Explicit, discoverable, model-side | `rules/code-cli-conventions.md` | rule |

That the sections sort cleanly into **is** (→ `architecture.md`), **want** (→ board) and **rule**
(→ `rules/`) is itself the argument that `direction.md` was three docs wearing one coat.

**Also required:** remove the `@` import from `CLAUDE.md`; delete the `direction.md` row from
`dev/docs/README.md`'s "Which doc is for what" table and the two paragraphs below it that contrast
`direction.md` with `architecture.md`; retarget the 10 citing files.

### Part C — `decisions.md` prune + shard, as TWO separate commits

**C1 — shard (mechanical, verifiable, first).**

```
dev/docs/decisions/
  README.md      <- the preamble: purpose, format, pruning rules, index of shards
  2026-06.md
  2026-07.md
```

Monthly shards, entries in their existing order, **no content changes whatsoever** — the commit
must be provably content-preserving (see verification below). Citation migration is mechanical:
a dated citation (`decisions.md 2026-07-25 17:20 UTC`) rewrites to `decisions/2026-07.md`; an
undated one points at `decisions/README.md`.

**C2 — prune (judgement, risky, second, separately reviewed).**

Only the two classes the preamble already permits: entries a later one has **wholly** superseded,
and spike-result/feasibility-"gate" notes whose evidence lives in `spikes/`. Each pruned entry is
listed in the commit message with the entry that supersedes it. **Partially-superseded entries
stay** — their live half still governs.

**Why two commits:** sharding is mechanical and can be verified by diff; pruning is a 229-entry
judgement call where one wrong call silently destroys a live decision. Bundling them would hide
the risky half inside the safe half's diff — exactly the "one risky change hiding among many safe
ones" case `CLAUDE.md` says to split.

## 4. Risks

| # | Risk | Mitigation |
|----|--------------------------------------------------------|---
| R1 | **A rule the agent never loads cannot catch the agent.** Acute for review gates under D2: a session that does not realise a gate applies will not read the file that says it does | The resident trigger states the obligation unconditionally and names the file. Accepted residual risk, explicitly Andrzej's call |
| R2 | Pruning a *partially*-superseded entry destroys a live decision | C2 is a separate commit; every prune names its superseding entry in the commit message; partial supersessions explicitly out of scope |
| R3 | 120-file citation churn leaves dangling links | Link-check script over `dev/docs` + `docs` as a verification gate, run before and after |
| R4 | Removing `direction.md` loses the free always-loaded target | Router line in `CLAUDE.md`: before any design question or spec, read `architecture.md` + `board/to-spec.md` |
| R5 | Content lost in the `direction.md` fold | The Part-B table is a checklist; every row discharged before deletion. `direction.md` is deleted in the *same* commit that lands its fold, so a half-done fold cannot ship |

## 5. Verification

- **Link check** — no reference in `dev/docs/` or `docs/` resolves to a missing file or a deleted
  section anchor. Before/after comparison, run as a script.
- **Shard content-preservation (C1)** — concatenating the shards in order reproduces the original
  entry set exactly: entry count 229, and every `^## ` heading present with identical text.
- **Fold completeness (Part B)** — every row of the Part-B table discharged; `direction.md` gone;
  no surviving `@dev/docs/direction.md` import.
- **Resident size (Part A)** — `CLAUDE.md` ≤ ~130 lines; every moved section reachable from a
  router line that carries its load-bearing fact.
- **House rule** — no user-facing doc under `docs/` references anything under `dev/docs/`
  (`CLAUDE.md` "Documentation"). The `rules/` tree must not leak into the user cut.

## 6. Out of scope

- **`Tools/uplayctl/CLAUDE.md`**, which mirrors these rules by hand. Whether it should reference
  the same `rules/` tree or keep mirroring is a real question → file on `board/inbox.md`.
- The user-facing `docs/` tree — untouched.
- Any change to what the rules *say*. This is a **relocation**, not a rewrite: a rule whose
  wording changes is a separate, separately-gated change. (Unavoidable exception: the review-gates
  trigger text is newly written per D2.)
- `board/inbox.md` (2,602 lines) and `board/done.md` (1,125 lines), which are also large and also
  unpruned → file on `board/inbox.md`.

## 7. Sequencing

Each step is committed and pushed on landing; the gate runs over the batch per `CLAUDE.md`.

1. This spec → **spec gate**.
2. Part A (rules split) → build gate.
3. Part B (`direction.md` fold + delete) → build gate.
4. Part C1 (shard) → build gate.
5. Part C2 (prune) → build gate, separately.
6. `decisions.md` entries for D1–D5; `dev/docs/README.md` table updated; spec deleted.
