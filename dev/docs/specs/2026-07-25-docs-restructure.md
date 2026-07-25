# Spec — docs restructure: `direction/` + `rationale/`, on-demand rules, no ledger

**Status:** v3. Awaiting spec-gate review (`CLAUDE.md` "Review gates").
**History:** v1 (git `cf21f54`) was parked on a structural finding — folding `direction.md` into
`architecture.md` abolished the "want" lane. v2 (`eee7e4e`) was parked on a second one — deleting
`decisions.md` left implementation rationale homeless. v3 resolves both by Andrzej's rulings.

---

## 1. The model

Two docs are replaced by **two trees**, split by *who owns them*:

| Tree | Answers | Owner | Mutability |
|-------------------------------|-----------------------------------|-----------------|---
| `dev/docs/direction/<topic>.md` | what Andrzej **wants** | **Andrzej** — agents must ask | revised in place |
| `dev/docs/rationale/<topic>.md` | why the **code** is the way it is | agents | revised in place |
| *(both)* | | | no supersession, no dated-entry history |

`direction.md` (382 lines) and `decisions.md` (8,985 lines / 227 entries) are deleted once both
trees are populated. Git keeps the history; the docs keep the current answer.

**Why two trees and not one.** The ledger conflated two things with different owners. Roughly 16
entries' worth is *intent* — what uedctl should become, which is Andrzej's call. The other ~200 are
*implementation rationale* — a T-junction tolerance, a `poly align` v1 scope, a texture-layout
arbitration. Those are engineering decisions an agent can and should maintain. One tree would
either gate trivial engineering notes behind a human round-trip, or leave intent unprotected.
Splitting by owner lets the confirmation rule apply exactly where it earns its cost.

**What this dissolves.** No never-reword rule to collide with, so the ~410 relative paths and the 39
in-ledger `direction.md` references stop being obstructions. No shard-axis question — topic is the
axis. The 216 dated code citations get a real target (`rationale/`), not a lossy one.

## 2. The confirmation rule, stated accurately

v2 claimed append-only made unauthorized rewriting *"structurally impossible."* That was wrong and
all three of round 2's reviewers said so: `decisions.md` was an ordinary tracked file. The accurate
property is narrower and still worth protecting:

> **Append-only meant a violation still preserved the prior text.** Revise-in-place destroys it —
> recoverable only by someone who already knows to look in git.

So the rule below is a convention replacing a convention, plus **detectability**: an append-only
file's diffs are otherwise pure additions, so a modified hunk stood out. Every legitimate
`direction/` edit is a modified hunk, so that signal is gone. It is therefore backed by a mechanical
check, not by good intentions (§5).

```markdown
### Direction docs — NEVER revise without confirmation

`dev/docs/direction/<topic>.md` states what Andrzej wants. It is MUTABLE —
revised in place, with no supersession and no dated-entry history (git keeps
that). Evidence citations and live-finding dates are KEPT, per the
Documentation rule.

- **NEVER create, revise, reword, or delete anything under
  `dev/docs/direction/` — including a single `Rejected` bullet — without
  asking Andrzej and getting an explicit yes.** Propose the exact text and
  wait. "It follows from what he said" does NOT satisfy this.
- **When direction looks stale, ASK — never edit.**
- **Confirm proactively.** When working in a topic, ask whether its direction
  doc is still current.
- **A decision awaiting his yes is parked** as an `[ANDRZEJ — confirm]` item
  on `board/inbox.md` carrying the proposed text verbatim, so it survives the
  session. It moves into the topic doc on his yes.
- Every commit touching `dev/docs/direction/` carries an
  `Andrzej-confirmed: <topic>` trailer.

`dev/docs/rationale/` and every other doc under `dev/docs/` an agent maintains
on its own. This one tree it does not.
```

**Scope: `direction/` only** (Andrzej, 2026-07-25). The honest justification is **not** "everything
else records facts" — `dev/docs/rules/` will hold Andrzej's normative process text, which is no more
fact-like than `direction/`. The real reason is enforcement: **`rules/` is enforced by the review
gate on every change that touches it** (Part D adds it to the NOT-trivial list), whereas `direction/`
governs work that may not happen for months, so a wrong edit there goes unchallenged far longer.

**The rule lands in resident `CLAUDE.md`, not in `rules/`.** Only `CLAUDE.md` is loaded by default;
a confirmation rule an agent has to know to read cannot protect anything.

## 3. Design

### Part 0 — the rule and both tree READMEs land first

Resident `CLAUDE.md` gains the rule above (~22 lines, budgeted in Part A). `direction/README.md`
and `rationale/README.md` state their model, ownership and precedence.

**`direction/README.md` is exempt from its own rule** — it is created in Part 0 with Andrzej's
confirmation of Part 0 itself, and the rule text says so explicitly to remove the self-reference.

