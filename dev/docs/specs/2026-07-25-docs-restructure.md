# Spec — docs restructure: `direction/` + `rationale/`, on-demand rules, no ledger

**Status:** v5 — gated. Ready for a plan.
**History:** v1 (`cf21f54`) and v2 (`eee7e4e`) were parked on structural findings and resolved by
the owner's rulings. v3 (`892a62c`) and v4 (`70d55fd`) drew none; their reviewers converged on
mechanism defects, fixed here.

---

## 0. What this is for

**The goal is to stop keeping an append-only ledger** (the owner, 2026-07-25). Decisions should live
in per-topic docs that are **revised** to say the current answer, not appended to forever. Decision
*history* is git's job.

Success, in order of what actually matters:

1. **No append-only ledger.** `decisions.md` is gone. A new decision is *revised into* a topic doc.
2. **Per-topic and navigable.** ~13 `direction/` topics + ~10 `rationale/` topics, each readable in
   one sitting, replacing one 8,985-line file and one 382-line derived file.
3. **No decision history.** No supersession chains, no dated entries.
4. **Nothing states intent twice.** `direction.md` was *derived* from the ledger and hand-reconciled,
   so it drifted — entries dated 2026-07-25 10:20, 11:20, 11:31, 17:20, 17:45, 17:58, 18:15, 18:40
   and 18:42 all postdate the newest one it reconciles (10:18). After this there is one home per
   topic and nothing to reconcile.

**A side effect, not the goal:** resident context drops from **1,063 lines** (`CLAUDE.md` 671 +
the `@dev/docs/direction.md` import's **392**) to **~653** — 671 − 74 moved + ~22 (the confirmation
rule) + ~12 (router rows), plus a ~22-line auto-loaded `direction/README.md`. ~39%.

**Be clear that most of that is cheap.** Roughly 91% of the line reduction comes from replacing one
`@` import with an index; the rule moves add ~59 and the confirmation rule costs ~22 back. If line
count were the goal, deleting one character would be most of the win. It isn't the goal — goals 1–4
are, and none of them is reachable without the migration.

**Non-goal:** changing what any rule *says*. Where the restructure forces a wording change, Part E
enumerates it.

## 1. The model

| Tree | Holds | Owner |
|---------------------------------|-----------------------------------------------|---
| `dev/docs/direction/<topic>.md` | what **the owner** decided — product intent *and* process rulings | the owner; agents must ask |
| `dev/docs/rationale/<topic>.md` | what an **agent** decided — why the code is the way it is | agents |

Both **revised in place**: no supersession, no dated-entry history.

**The axis is WHO DECIDED, not what it is about.** v3 stated this and then derived its topic lists
by subject, losing a whole category: **process rulings** — the review gate (`decisions.md:8650`,
`:8872`), worktrees (`:8809`), the dev-doc system (`:719`), the host-native venv (`:3439`). Those
are the owner's, so they go to `direction/process.md`, not `rationale/`.

## 2. The confirmation rule — a convention, and only a convention

Two earlier revisions overclaimed here. v2 said append-only made rewriting *"structurally
impossible"* (false — it was an ordinary tracked file). v3 said the replacement was *"mechanical"*
(false — the trailer was written and checked by the same agent it constrained). v4 proposed a
`pre-commit` hook; round 2 **empirically demonstrated it cannot work**: `pre-commit` runs before the
message exists and takes no arguments, so a hook reading `.git/COMMIT_EDITMSG` sees the *previous*
commit's message — meaning a trailerless `direction/` commit passes whenever the one before it was
confirmed, which is the steady state of the migration. It fails open and looks green.

**The owner's ruling (2026-07-25): no hook.** `core.hooksPath` is a single value that overrides any
global or system hooks path, and the house rules depend on a system-wide pre-push hook enforcing
no-force-push; a repo-local override could silently disable it. Not worth the risk for a guard that
was never more than a marker.

So, stated honestly and finally:

> Append-only bought **detectability** — a violation still preserved the prior text, and stood out
> because the file's diffs were otherwise pure appends. Revise-in-place destroys the prior text and
> makes a bad edit look exactly like a good one. **Nothing replaces that.** The rule below is a
> convention; the trailer is an audit marker for `git log --grep`, not a gate.

