# Spec — docs restructure: `direction/` + `rationale/`, on-demand rules, no ledger

**Status:** v4. Awaiting round 2 of the spec gate (`CLAUDE.md` "Review gates").
**History:** v1 (`cf21f54`) parked — folding `direction.md` into `architecture.md` abolished the
"want" lane. v2 (`eee7e4e`) parked — deleting `decisions.md` left implementation rationale
homeless. v3 (`892a62c`) drew no structural finding; its reviewers converged on mechanism defects,
fixed here.

---

## 0. The problem, and what success looks like

Every uedctl agent session begins with **1,053 lines** already in context:

| | Lines | How |
|-----------------|-------|---
| `CLAUDE.md` | 671 | project instruction file |
| `direction.md` | 382 | the `@dev/docs/direction.md` import at `CLAUDE.md:591` |

Three problems hide in that:

1. **Most of `CLAUDE.md` is procedure, not trigger.** A session must *know* a worktree procedure
   exists; it need not hold all 84 lines until it starts a feature.
2. **`direction.md` is derived** — "synthesized from `decisions.md`", hand-reconciled, so
   periodically wrong. Its reconcile rule demonstrably lagged: entries dated 2026-07-25 11:20,
   11:31, 17:45, 18:15 and 18:40 postdate the newest one it reconciles (10:18).
3. **`decisions.md` is 8,985 lines / 227 entries** and grows ~30 entries a day at peak. It costs no
   context (it is not auto-loaded) but it is unnavigable, and its append-only model means it can
   only grow.

**Target:** resident context of **~569 lines** — `CLAUDE.md` 671 − 155 moved + ~22 (the
confirmation rule) + ~16 (router rows), plus a ~15-line auto-loaded `direction/README.md` index.
A **~46% reduction**, with every removed line reachable by an explicit trigger.

**Non-goal:** changing what any rule *says*. Where this restructure forces a wording change, Part E
enumerates it.

## 1. The model

Two docs are replaced by **two trees, split by who decided**:

| Tree | Holds | Owner |
|---------------------------------|-----------------------------------------------|---
| `dev/docs/direction/<topic>.md` | what **Andrzej** decided — product intent *and* process rulings | Andrzej; agents must ask |
| `dev/docs/rationale/<topic>.md` | what an **agent** decided — why the code is the way it is | agents |

Both are **revised in place**: no supersession, no dated-entry history. Git keeps history; the docs
keep the current answer. `direction.md` and `decisions.md` are deleted once both trees are populated.

**The axis is WHO DECIDED, not what it is about.** v3 stated this and then mis-derived its topic
lists by subject, which lost a whole category: **process decisions** — the review gate
(`decisions.md:8650`, `:8872`), the worktree procedure (`:8809`), the dev-doc system (`:719`), the
host-native venv (`:3439`). These are Andrzej's rulings about how the project runs. They are not
product intent and not keyed to a code module, so under v3 they would have been dropped. They are
his, so they go to **`direction/process.md`**.

**What the split buys.** One tree would either gate routine engineering notes behind a human
round-trip, or leave Andrzej's intent unprotected. Splitting by owner applies the confirmation cost
exactly where it earns itself.

## 2. The confirmation rule

**What is actually being traded.** v2 claimed append-only made rewriting *"structurally
impossible"*; that was false — `decisions.md` was an ordinary tracked file. v3 then claimed the
replacement was *"mechanical"*; that was also false — the trailer it named is written and checked
by the same agent it constrains. Stated correctly, third time:

> Append-only bought **detectability**: a violation still preserved the prior text, and stood out
> because the file's diffs were otherwise pure appends. Revise-in-place destroys the prior text and
> makes every legitimate edit look identical to an illegitimate one.

So the rule needs something outside the agent's own narration. **Part 0 installs a real
`core.hooksPath` pre-commit hook** that rejects a commit touching `dev/docs/direction/` without an
`Andrzej-confirmed:` trailer. This is bypassable by anyone who reads it — it is a guard rail, not a
security boundary — but it is external to the agent writing the commit, which the trailer alone was
not. The environment already relies on this pattern (a system-wide pre-push hook enforces the
no-force-push rule).