**No `direction/<topic>.md` is written before this lands.** It governs the migration itself.

### Part A — move the rules whose fact fits a router line

v2's criterion ("rare trigger") did not survive review: `board` and `tests` are both named by
`CLAUDE.md` "After every change", so they fire on every change too. The honest criterion:

> **A section stays resident iff a one-line router cannot carry its load-bearing fact.**

| Moves to `dev/docs/rules/` | Lines | Router line carries |
|--------------------------|-------|---
| `worktrees.md` | 84 | never push a feature branch; squash-merge from the main checkout |
| `spikes.md` | 29 | commit the harness; pin the finding with a regression test |
| `tests.md` | 21 | run tests via `bin/test`, never `pytest` directly |
| `background-work.md` | 21 | never leave a background job on an open-ended wait; pair with a ~20-min fallback |
| **total** | **155** |

**Stays resident:** Review gates (**224**), Documentation (96), Code & CLI conventions (63),
**TODOs/board (39)** — its six-queue map, tag→queue mapping and one-home invariant do not compress
into a line — UnrealEd navigation (31), repo-this-lives-in (22), Commits (16), After every change
(14). Plus Part 0's rule (~22) and the new router rows (~16).

`dev/docs/rules/README.md` indexes the four files, matching every other `dev/docs/` subtree.

**Router lines are plain backticked paths, never `@` imports** — with **one deliberate exception**:
`@dev/docs/direction/README.md` (the 11-topic index, ~15 lines) stays auto-loaded. Without it an
agent has no idea the direction tree exists and cannot honour "confirm proactively". So the gate is
**`grep -n '@dev/docs/' CLAUDE.md` returns exactly that one line** — not empty, as v2 had it.

This is an explicit decision, not a side effect: **the want lane's *index* is resident; its
*content* is read-on-demand.** `CLAUDE.md:573` ("Only `direction.md` … is auto-loaded") and
`dev/docs/README.md:42` are rewritten to say so.

### Part B — populate `direction/`, one topic at a time, each confirmed

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
| `conventions.md` | No back-compat cruft + Explicit/discoverable/model-side |

**`conventions.md` is a direction topic, not a fold into `CLAUDE.md`.** v2 routed it to resident
"Code & CLI conventions"; reviewers found that (a) adds ~45 unbudgeted resident lines and (b) moves
statements of intent — notably the 2026-07-25 `movers.is_mover` decision that an actor's class is
answered from the hierarchy and never its name, with its named list of dependent verbs — outside the
confirmation loop. It stays intent, so it stays in `direction/`.

Each topic doc has **What we want** and **Rejected** (what we deliberately are not doing, and why).
`Rejected` is forward-looking — it stops a future session re-proposing a killed design — which is
why it survives a model that drops history.

**The migration is an interview.** Per Part 0, every topic's content needs Andrzej's explicit yes.
For each topic: draft *What we want*; sweep `decisions.md` for that topic's still-relevant rejected
alternatives **and for live decisions `direction.md` never reconciled** (its reconcile rule lagged —
entries dated 2026-07-25 11:20, 11:31, 17:45, 18:15, 18:40 postdate its newest reconciled entry);
put both to Andrzej as text; write only what he confirms; commit with the `Andrzej-confirmed:`
trailer.

**As each topic lands, its section is deleted from `direction.md` in the same commit**, leaving a
one-line pointer. Otherwise the migration runs a hybrid state of unbounded duration in which the
*stale* text is the resident one. `direction.md` survives until all 12 topics land; only the
duplicated sections go.

### Part C — populate `rationale/`, agent-maintained

The ~200 non-direction entries fold into `rationale/<topic>.md` keyed by the module or subsystem
they govern (`brush-builders.md`, `poly-align.md`, `packages.md`, `doctor.md`, `preview.md`,
`config.md`, `native-build.md`, `textures.md`, `movers.md`, `t3d-io.md` — final list derived from
the disposition table below, not guessed here).

**Every ledger entry gets a recorded disposition.** The build produces a table, one line per entry:

```
<date> <title>  ->  direction/<topic>.md | rationale/<topic>.md | superseded-dead | dropped
```

`dropped` requires a reason. This is the artifact that makes the sweep checkable — v2's mitigation
was "reviewed by Andrzej" with no stopping criterion, which reviewers correctly called unbounded.
**All 227 entries must carry a disposition before either file is deleted**, and the `dropped` list
gets Andrzej's explicit sign-off (see R2).

### Part D — citation migration