```markdown
### Direction docs — NEVER revise without confirmation

`dev/docs/direction/<topic>.md` holds what the OWNER decided — product intent
and process rulings alike. MUTABLE: revised in place, no supersession, no
dated-entry history (git keeps that). Evidence citations and live-finding
dates ARE kept, per the Documentation rules.

- **NEVER create, revise, reword, or delete anything under
  `dev/docs/direction/` — including a single `Rejected` bullet — without
  asking the owner and getting an explicit yes.** Propose the exact text and
  wait. "It follows from what they said" does NOT satisfy this.
- **`direction/README.md` is the exception**: its index rows and its short
  model statement may be maintained freely. No topic CONTENT goes there, and
  it may never contain an `@` import.
- **Moving a topic OUT of `direction/` needs their yes too** — it removes the
  protection.
- **When direction looks stale, ASK — never edit.**
- **Confirm proactively.** When working in a topic, ask whether its direction
  doc is still current.
- **A decision awaiting their yes is parked** as an `[OWNER — confirm]` item
  on `board/inbox.md` carrying the proposed text verbatim.
- Commits touching `dev/docs/direction/` carry a `Confirmed: <topic>`
  trailer — an audit marker, not enforcement.

`dev/docs/andrzej.md` and `dev/docs/2026-06-20-open-questions-for-andrzej.md`
are also theirs — do not touch them at all.

Every other doc under `dev/docs/`, including `rationale/` and `rules/`, an
agent maintains on its own.
```

**Scope: `direction/` only** (owner ruling). Not because everything else is "facts" — `rules/` holds their
normative process text too — but because of **exposure time**: `rules/` is exercised by every
session so a corruption surfaces fast; `direction/` governs work that may not start for months.

## 3. Design

### Part 0 — rule, READMEs, ledger freeze, governing rule text

- The rule above into resident `CLAUDE.md`.
- `direction/README.md` — short model statement + the topic index, each row carrying **per-topic
  migration state** so the resident index never points at a file that does not exist yet.
- `rationale/README.md` — the model, the mandated entry shape, and a **signpost to the history**:
  `git log --follow -- dev/docs/decisions.md`.
- **Freeze `decisions.md`** and rewrite `CLAUDE.md`'s "record every decision … in the durable,
  append-only `decisions.md`" **here**. v3/v4 left this to Part E, so every concurrent session would
  still have been under orders to append to a file being audited against a fixed count.
- **Rewrite the pruning rule too.** `CLAUDE.md` currently permits removing only *wholly superseded*
  entries and spike-"gate" notes. Part C's `dropped` disposition is a third kind and has no
  authorizing rule until this lands.
- The `direction/` exemptions to "After every change" and "The dev docs split by role".

### Part A — move the rules whose read can be reliably triggered

A section moves iff its read can be **triggered by a specific observable moment**, and acting on the
router line alone is not dangerous.

| Moves to `dev/docs/rules/` | Body lines | Trigger | What the router deliberately drops |
|----------------------|------|--------------------------|---
| `spikes.md` | 29 | starting/finishing a spike | commit-the-harness; pin-the-finding-with-a-test |
| `tests.md` | 21 | running tests | host-native not container; integration deselected |
| `background-work.md` | 21 | starting a background job | the ~20-min fallback-timer shape |
| **total** | **71** (+3 headings = **74**) | |

**`worktrees.md` (84) STAYS RESIDENT.** Its router line cannot be made safe: `CLAUDE.md:321`
requires `git diff --cached --quiet` *before* `git merge --squash`, because the following commit
takes whatever a concurrent session had staged — a data-loss trap — and `:337` requires asking
before `git branch -D`.

Also resident: Review gates (224), Documentation (96), Feature worktrees (84), Code & CLI (63),
TODOs/board (38 — its six-queue map does not compress), UnrealEd navigation (31),
repo-this-lives-in (22), Commits (16), After every change (14).

`dev/docs/rules/README.md` indexes the three files.