```markdown
### Direction docs — NEVER revise without confirmation

`dev/docs/direction/<topic>.md` holds what ANDRZEJ decided — product intent
and process rulings alike. It is MUTABLE: revised in place, no supersession,
no dated-entry history (git keeps that). Evidence citations and live-finding
dates ARE kept, per the Documentation rule.

- **NEVER create, revise, reword, or delete anything under
  `dev/docs/direction/` — including a single `Rejected` bullet — without
  asking Andrzej and getting an explicit yes.** Propose the exact text and
  wait. "It follows from what he said" does NOT satisfy this.
- **EXCEPTION, narrow:** `direction/README.md`'s index rows may be maintained
  without confirmation. No other content may be added to that file, and it
  may never contain an `@` import.
- **Moving a topic OUT of `direction/` is itself a confirmation point** — it
  removes the protection, so it needs his yes like any other edit.
- **When direction looks stale, ASK — never edit.**
- **Confirm proactively.** When working in a topic, ask whether its direction
  doc is still current.
- **A decision awaiting his yes is parked** as an `[ANDRZEJ — confirm]` item
  on `board/inbox.md` carrying the proposed text verbatim, so it survives the
  session ending. It moves into the topic doc on his yes.
- Every commit touching `dev/docs/direction/` carries an
  `Andrzej-confirmed: <topic>` trailer. A pre-commit hook enforces it.

`dev/docs/andrzej.md` and `dev/docs/2026-06-20-open-questions-for-andrzej.md`
are ALSO his — do not touch them at all.

Every other doc under `dev/docs/`, including `rationale/` and `rules/`, an
agent maintains on its own.
```

**Scope: `direction/` only** (Andrzej, 2026-07-25). The justification is **not** "everything else
is facts" — `rules/` holds his normative process text, which is no more fact-like. The real reason
is exposure time: `rules/` is exercised by every session and a corruption surfaces fast, whereas
`direction/` governs work that may not start for months.

**Named cost of the move, stated plainly:** today `CLAUDE.md` is resident, so a corrupted worktree
or spike rule is under ambient review by every session. After Part A those rules are read-on-demand
and a corruption is seen only by sessions that open the file. The NOT-trivial listing (Part E) is a
partial answer, not a full one.

**The rule lands in resident `CLAUDE.md`**, not in `rules/` — a confirmation rule an agent must
know to go read cannot protect anything.

## 3. Design

### Part 0 — rule, hook, READMEs, and the ledger freeze

- The rule above into resident `CLAUDE.md` (~22 lines).
- The **pre-commit hook** (`core.hooksPath`), committed to the repo.
- `direction/README.md` — the index; `rationale/README.md` — the model, ownership, and a **signpost
  to the history**: "pre-2026-07-25 rationale is in git history at `dev/docs/decisions.md`, removed
  in `<sha>`; `git log --follow -- dev/docs/decisions.md`". Both state the four-lane model that
  replaces `direction.md`'s preamble (`direction/` want · `rationale/` why · `architecture.md` is ·
  `rules/` process).
- **`decisions.md` is frozen here**, and `CLAUDE.md`'s "record every decision … in the durable,
  append-only `decisions.md`" is rewritten **now**, not in Part E. v3 left the flip until after the
  disposition sweep, so every concurrent session was still under orders to append to a file being
  audited against a frozen count.
- **The rule text that governs the migration lands here too** — the `direction/` exemptions to
  "After every change" and "The dev docs split by role". v3 sequenced those after the work they
  govern, so during Parts B–D the resident rules would simultaneously mandate "no doc may be left
  stale" and forbid touching `direction/`.

### Part A — move the rules whose read can be reliably triggered

v3's criterion ("a router line carries the load-bearing fact") did not survive its own table: the
`worktrees` router dropped two of the highest-consequence facts in the file. Corrected — under a
read-on-demand model **the router line's job is to trigger the read at the right moment, not to
carry the content**:

> A section moves iff its read can be triggered by a specific, observable moment. It stays resident
> iff it applies continuously, or if acting on the router line alone is dangerous.

| Moves | Lines | Router line triggers on | What the router deliberately drops |
|----------------------|-------|--------------------------------|---
| `spikes.md` | 29 | starting or finishing a spike | commit-the-harness; pin-the-finding-with-a-test |
| `tests.md` | 21 | running tests | host-native not container; integration deselected by default |
| `background-work.md` | 21 | starting a background job | the ~20-min fallback-timer shape |
| **total** | **71** | |

**`worktrees.md` (84) now STAYS RESIDENT.** Its router line cannot be made safe: `CLAUDE.md:321`
requires a `git diff --cached --quiet` check *before* `git merge --squash`, because the following
`git commit` commits whatever a concurrent session had staged — a data-loss trap — and `:337`
requires asking Andrzej before `git branch -D`. A rule whose omission destroys another session's
work fails the "acting on the router alone is dangerous" test.