| Cited thing | Citing files | Policy |
|-------------------------------|--------------|---
| `decisions.md` | **171** (122 `.md`, 45 `.py`, 3 `.sh`, `pyproject.toml`) | retarget to the `direction/` or `rationale/` topic its disposition assigns |
| `direction.md` | **45** (40 `.md`, 5 `.py`) | retarget to the owning `direction/<topic>.md` |
| **`CLAUDE.md` "<moved section>"** | see §5 | **third class, missed by v2** — retarget to `dev/docs/rules/<file>.md`. Includes `uedctl/editor.py:267`, `uedctl/tests/test_engine_facts.py:3`, `test_mesh_decode.py:3`, `test_polyalign.py:434` |
| **bare dated refs** (`(decision 2026-07-24 18:12)`) | 76 refs in 32 files, **15 of which contain no literal `decisions.md`** — `uedctl/cli.py`, `level_select.py`, `native/materialize.py`, `normalize.py`, `stash_register.py`, + 10 tests | **fourth class, outside v2's inventory entirely.** The new model has no timestamps, so these need rewriting to a topic path, not a date |
| **evidence citations** in `unrealed/*.md` | 7 sites incl. a 🔬 marker at `package-format.md:65` | retarget to the `spikes/` file that holds the evidence, **not** to a mutable doc — `CLAUDE.md` requires engine claims to carry re-verifiable evidence |
| ephemeral `specs/` + `plans/` | 62 of 64 specs, 18 of 23 plans | **not** retargeted — except those on `to-build.md` (the asset-catalog spec + plan), which are about to be executed |

Code comments are load-bearing by house rule, so **`bin/test` must run and this is a `build` row,
not docs-only.**

### Part E — forced rule text

v2 hand-listed ~6 sites; reviewers found 16 in `CLAUDE.md` alone. **The build is driven by the grep,
not by a hand list:** `grep -n 'decisions\.md\|direction\.md' CLAUDE.md dev/docs/README.md`.

Known sites: `CLAUDE.md` 143 (NOT-trivial list), 230 (Review-gates *evidence* citation, inside the
resident section), 386 (Tests → moves to `rules/tests.md`), 422, 428, 472 (Code & CLI), 493/496/499
(Documentation prose), 526-531 (the three-lane model), 532, 554, 558, 573, 591, 593 (router rows),
649 (TODOs). `dev/docs/README.md` 24, 38, 39, 42, 103 (`direction.md`) **and 25, 43**
(`decisions.md` — v2 missed both).

Also required:

- **NOT-trivial list** drops the two deleted docs, gains `dev/docs/direction/*`,
  `dev/docs/rationale/*` and **`dev/docs/rules/*`** — without the last, a one-line edit to a
  relocated rule becomes gateable as trivial, an observable weakening caused by the move itself.
- **`CLAUDE.md` "After every change" and "The dev docs split by role" gain a `direction/`
  exemption** — both currently mandate "no doc may be left stale", which would order the very edit
  the confirmation rule forbids.