**`@` imports:** exactly one survives — `@dev/docs/direction/README.md`. `CLAUDE.md` imports resolve
**recursively**, and a path-prefix gate is defeated by `@README.md` or `@../TODO.md`, so the gate is
keyed on **import syntax**: `grep -rnE '@[A-Za-z0-9._/-]+\.md' CLAUDE.md dev/docs/direction/README.md`
returns exactly the one allowed line. This overrides the logged inbox finding ("gate on `@dev/docs/`
empty") — recorded as a decision, not silently.

### Part B — populate `direction/`, one topic at a time, each confirmed

**13 topics**: `scope`, `projects-and-config`, `trunk-and-editor`, `organization`, `materialize`,
`safety`, `containers`, `generators`, `packages`, `asset-catalog`, `terminology`, `conventions`,
`process`. The first 12 cover all 16 sections of `direction.md`; `process.md` is new.

`conventions.md` stays a direction topic rather than folding into resident `CLAUDE.md` — it carries
the `movers.is_mover` ruling (an actor's class is answered from the hierarchy, never its name),
which is intent, and folding it would add ~45 unbudgeted resident lines.

**Shape:** `What we want` · `Rejected` · `Refs`. The `Refs` slot is not optional — the ledger format
had one, and dropping it discards spike/code evidence pointers by construction.

**Per topic, one commit:** draft *What we want*; sweep the ledger for that topic's still-relevant
rejected alternatives **and any live decision `direction.md` never reconciled** (criterion: any
entry postdating the newest one it reconciles — not a hard-coded list); put both to the owner as text;
on their yes write the doc, **delete that section from `direction.md`**, and **retarget that topic's
citations**, all in the same commit.

**This spec's own rulings land in `direction/process.md`** — the who-decided axis, `direction/`-only
scope, revise-in-place, no hook, deleting the ledger. Otherwise they exist only in a spec that step
9 deletes.

### Part C — populate `rationale/`, agent-maintained

**Mandated shape**, matching `direction/`:

```markdown
## <the decision>
**Why it is this way:** …
**Rejected:** <alternative> — because …
**Refs:** `spikes/<file>`, `uedctl/<module>.py`
```

v3 specified no shape, which would have discarded the ledger's **83 `**Rejected:**` blocks** —
mostly on entries routed here. That is the homelessness v2 was parked for, one level down.

**Every entry gets a disposition**, in a durable `dev/docs/rationale/MIGRATION.md` (not the spec,
which is deleted). It is also the only `date → topic` map for Part D's bare dated refs, so it
outlives the migration.

```
<date> <title>  ->  direction/<t>.md | rationale/<t>.md | superseded-dead | dropped
```

`dropped` **and** `superseded-dead` both need a named reason; `superseded-dead` must name the
superseding entry (v4 left it unsigned, making it a free escape hatch from `dropped`'s sign-off).
Both get the owner's sign-off. Gate stated **dynamically** — *no `^## \d{4}-` entry lacks a row* — not
against a frozen count.

### Part D — citation migration

| Class | Scale | Policy |
|--------------------------------|--------------------------|---
| `decisions.md` by name | 171 files (**170** excl. itself): 122 `.md`, 45 `.py`, 3 `.sh`, `pyproject.toml` | retarget per its disposition row |
| `direction.md` by name | 45 files (**44** excl. itself): 40 `.md`, 5 `.py` | retarget to the owning topic |
| `CLAUDE.md "<moved section>"` | **4** code sites: `editor.py:267`, `test_engine_facts.py:3`, `test_mesh_decode.py:3`, `test_polyalign.py:434` | retarget to `rules/<file>.md` |
| bare dated refs | ~17–19 files with no literal `decisions.md`, incl. `unrealed/commands.md:212` (a durable doc) — **count it in the build, don't trust this range** | rewrite to a topic path + anchor |
| evidence citations | 7 `unrealed/*.md` sites incl. the 🔬 at `package-format.md:65` | retarget to the `spikes/` file, **never** a mutable doc |
| `spikes/` | **31 files**, incl. two committed harnesses | retarget — durable evidence, not ephemeral |
| ephemeral `specs/` + `plans/` | 62 of 64 specs, 18 of 23 plans | exempt from retarget **and from all three checks** — **except the 13 files reachable from `to-build.md`**, which are about to be executed |

Two board sites (`inbox.md:74-83`, `board/README.md:43`) cite sections that now **stay resident**;
they need *editing*, not retargeting — `inbox.md`'s item even names a worktrees rules file, which is a file
Part A no longer creates.

**Accepted cost:** these citations move from an immutable dated anchor to a revise-in-place doc, so
a comment can silently outlive the text it cited. Mitigation: cite `rationale/<topic>.md#<slug>` and
add **anchor existence** to the link gate.

Code comments are load-bearing by house rule ⇒ **`bin/test` runs; this is a `build` row.**

### Part E — forced rule text

**The hand list is authoritative; the grep is a floor.** Three revisions claimed a grep drove this
and three times it missed `CLAUDE.md:428`, `:493`, `:496`, `:499` — because those citations
**straddle line breaks** and grep is line-oriented. Use `rg -U` if you want a machine assist, but
the list below is the contract.

`CLAUDE.md`: 143, 230, 386, 422, 428, 472, 493, 496, 499, 526-531, 532, 554, 558, 573, 591, 593, 649.
`dev/docs/README.md`: 24, 25, 38, 39, 42, 43, 45 (the `Tools/uedctl/` label), 103.

- **NOT-trivial list** drops the two deleted docs; gains `direction/*`, `rationale/*`, `rules/*`.
- **≥12 internal cross-references**, both directions. The gate is **not** keyed on `see **X**` —
  that misses `:248`, `:300`, `:308`, `:347`, `:628`, `:662`. It is a position-relative sweep for
  "above", "below", "this file", "two levels up", bold/italic section names, and doc-relative paths
  (e.g. `:393`'s `unrealed/quirks.md "Stability"`) across the moved 74 lines.
- **`dev-runtime.md` is stale in the opposite direction** — it still documents the Docker
  `uedctl-dev` image and `bin/_dev-run.sh`, retired 2026-07-14. Today the correct text is resident
  and wins; after the move an agent could read the wrong one first. Fix it in the same change.

### Part F — three false statements in the retained/moved text

All three are in the diff, so `CLAUDE.md` forbids logging them instead of dealing with them.

1. **`CLAUDE.md:290` — "`.claude/worktrees/` is gitignored" is FALSE.** `.gitignore` has no
   `.claude` entry; `git check-ignore .claude/worktrees` exits 1; `git status` shows `?? .claude/`.
   An agent trusting it could `git add` an entire second checkout. **Remedy: add `.claude/` to
   `.gitignore`**, making the sentence true — the owner's call, logged to `board/inbox.md` if he
   declines. Note this interacts with (3): a blanket `.claude/` ignore would block committing
   `.claude/settings.json`, so use `.claude/worktrees/` if (3) is resolved by creating that file.
2. **`CLAUDE.md:3-19` — the `Tools/uedctl/` inside `dx_lum` layout, and "`_scratch/` two levels
   up".** Toplevel is `/home/neob91/Documents/Dev/uedcli`; no `Tools/`; `_scratch/` is at that root.
   **Remedy: rewrite the paragraph to the real layout.** Same false label at `dev/docs/README.md:45`.
3. **`CLAUDE.md:293-297` — "this repo's `.claude/settings.json` sets `worktree.baseRef: head`".**
   That file does not exist, so `EnterWorktree` branches from `origin/<default>`, contradicting
   "the base is the branch the main checkout is already on". **Behavioural, not wording — the owner
   chooses:** create the file, or delete the sentence and accept the default.

## 4. Risks

| # | Risk | Mitigation |
|----|-----------------------------------------------|---
| R1 | `direction/` is silently rewritable | The resident rule + the `[OWNER — confirm]` parking lane + the audit trailer. **Convention only** — nothing mechanical, and §2 says so |
| R2 | Migration drops a live decision | Every entry dispositioned in durable `MIGRATION.md`; `dropped` and `superseded-dead` both reasoned and signed off; deletion is itself a confirmation point |
| R3 | Citations dangle or silently rot | Repo-wide link + prose + **anchor-existence** checks |
| R4 | Concurrent sessions | The `brush-profile-generators` branch **has merged** (`6900e34`), so the precondition is met — but any session may create a worktree and, until Part 0 lands, keeps minting `decisions.md` refs. **Re-run every inventory grep immediately after Part 0**; the counts here are measurements-at-a-sha, not constants |
| R5 | Migration stalls part-done | Each topic is one self-contained commit; `direction/README.md` carries per-topic state so the index never points at a missing file |
| R6 | Steady-state confirmation traffic | The two-tree split. Relocating a topic out of `direction/` is itself a confirmation point, so it cannot be the escape hatch |
| R7 | **`rationale/` is unprotected** and is where most of the 83 `Rejected` blocks land | **Accepted cost, named.** Any agent can delete a `Rejected` bullet and re-propose a killed design, with no confirmation and no signal in the diff. The mandated shape and the NOT-trivial listing are partial answers; there is no full one |
| R8 | Squash-merging this work would collapse 13 `Confirmed:` trailers into one | **This work does not run in a feature worktree** — it lands incrementally on the checked-out branch, so each confirmation keeps its own commit. Recorded as a deliberate exception to the worktree rule |

## 5. Verification

Re-run before building — these have been wrong in every prior revision:

```sh
wc -l CLAUDE.md dev/docs/direction.md              # 671, 392  (resident today = 1063)
grep -rl 'decisions\.md' . --exclude-dir=.git --exclude-dir=.claude | wc -l   # 171 (170 excl. itself)
grep -rl 'direction\.md' . --exclude-dir=.git --exclude-dir=.claude | wc -l   # 45  (44  excl. itself)
grep -cE '^## [0-9]{4}-' dev/docs/decisions.md     # 227  (naive '^## ' gives 229: '## Format'
                                                   #       + a heading INSIDE a fenced block)
grep -c '^\*\*Rejected:\*\*' dev/docs/decisions.md # 83
grep -rl 'decisions\.md\|direction\.md' dev/docs/spikes/ | wc -l              # 31
awk '/^### /{if(h)print n" "h;h=$0;n=0;next}{n++}END{if(h)print n" "h}' CLAUDE.md
#   Review gates 224 · worktrees 84 · board 38 · spikes 29 · tests 21 · background 21
#   moved = 71 body + 3 headings = 74
git check-ignore .claude/worktrees                 # exits 1 — CLAUDE.md:290 is FALSE
```

Gates: repo-wide link + prose + anchor-existence checks (all three exempt `specs/`+`plans/` save the
13 on `to-build.md`) · `bin/test` passes · the import-syntax `@` gate returns exactly one line ·
`direction/README.md` carries no topic content and no `@` · the position-relative sweep is clean
across `CLAUDE.md` and `rules/*.md` · no `^## \d{4}-` entry lacks a `MIGRATION.md` row · all 16
`direction.md` sections **and its preamble's lane model** are accounted for · `docs/` references
nothing under `dev/docs/`.

## 6. Out of scope

`Tools/uplayctl/CLAUDE.md` mirrors these rules and is in a **different repository** — silently
desynchronised by this work; already on `board/inbox.md`. `dev/docs/README.md`'s table omits ~8
docs; `board/inbox.md` (2,671 lines) and `done.md` (1,125) are unpruned.

## 7. Sequencing

A **plan round** follows this spec, then a **build round after each part** — the whole is far past
what one reviewer can read without skimming.

1. This spec → gated.
2. Plan doc → gate → `to-build.md`.
3. Part 0 → gate. Re-run every inventory grep immediately after.
4. Part A → gate.
5. Part B — 13 topics, each confirmed; gate per group of ~4.
6. Part C → gate. 7. Part D → gate. 8. Parts E+F → gate.
9. Delete `direction.md` + `decisions.md` on the owner's explicit confirmation.
10. `dev/docs/README.md` updated; retire the resolved inbox items **by title, not line range**
    (the concurrency item, the `@`-gate item Part A overrides, the `[debug]` item Part F fixes);
    delete this spec.