**Stays resident:** Review gates (**224**), Documentation (96), **Feature worktrees (84)**, Code &
CLI conventions (63), TODOs/board (**38** — its six-queue map does not compress), UnrealEd
navigation (31), repo-this-lives-in (22), Commits (16), After every change (14), plus the rule
(~22) and router rows (~12).

Resident: 671 − 71 + 34 ≈ **634**, plus the ~15-line `direction/README.md` = **~649** vs 1,053
today. A ~38% reduction — less than v3 claimed, because two sections it moved should not move.

`dev/docs/rules/README.md` indexes the three files.

**`@` imports:** exactly one survives — `@dev/docs/direction/README.md`. Because `CLAUDE.md`
imports resolve **recursively (up to 5 hops)**, gating on `CLAUDE.md` alone is defeatable: the
README could `@`-import all 12 topics and the gate would still pass. So the gate is
`grep -rn '@dev/docs/' CLAUDE.md dev/docs/direction/README.md dev/docs/rules/` returning exactly
the one line, and the rule text forbids `@` in the README.

This overrides the logged finding at `board/inbox.md` ("gate on `@dev/docs/` **empty**") — recorded
as an explicit decision, not silently, per Part E.

### Part B — populate `direction/`, one topic at a time, each confirmed

**Thirteen topics** (12 from `direction.md`'s 16 sections, plus `process.md`):

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
| **`process.md`** | **the ledger's process rulings — review gate, worktrees, dev-doc system, venv** |

`conventions.md` stays a direction topic rather than folding into resident `CLAUDE.md`: it carries
the `movers.is_mover` ruling (an actor's class is answered from the hierarchy, never its name),
which is intent, not convention — and folding it would add ~45 unbudgeted resident lines.

Each topic has **What we want** + **Rejected**.

**Per topic, in one commit:** draft *What we want*; sweep the ledger for that topic's still-relevant
rejected alternatives **and any live decision `direction.md` never reconciled** (criterion: any
entry postdating the newest one `direction.md` reconciles — not a hard-coded list); put both to
Andrzej; on his yes, write the topic doc, **delete its section from `direction.md`**, and
**retarget that topic's citations** in the same commit. v3 deferred citations to a later part,
leaving the ledger's 39 `direction.md` refs dangling mid-migration.

`direction/README.md`'s rows carry per-topic state — an un-migrated topic points at
`direction.md §<name>`, so the resident index never points at a missing file.

### Part C — populate `rationale/`, agent-maintained

**`rationale/<topic>.md` has a mandated shape**, matching `direction/`:

```
## <the decision>
**Why it is this way:** …
**Rejected:** … because …
```

v3 specified no shape, which would have silently discarded the ledger's **83 `**Rejected:**`
blocks** — the majority of them on entries routed to `rationale/`. The ledger's own preamble says
those alternatives are the whole point of the file. A `rationale/` topic without a `Rejected`
section is the homelessness v2 was parked for, one level down.

**Every ledger entry gets a recorded disposition**, in a **durable file**,
`dev/docs/rationale/MIGRATION.md` (not the spec, which is deleted):

```
<date> <title>  ->  direction/<t>.md | rationale/<t>.md | superseded-dead | dropped
```

- `dropped` **and** `superseded-dead` both require a named reason, and `superseded-dead` must name
  the superseding entry. v3 left it unsigned, which made it a free escape hatch from `dropped`'s
  sign-off — and `CLAUDE.md` permits pruning only entries a later one has *wholly* superseded.
- Both columns get Andrzej's explicit sign-off before deletion.
- Gate stated **dynamically**: *no `^## \d{4}-` entry in `decisions.md` lacks a disposition row* —
  not "all 227", which is a frozen constant.
- `MIGRATION.md` is also the only `date → topic` map for Part D's bare dated refs, so it must
  outlive the migration.

### Part D — citation migration

| Class | Scale | Policy |
|--------------------------------|--------------------------|---
| `decisions.md` by name | 171 files (**170** excl. itself) — 122 `.md` (121 excl.), 45 `.py`, 3 `.sh`, `pyproject.toml` | retarget per its disposition row |
| `direction.md` by name | 45 files (**44** excl. itself) — 40 `.md`, 5 `.py` | retarget to the owning topic |
| `CLAUDE.md "<moved section>"` | `editor.py:267`, `test_engine_facts.py:3`, `test_mesh_decode.py:3`, `test_polyalign.py:434`, `board/inbox.md:77`, `board/README.md:43` | retarget to `rules/<file>.md` |
| **bare dated refs** | **19 files** with no literal `decisions.md` — the 5 named in v3 plus 11 tests, `preview_game.py`, `rotation.py`, and **`unrealed/commands.md:212`** (a durable engine doc) | rewrite to a topic path + anchor |
| **evidence citations** | 7 `unrealed/*.md` sites incl. the 🔬 at `package-format.md:65` | retarget to the `spikes/` file, **never** to a mutable doc |
| **`spikes/`** | **31 files**, incl. two committed harnesses | **retarget** — `spikes/` is durable evidence, not ephemeral. v3 gave it no policy while its own gate fired on it |
| ephemeral `specs/` + `plans/` | 62 of 64 specs, 18 of 23 plans | exempt from retarget **and from both checks** — except those on `to-build.md`, which are about to be executed |

**Accepted cost, stated:** these citations move from an immutable dated anchor to a revise-in-place
doc, so a comment can silently outlive the text it cited. v3 applied exactly this reasoning to route
`unrealed/` evidence to `spikes/` and then didn't apply it to code. Mitigation: cite
`rationale/<topic>.md#<slug>` and add **anchor existence** to the link gate, so a removed claim
breaks a check instead of rotting.

Code comments are load-bearing by house rule ⇒ **`bin/test` runs; this is a `build` row.**

### Part E — forced rule text

**The driver is a union of patterns, not one grep.** v3 claimed
`grep -n 'decisions\.md\|direction\.md' CLAUDE.md dev/docs/README.md` drove the build, then listed
four sites that grep does not return (`CLAUDE.md:428`, `:493`, `:496`, `:499` — bare date and
concept prose). Driver:

```sh
grep -nE 'decisions\.md|direction\.md|[Dd]ecisions? [0-9]{4}-|architecture, direction' \
  CLAUDE.md dev/docs/README.md
```

Known sites: `CLAUDE.md` 143, 230, 386, 422, 428, 472, 493, 496, 499, 526-531, 532, 554, 558, 573,
591, 593, 649; `dev/docs/README.md` 24, 25, 38, 39, 42, 43, 103.

Also required:

- **NOT-trivial list** drops the two deleted docs; gains `direction/*`, `rationale/*`, `rules/*`.
- **≥12 internal cross-references**, in both directions. The gate is **not** keyed on the literal
  `see **X**` — that form misses `CLAUDE.md:248`, `:300`, `:308`, `:347`, `:628`, `:662`. It is the
  position-relative sweep: any "above", "below", "this file", "two levels up", or bold/italic
  section name inside the moved 71 lines, plus doc-relative paths like `:393`'s
  `unrealed/quirks.md "Stability"`.
- **`dev-runtime.md` is stale in the opposite direction** — it still documents the Docker
  `uedctl-dev` image and `bin/_dev-run.sh`, retired 2026-07-14. Today the correct text is resident
  and wins; after the move an agent could read the wrong one first. Fixed in the same change.
- **The `@`-gate override** of the logged inbox finding, recorded as a decision.

### Part F — fix the three false statements in the moved/retained text

`CLAUDE.md` gate rules forbid waving a finding through because it is pre-existing, and all three are
inside the diff. Logging was v3's choice; these are **fixed**:

1. **`CLAUDE.md:290` — "`.claude/worktrees/` is gitignored" is FALSE.** Verified: `.gitignore` has
   no `.claude` entry, `git check-ignore .claude/worktrees` exits 1, `git status` shows `?? .claude/`.
   An agent trusting it could `git add` an entire second checkout. Either add `.claude/` to
   `.gitignore` (making the sentence true) or correct the sentence — **Andrzej's call**.
2. **`CLAUDE.md:3-19` — the `Tools/uedctl/` inside `dx_lum` layout, and "`_scratch/` two levels
   up".** The toplevel is `/home/neob91/Documents/Dev/uedcli`; there is no `Tools/`; `_scratch/` is
   at that root. This section stays permanently resident, so the error sits in the most privileged
   position available.
3. **`CLAUDE.md:293-297` — "this repo's `.claude/settings.json` sets `worktree.baseRef: head`".**
   That file does not exist.

## 4. Risks

| # | Risk | Mitigation |
|----|-------------------------------------------------|---
| R1 | A mutable `direction/` is silently rewritable | The rule, resident; the pre-commit hook; the `[ANDRZEJ — confirm]` inbox parking lane. A guard rail outside the agent's narration — **not** a security boundary, and said so |
| R2 | The migration drops a live decision | Every entry carries a disposition in durable `MIGRATION.md`; `dropped` and `superseded-dead` both need a named reason and sign-off; deletion is itself a confirmation point |
| R3 | Citations left dangling or silently rotted | Repo-wide link check + prose check + **anchor-existence** check; both exempt `specs/`+`plans/` |
| R4 | In-flight worktrees | `brush-profile-generators` is live; its diff touches `direction.md`, `README.md`, `architecture.md`, `inbox.md` — **not `CLAUDE.md`**. The hazard is `direction.md`→`direction/`, a delete/modify conflict git cannot auto-merge. Its merge is a **precondition** of this work, gated by whoever owns that branch — this work has no standing to merge it. A branch created later re-applies its `direction.md` hunk to the owning topic doc, which **re-enters the confirmation loop** |
| R5 | Migration stalls part-done | Each topic is one commit that lands the doc, deletes its `direction.md` section, and retargets its citations. `direction/README.md` carries per-topic state, so the index never points at a missing file |
| R6 | Steady-state confirmation traffic | The two-tree split is the mitigation. Relocating a topic out of `direction/` is **itself** a confirmation point, so it cannot be used as the escape hatch |
| R7 | Concurrent sessions append to a frozen ledger | The append rule is rewritten in **Part 0**, before the sweep |

## 5. Verification

Re-run before building — these have been wrong in every prior revision:

```sh
wc -l CLAUDE.md dev/docs/direction.md              # 671, 382  (resident today = 1053)
grep -rl 'decisions\.md' . --exclude-dir=.git --exclude-dir=.claude | wc -l   # 171 (170 excl. itself)
grep -rl 'direction\.md' . --exclude-dir=.git --exclude-dir=.claude | wc -l   # 45  (44  excl. itself)
grep -cE '^## [0-9]{4}-' dev/docs/decisions.md     # 227   (naive '^## ' gives 229: '## Format'
                                                   #        + a heading INSIDE a fenced block)
grep -c '^\*\*Rejected:\*\*' dev/docs/decisions.md # 83
awk '/^### /{if(h)print n" "h;h=$0;n=0;next}{n++}END{if(h)print n" "h}' CLAUDE.md
#   Review gates 224 · worktrees 84 · board 38 · spikes 29 · tests 21 · background 21
#   moved = spikes+tests+background = 71
git check-ignore .claude/worktrees                 # exits 1 — CLAUDE.md:290 is FALSE
```

Gates:

- Repo-wide link check, prose-citation check, **anchor-existence** check; all three exempt
  `specs/`+`plans/`.
- `bin/test` passes.
- `grep -rn '@dev/docs/' CLAUDE.md dev/docs/direction/README.md dev/docs/rules/` returns exactly
  one line.
- `direction/README.md` contains index rows only.
- The pre-commit hook rejects a trailerless `direction/` commit (tested, not assumed).
- The position-relative sweep is clean across `CLAUDE.md` **and** `dev/docs/rules/*.md`.
- No `^## \d{4}-` entry in `decisions.md` lacks a `MIGRATION.md` row; `dropped` and
  `superseded-dead` are signed off.
- All 16 `direction.md` sections **and its preamble's three-lane model** are accounted for.
- `docs/` references nothing under `dev/docs/`.

## 6. Out of scope

- **`Tools/uplayctl/CLAUDE.md`** mirrors these rules and is in a **different repository** —
  silently desynchronised by this work. Already on `board/inbox.md`.
- `dev/docs/README.md`'s table omits ~8 docs; `board/inbox.md` (2,671 lines) and `done.md` (1,125)
  are unpruned. Already logged.

The three false statements v3 deferred here are **now fixed in Part F** — they are in the diff, and
`CLAUDE.md` forbids logging an in-scope defect to avoid dealing with it.

## 7. Sequencing

Gates per `CLAUDE.md` "Review gates" — a **plan round** after this spec, then a **build round after
each of Part 0, Part A, Part B, and Parts C–F**, because the whole is far past what one reviewer
can read without skimming.

1. This spec → gate.
2. Plan doc → gate.
3. **Precondition:** `brush-profile-generators` has merged (owned by another session).
4. Part 0 — rule, hook, READMEs, ledger freeze, governing rule-text. → gate.
5. Part A — move 71 lines; router rows; `@`-gate. → gate.
6. Part B — 13 topics; each = doc + `direction.md` section deleted + citations retargeted. → gate.
7. Parts C–F — `rationale/` + `MIGRATION.md`; remaining citations; forced rule text; the three
   fixes. → gate.
8. Delete `direction.md` + `decisions.md` on Andrzej's explicit confirmation.
9. `dev/docs/README.md` updated; **retire the resolved inbox items by title, not line range**
   (they include the concurrency item, which R4 supersedes, and the `@`-gate item, which Part A
   overrides); delete this spec.