- **10 internal cross-references**, not 8 (lines 21, 30, 34, 35, 37, 51, 248, 300, 310, 662), in
  **both directions**. The nastier direction is *moved → resident*: `CLAUDE.md:300` ("**Commits**
  below") and `:310` ("**Review gates** above") end up inside `rules/worktrees.md` pointing at
  nothing, and a check that inspects only `CLAUDE.md` cannot see them.
- **Position-relative language in the moved 155 lines** — `CLAUDE.md:282-283` says the repo root is
  "two levels above this file", which becomes three inside `dev/docs/rules/`. Sweep for "this
  file", "below", "above", "two levels up".
- **`rules/tests.md` collides with `dev/docs/dev-runtime.md`**, which already documents `bin/test`
  and is **stale in the opposite direction** (it still describes the Docker `uedctl-dev` image and
  `bin/_dev-run.sh`, retired 2026-07-14). Today the correct text is resident and wins by default;
  after the move an agent can read the wrong one first. Fix `dev-runtime.md` in the same change.

## 4. Risks

| # | Risk | Mitigation |
|----|------------------------------------------------------|---
| R1 | A mutable `direction/` is silently rewritable; the old convention at least preserved prior text | Part 0's rule, resident in `CLAUDE.md`, plus the `Andrzej-confirmed:` commit trailer and its check (§5). Convention **plus** mechanism, since convention alone is a lateral move |
| R2 | The migration drops a live decision | Every one of the 227 entries carries a recorded disposition (Part C); the `dropped` list needs Andrzej's explicit sign-off, and **deletion of the two files is itself a confirmation point** — confirming 12 topic docs is not the same as confirming nothing else was worth keeping |
| R3 | 216+ citations left dangling | Repo-wide link check **and** a string check for prose citations, over `CLAUDE.md`, `dev/docs/`, `uedctl/`, `bin/`, `pyproject.toml`. Both exempt `specs/`+`plans/` |
| R4 | In-flight worktrees carry the pre-restructure tree | **`brush-profile-generators` is live now and its diff already touches `direction.md`, `README.md`, `architecture.md` and `inbox.md` — it merges first.** "Land only when no worktree is in flight" is not an achievable precondition (any session may create one), so the spec instead states the reconciliation: an in-flight branch takes the post-restructure `CLAUDE.md` wholesale and re-applies its own edits at the new locations |
| R5 | Migration stalls half-done | Each topic is independent and committed individually; per-topic deletion from `direction.md` keeps exactly one live text per topic, so a stall is a valid resting state with no ambiguity |
| R6 | Steady-state confirmation traffic makes routine work slow | The `direction/`/`rationale/` split is the mitigation: only intent needs a round-trip. If it still bites, that is a signal to move a topic to `rationale/`, not to bypass the rule |

## 5. Verification

**Re-verify these before building** (all measured 2026-07-25; v1's were wrong by ~4x, and round 2
found two of v2's still wrong):

```sh
grep -rl 'decisions\.md' . --exclude-dir=.git --exclude-dir=.claude | wc -l   # 171
grep -rl 'direction\.md' . --exclude-dir=.git --exclude-dir=.claude | wc -l   # 45 (excl. itself)
grep -cE '^## [0-9]{4}-' dev/docs/decisions.md                                # 227
#   NB: naive '^## ' gives 229 — it counts '## Format' and a heading INSIDE a
#   fenced code block. Any splitter must be fence-aware or it corrupts the template.
awk '/^### /{if(h)print n" "h; h=$0; n=0; next}{n++}END{if(h)print n" "h}' CLAUDE.md
#   Review gates 224 (NOT 216 — v2 carried a stale figure), board 39, worktrees 84,
#   spikes 29, tests 21, background 21  => moved total 155
```

Gates:

- Repo-wide link check; prose-citation check; **both** exempt `specs/`+`plans/`.
- `bin/test` passes.
- `grep -n '@dev/docs/' CLAUDE.md` returns **exactly one line** — `@dev/docs/direction/README.md`.
- No `see **X**` in `CLAUDE.md` **or `dev/docs/rules/*.md`** points at a section its file no longer
  holds; no position-relative language survives the move.
- The confirmation rule is present in resident `CLAUDE.md`.
- Every commit touching `dev/docs/direction/` has an `Andrzej-confirmed:` trailer.
- All 227 entries have a disposition; the `dropped` list is signed off.
- All 16 `direction.md` sections are covered by the Part-B table; both files are deleted only after
  every topic lands and Andrzej confirms the deletion.
- `docs/` references nothing under `dev/docs/` (currently clean — keep it).

## 6. Out of scope — already logged, do NOT re-log

All four are already on `board/inbox.md:74-89` from round 1. §7 **verifies** they are logged; it
does not add them again (`board/README.md`: move, don't copy — one home per item).

- `CLAUDE.md` "The repo this tool lives in" says uedctl lives at `Tools/uedctl/` inside `dx_lum`
  with `_scratch/` "two levels up". The toplevel is `/home/neob91/Documents/Dev/uedcli` and there is
  no `Tools/`. (`_scratch/` **does** exist — at that root, not two levels up.) Part A keeps this
  section resident, so the error stays in the most privileged position available.
- `CLAUDE.md` "Feature worktrees" asserts this repo's `.claude/settings.json` sets
  `worktree.baseRef: "head"`. That file does not exist. The text moves to `rules/worktrees.md`.
- `Tools/uplayctl/CLAUDE.md` mirrors these rules and is in a **different repository** — silently
  desynchronised by this work.
- `dev/docs/README.md`'s table omits ~8 docs; `board/inbox.md` (**2,671** lines) and `done.md`
  (1,125) are unpruned.

## 7. Sequencing

Per `CLAUDE.md`, specced pipeline work takes a **plan round**; v1 skipped it.

1. This spec → spec gate.
2. **Plan doc** → plan gate.
3. Merge `brush-profile-generators` (R4).
4. Part 0 — rule + both READMEs. **Nothing under `direction/` before this.**
5. Part A — rules split (155 lines).
6. Part B — 12 topics, each confirmed; each deletes its `direction.md` section.
7. Part C — disposition table for all 227 entries; populate `rationale/`.
8. Part D + E — citations and forced rule text.
9. Delete `direction.md` + `decisions.md`, on Andrzej's explicit confirmation.
10. Update `dev/docs/README.md`; **retire the round-1 inbox items this work resolved**
    (`inbox.md:22-73` — the parked finding, the shard-axis question, the Part-A-net-loss question,
    the corrected-measurements chore, the asset-catalog routing note are all settled); verify §6's
    items are still logged; delete this spec.
