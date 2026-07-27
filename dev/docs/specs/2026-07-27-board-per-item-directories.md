# Spec — the board becomes one directory per work item

**Status:** rewritten 2026-07-27 after a spec-review round that returned a **structural finding**
(escalated to the owner and ruled — see §2.9). Awaiting a fresh round 1.
**Board item:** [`../board/to-plan.md`](../board/to-plan.md).
**Owner decisions:** §2. **Agent decisions:** §3, durable home nominated in §6.

**Every number in this spec was measured directly.** The first draft carried several that were
wrong — the item total was a double-count, the spec-file count was understated 2.4×, and the
priority census used a regex that saw only one of several spellings in use. Each figure below is
followed by the command that produced it where the command is not obvious.

---

## 1. What this changes

Today the uedcli backlog is **seven markdown files** under `dev/docs/board/` (`inbox.md`,
`to-spec.md`, `to-spike.md`, `to-plan.md`, `to-build.md`, `someday.md`, `done.md`) plus two
`HANDOFF-*.md` documents. Each file is a bullet list; each bullet is (mostly — see §3.9) one work
item. An item advances by having its bullet cut from one file and pasted into the next.

After this change, **each work item is a directory**, and the stage it is in **is the directory it
sits in**:

```
dev/docs/board/
  README.md                     the only prose file left at the top level
  inbox/
    parse-decimal-infinity/
      overview.md               REQUIRED — everything else is optional
    actor-preview-faces-order/
      overview.md
      questions/
        build-order.md
  to-spec/    <item>/…
  to-spike/   <item>/…
  to-plan/    <item>/…
  to-build/   <item>/…
  someday/    <item>/…
  stale/      <item>/…
  done/       <item>/…
```

Advancing an item is **one `git mv` of its directory** into the next stage.

### Why — the three problems

1. **Reads are enormous.** `inbox.md` is **356,795 bytes (357 KB) / 4,042 lines / 293 bullets**;
   the whole board is **7,187 lines**. An agent that wants one item reads all 293.
2. **Writes collide.** Several agent sessions work this repo at once, and every review round logs
   its findings to `inbox.md`. **35% of the last three days' commits touch that one file**
   (`git log --since=3.days --oneline -- dev/docs/board/inbox.md | wc -l` → 49, against 141 commits
   total). Two sessions finishing together edit the same file and then have to work out what
   happened to their edit.
3. **Questions are unfindable.** **68 board entries** are tagged as waiting on the owner, in eleven
   different spellings (`[OWNER — confirm]` 20, `[flag for Andrzej]` 10, `[OWNER — decide]` 9,
   `[decide]` 8, `[flag]` 6, `[ANDRZEJ — decide]` 6, `[flag→Andrzej]` 5, and four one-offs). Each is
   a paragraph inside a long file, indistinguishable from a note.

**Be clear about which win is which.** The **write-collision fix is structural and permanent** —
two agents logging two findings touch two paths that cannot conflict. The **read saving is real but
partial**: fetching one item gets ~350× cheaper, but *triage* — scanning the whole pool, which is
the majority access pattern — gets **worse**, because it becomes 293 file reads instead of one.
§3.10's `bin/board` exists to make that scan a header-only read rather than a full one; without it
this change would be a net regression for triage.

### What it unlocks

An agent drafts `spec.md` for an item and parks each unresolved fork as a question file. The owner
walks the question files, writes an answer into each, and an agent folds the answers into the spec
and the durable docs. The item cannot be planned or built while a question is open (§3.6), so
drafting runs ahead of the decisions without them being lost or silently guessed.

---

## 2. Owner decisions

Recorded as made, 2026-07-27. `CLAUDE.md` — "An owner DECISION is implemented as given" — binds
every one of these: an implementation may not add a guard, a fallback or a special case that
changes what they do.

**2.1 — Every stage has the identical shape, including `inbox` and `done`.**
*Owner: "Each one: inbox, ready-to-build, etc. should have the same setup; So you just git-mv stuff
between them when you need to."* No stage is special-cased; advancing is always the same command.
**Rejected:** *inbox stays a flat capture file* (cheapest capture, but leaves the 357 KB file and
its collisions untouched — that file is the problem). *`done`/`someday` stay flat* (saves converting
121 entries, but puts a hand-conversion on the boundary every time a `someday` item is revived).

**2.2 — `questions/` holds questions that BLOCK the item, not a conversation log.**
*Owner: "questions.md is not questions I asked, it's questions that need answering before the issue
can be built or planned."* A question file is a **gate**. Note the owner's words: *built **or
planned***. §3.6 implements both — the first draft gated only the build queue, which was a silent
narrowing of this decision.
**Rejected:** reading `questions/` as a per-item Q&A archive — it fills with resolved chatter and
stops being a reliable list of what is blocking.

**2.3 — Answering: the owner writes into the file; an agent folds it out and deletes it.**
Each question file carries an empty `## Answer`. The owner fills it in — that is the whole job. An
agent then copies the decision to its durable home (`direction/` for the owner's, `rationale/` for
an agent's), updates `spec.md`, and **deletes the question file**. Git keeps the text.
**Rejected:** *answered files stay, marked answered*; *answered files move to `answered/`* — both
accumulate dead questions and turn "what is open" into a status read.

**2.4 — Priority lives in the header at the top of `overview.md`, not in the directory name.**
A rename breaks links and fragments history.
**Rejected:** *a `p1-`/`p3-` name prefix* (free sorting, but re-prioritising renames the directory).
*No priority at all.*

**2.5 — The header carries a SHORT description; detail goes in the body.**
*Owner: "Header in overview.md should contain a SHORT description. More detail will be added in the
main body."*

**2.6 — Stale items go to `board/stale/`; removal is deferred.**
*Owner: "Put stale issues into board/stale, let's defer removal."* An ordinary stage directory of
the same shape. Nothing is deleted by this change.

**2.7 — The stale list is proposed at the VERY END, in bulk.**
*Owner: "Agent proposes, I confirm the list, BUT do that at the very end, ok? And then ask me in
bulk."* The migration converts every item **in place**, in its current stage, and only then produces
one list of proposed-stale items with a one-line reason each. `stale/` stays empty until that list
comes back confirmed.
**Rejected:** *an agent applies a written staleness rule unilaterally* — mechanical tests misfire on
vague one-liners and live work would vanish into a directory nobody reads.

**2.8 — The build queue keeps the name `to-build`.**
Stages: `inbox`, `to-spec`, `to-spike`, `to-plan`, `to-build`, `someday`, `stale`, `done`.
**Rejected:** `ready-to-build` (the owner's first sketch) — it would be the one stage not named
`to-<verb>`, needing a carve-out in the board's own naming rule.

**2.9 — Specs and plans live in the item directory, and everything references an item by its
SLUG, never by a path.** *This decision resolves a structural finding.* A spec review found that
**86 tracked files cite a spec or plan by path across 400 lines**, and **78 of those 86 citers are
durable** — 39 source files (`uedcli/`, `uned/`, `uedcli-native/src/`), 30 spike documents, plus
`architecture.md`, `unrealed/*.md`, `rationale/*.md`, `dev/docs/README.md` and the repo `README.md`.
Only 8 are the board itself.

```
git grep -l -E '(\.\./)?(dev/docs/)?(specs|plans)/[0-9]{4}-[0-9]{2}-[0-9]{2}[a-z0-9-]*\.md' \
    -- . ':!dev/docs/specs/*' ':!dev/docs/plans/*' | wc -l     # 86 files, 400 lines
```

Putting `spec.md` at `board/to-build/<slug>/spec.md` makes each of those addresses contain the
item's **current stage** — the one field this whole design exists to make cheap to change. Left
unaddressed, every `git mv` would invalidate its item's inbound citations, and repointing them
would touch shared files, destroying the disjoint-paths property that is the change's main win.

The owner's ruling: **keep specs and plans in the item directory, and make the slug the only
reference form.** A citation says `board item \`level-import\``, never a path. §3.3 specifies the
resolver and the test.
**Rejected:** *specs and plans stay in `dev/docs/specs/` and `dev/docs/plans/`, linked from
`overview.md`* — zero citations break and there is no resolver, but the item is not self-contained
and two parallel trees stay alive with the hand-maintained "which spec belongs to which item"
bookkeeping. *A stage-free item address (`board/items/<slug>/` with the stage as a field)* — nothing
can ever break, but `ls to-build/` stops being the queue and advancing becomes a file edit, which
reintroduces the contention the change exists to remove.

**2.10 — The header is YAML frontmatter.**
Chosen once dependencies entered the design: dependencies are a **list**, and a one-line
separator format handles lists badly. Frontmatter is unambiguously machine-readable, so the test is
a parser call rather than a hand-rolled regex, and fields can be added later without new syntax.
**Rejected:** *a middle-dot-separated blockquote* — reads better rendered and is closer to today's
board, but `·` already appears **30 times inside board prose** (`grep -c '·' *.md` → inbox 14,
done 13, to-build 2, to-spike 1), including in formulae, so the parse rule would need pinning, and a
dependency list inside a prose line is its weakest point. *Frontmatter for the fields with the
description left as prose* — two places to look for "what is this item", and the description stops
being machine-readable for `bin/board ls`.

**2.11 — `[spec]`, `[plan]` and `[spike]` are NOT kinds.**
*Owner: "Why do we need [spec] or [plan]? Each issue gets a plan."* Since every item that gets built
passes through spec and plan anyway, those tags say nothing the stage directory does not. The kinds
that survive are the ones the pipeline cannot infer: **`implement`, `chore`, `debug`, `docs`,
`owner-question`, `unknown`**.
**Rejected:** *keeping `[spec]`/`[spike]`/`[plan]` as pre-triage routing hints on untriaged items* —
proposed on the grounds that 51 inbox/someday items carry them and the path does not say "this needs
a spec next"; overruled by the owner's point that it needs one regardless. *Keeping all ~30 existing
spellings verbatim* — mechanical, but three of them mean "ask the owner" and filtering never becomes
reliable. *Dropping the kind field entirely.*

**2.12 — An item records what it depends on.**
*Owner: "Should we have room for dependencies (other issues this one depends on or spikes?)"* Yes —
and the distinction the owner drew about paths is exactly the §2.9 problem: **a dependency on
another item is written as that item's slug**, because a path would break every time the target
advanced a stage. **A dependency on a spike is written as a repo-root-relative path**, because
`dev/docs/spikes/` is durable and never moves.

---

## 3. The design

### 3.1 The stage directories

Exactly eight, all siblings of `README.md`, all the same shape:

| Directory | Holds | Next action
|--------------|--------------------------------------------------------|---
| `inbox/` | raw, un-triaged capture — ideas, gaps, bugs, chores, anything flagged for the owner | triage → `git mv` to a stage
| `to-spec/` | needs a spec/design written | write `spec.md` in the item directory
| `to-spike/` | an open question needs a live/offline investigation first | run a spike; evidence lands in `dev/docs/spikes/`
| `to-plan/` | has a reviewed spec, needs a plan | write `plan.md` in the item directory
| `to-build/` | reviewed plan, ready to implement now | implement it
| `someday/` | parked nice-to-have, not surfaced in normal triage | `git mv` back to `inbox/` when picked up
| `stale/` | judged stale, retained rather than deleted (§2.6) | none — revisit, or eventually delete
| `done/` | recently finished, or finished with deferred remnants | none — reference tail

**A stage directory contains item directories and a `.gitkeep`, and nothing else** — no per-stage
README, no loose `.md`. `ls dev/docs/board/to-build/` is therefore exactly the queue. `.gitkeep` is
required because git cannot track an empty directory and both `to-spike/` (3 items) and `stale/`
(empty until §2.7's list returns) will be empty. There is no `.gitkeep` convention in this repo
today (`git ls-files | grep -i gitkeep` → nothing), so the test in §3.7 asserts both the eight
directories and their keeps.

`board/README.md` stays the single prose file and documents the flow.

### 3.2 The item directory

```
<stage>/<item-slug>/
  overview.md         REQUIRED, in every stage. Frontmatter + title + body.
  spec.md             optional — the design
  plan.md             optional — the implementation plan
  questions/<q>.md    optional — one file per BLOCKING question
  <anything>.md       optional — handoff notes, measurements, findings
```

- **`overview.md` is the only required file.** For a one-line inbox note it is legitimately six
  lines. No item is forced to be filled out.
- **No other subdirectory is permitted** inside an item directory besides `questions/`. (The first
  draft left this undefined; the test in §3.7 now enforces it, so `to-plan/foo/attachments/` is an
  error rather than a silent grey area.)
- **Extra files are free.** `HANDOFF-level-import.md` (338 lines) and
  `HANDOFF-native-full-parity.md` (191 lines) become `handoff.md` inside their items. The second is
  marked SUPERSEDED in its own first line and has no owning board item; §4 rule 7 covers it.
- **Spike evidence does NOT move here.** `dev/docs/spikes/` is durable, cited from `architecture.md`
  and `unrealed/*.md`, and outlives the item. An item names its spikes in frontmatter (§3.4).

### 3.3 Slugs, and the reference rule (owner decision 2.9)

**The slug is the item's permanent identity.** Kebab-case, unique across the *whole* board
including `done/` and `stale/`, and **never renamed**.

**Derivation.** From the item's title, lowercased; `—`, `/`, `:` and backticks dropped; runs of
non-alphanumerics collapsed to a single `-`; trimmed to **48 characters** at a word boundary.

**Where there is no title to derive from.** Some bullets have no bolded lead sentence. The
migration takes the first sentence of the body instead, and where that is unusable an agent writes
one — this is the single place §4's "no rewriting" rule yields, and §4 rule 2 states it explicitly.

**Collisions.** Two items that reduce to the same slug get a numeric suffix on the *later* one
(`-2`), assigned by the migration in file order so it is deterministic and re-runnable. Real
near-collisions exist and must be handled by hand, not by suffixing: `done.md` "Per-surface texture
verbs, STEP 1 of 5" versus `to-plan.md` "Per-surface texture verbs — STEPS 2-5" are genuinely
different items and want genuinely different slugs.

**A completed item's slug is reserved forever**, because uniqueness spans `done/` and `done/` is
never pruned to nothing. A recurring chore therefore cannot reuse its natural name. This is a real
cost and it is accepted: the alternative — scoping uniqueness per stage — would make a slug
ambiguous as a reference, which is the whole point of §2.9.

**The reference rule.** Nothing outside an item directory writes a path *into* one. A code comment,
a durable doc, a spike, another item's frontmatter — all say the slug:

```python
# The edge model reads the single `Event` property only; see board item `eventgraph-scope`.
```

`bin/board show <slug>` (§3.10) resolves a slug to its current path. **A test asserts every
referenced slug exists** (§3.7), which is what makes the slug form safer than the path form it
replaces: a path citation into `specs/` rots silently today — `test_doc_links.py` only checks
markdown links, and its prose check covers `direction/`, `rationale/` and `rules/` alone — whereas a
dangling slug reddens the suite.

**The migration rewrites the 400 existing path citations to slug form** (§4 rule 8), with the two
exceptions §4.1 carves out.

### 3.4 `overview.md`

```markdown
---
priority: p1
kind: implement
summary: Replace the align flag group with subcommands and adopt the editor's projection family.
depends-on: [native-texture-decode]
spikes: [dev/docs/spikes/2026-07-26-unrealed-texalign-semantics/]
---

# Per-surface texture verbs — steps 2-5

The body: full detail, background, links, whatever the item needs.
```

| Field | Required | Values
|--------------|----------|---
| `priority` | yes | `p1` `p2` `p3` `p?`. **`p?` is legal in every stage.** See below.
| `kind` | yes | `implement` `chore` `debug` `docs` `owner-question` `unknown` (§2.11)
| `summary` | yes | one sentence, non-empty after stripping (§2.5)
| `depends-on` | no | list of **item slugs** — never paths (§2.12)
| `spikes` | no | list of **repo-root-relative paths** into `dev/docs/spikes/` (§2.12)

No other keys are permitted; the test rejects unknown ones, so a typo'd key is an error rather than
silently ignored data.

**`p?` is legal in every stage**, not only `inbox`/`stale`. The first draft restricted it, which
made the migration impossible to complete: **181 items carry no priority in any spelling, 122 of
them outside the inbox** — inbox 59, `to-spec` 13, `to-build` 3, `someday` 13, **`done` 93**.
Migration rule 3 forbids re-triaging and rule 4 forbids inventing a priority, so the restriction,
the copy-never-invent rule and the convert-in-place rule could not all hold. Priority is close to
meaningless in `done/` anyway.

**Priority is written several ways today and the migration must read all of them.** Only **82** of
293 inbox bullets use the backticked `` `p1` `` form, but **234** carry a priority once the other
spellings are counted:

```
- **[debug] p3 `parse_decimal` admits an INFINITY…**        ← inside the bold lead (the common form)
- `p2 [spec-done→plan]` **`config.toml paths` as a TOML list**
- **[implement] Native materialize remaining slices.** p1.  ← trailing
```

A migration that recognised only the backticked form would silently downgrade **152 prioritised
items to `p?`** — the mirror image of the fabrication that rule 4 exists to prevent.

**The kind vocabulary maps from ~30 existing spellings.** The census
(`grep -h '^- ' *.md | cut -c1-45 | grep -oE '\[[a-zA-Z][^]]*\]' | sort | uniq -c | sort -rn`):

| Existing | → kind
|-------------------------------------------------------------------------|---
| `[implement]` 77, `[build]` 2, `[implement?]` | `implement`
| `[chore]` 74, `[chore/bug]`, `[process/flag]` 2 | `chore`
| `[debug]` 55, `[finding]` 3, `[debug/perf]` | `debug`
| `[docs]` 3, `[note]` 4 | `docs`
| `[OWNER — confirm]` 15, `[flag for Andrzej]` 9, `[decide]` 7, `[flag]` 6, `[ANDRZEJ — decide]` 6, `[flag→Andrzej]` 5, `[OWNER — decide]` 5, `[question]`, and the `→Andrzej` compounds | `owner-question`
| `[spec]` 54, `[spike]` 17, `[plan]` 10, `[verify live]` 2, and the `[spike/…]`/`[…→…]` compounds | dropped per §2.11 — the item keeps the kind of *work* it is, or `unknown`
| no tag at all — **113 items, 91 of them in `done/`** | `unknown`

Applying this mapping **is a rewording**, which §4.2 otherwise forbids; rule 2 states the exception.

**`[OWNER — confirm]` keeps its spelling as a board *marker*.** `CLAUDE.md` mandates that exact
string in two places for parking a decision, so the frontmatter `kind: owner-question` is an
addition, not a rename — the item's title still reads `[OWNER — confirm]` where `CLAUDE.md` requires
it. (The first draft silently respelled it `[owner-confirm]`, which would have broken two `CLAUDE.md`
rules at once.)

### 3.5 Question files

Path: `<stage>/<item-slug>/questions/<question-slug>.md`.

```markdown
# Should `--faces` slices S1-S3 land before the texture decoder?

## Context

`actor preview --faces` draws brush faces as solid or textured pictures instead of outlines.
Its plan has five slices; only the fourth reads any texture data. …

## Options

- **Keep the ruled order.** … Consequence: …
- **Let S1-S3 land first.** … Consequence: …

## Recommendation

…

## Answer

<!-- Empty = open. Write the decision here. -->
```

- **`## Context` is mandatory**, and written for a reader who has neither the spec nor the code in
  their head — `CLAUDE.md` "Asking the owner" applied to a written artifact: name the thing in plain
  words first, never make a section number or symbol load-bearing, make each option self-contained
  with its concrete consequence, recommendation first. The test asserts the section exists.
- **`## Answer` is mandatory too, and its absence is a FAILURE, not an open question.** Worded the
  other way round — "open means the `## Answer` section is empty" — a malformed file with no
  `## Answer` heading at all would satisfy the gate and silently unblock the item.
- **"Empty" is defined**, because the edge cases decide whether a blocked item ships: content is any
  non-whitespace text between `## Answer` and the next same-or-higher heading or EOF, **excluding**
  HTML comments. A nested `###` heading, a fenced block, or a bare `?`/`TBD` **is** content — the
  test cannot second-guess the owner's intent, and a placeholder answer is the owner's problem, not
  the parser's.
- **A question needing a measurement is not a question file.** It moves the item to `to-spike/`.
- **This does not replace the `AskUserQuestion` widget.** `CLAUDE.md` requires decisions to go
  through the widget in-session. A question file is the *durable* form — how a question survives the
  session ending and how a batch is walked later. Asked and answered live, it never needs a file.

### 3.6 The blocking rule

**An item with an open question may not sit in `to-plan/` or `to-build/`** — the owner's words in
§2.2 are "built **or** planned". `to-spec/` is deliberately *not* gated: drafting a spec is exactly
how questions get discovered, so gating it would be circular.

**This supersedes the bounce-back rule.** `CLAUDE.md` and `board/README.md` both currently say *"a
question raised mid-pipeline bounces the item back to `inbox.md` until it's answered"*. Under the
new shape the question travels **with** the item as a file, and the item stops at the `to-plan/`
boundary instead of being sent to the back of the queue — which is strictly better, because the
spec work already done is not shelved. Both documents are updated in this change (§4.1).

**The answered-but-not-yet-folded state gets a name and a view.** The moment the owner types an
answer, the question stops being open — the gate lifts and the item becomes plannable from a
decision that no spec has absorbed and no durable doc records. So:

- `bin/board answered` lists every question whose `## Answer` is non-empty. This is the agent's work
  queue, and it is how an agent discovers that answers are waiting at all.
- **The `to-plan/`/`to-build/` gate keys on the file being *gone*, not on the answer being present.**
  Folding the answer out and deleting the file is what unblocks the item — which makes the durable
  write (`direction/`/`rationale/`, per §2.3) a precondition of building rather than an afterthought.
- **A question rendered moot by another answer** is deleted with a one-line note in the item's
  `overview.md` body saying which answer mooted it. Without this there is no disposal path for a
  moot question and it blocks the item forever.

### 3.7 The board test

Under `uedcli/tests/test_board.py`. **The path matters:** `pytest.ini` sets `testpaths = uedcli` and
`bin/test` runs `pytest uedcli`, so a test placed anywhere else is silently never executed and §7's
done-when would be vacuously true.

It asserts:

1. `dev/docs/board/` contains exactly the eight stage directories plus `README.md`; each stage has a
   `.gitkeep`.
2. Every stage directory contains only directories (plus `.gitkeep`).
3. Every item directory has an `overview.md`, and contains no subdirectory other than `questions/`.
4. Every `overview.md` has parseable YAML frontmatter with exactly the keys of §3.4, `priority` in
   `{p1,p2,p3,p?}`, `kind` in the six values, and a `summary` that is non-empty after stripping.
5. `depends-on` entries all resolve to an existing slug somewhere on the board; `spikes` entries all
   resolve to an existing path.
6. Item slugs are unique across the whole board.
7. Every question file has both a `## Context` and a `## Answer` section.
8. **No item under `to-plan/` or `to-build/` has any question file at all** (§3.6 — the gate keys on
   absence, so this needs no emptiness parsing and cannot be fooled by a malformed file).
9. Every `board item \`<slug>\`` reference in the tracked tree resolves (§3.3).

### 3.8 Advancing an item

```
git mv dev/docs/board/to-plan/<slug> dev/docs/board/to-build/<slug>
```

Two agents advancing two items touch disjoint paths — the §1 collision fix. Because references are
slugs (§2.9), nothing outside the item needs repointing.

**What git actually does, stated accurately.** `git log <item-dir>` after a move shows only the move
commit; `git log --follow` traces content across renames but accepts a **file**, not a directory. So
an item that traverses inbox → to-spec → to-plan → to-build → done needs one `--follow` per file.
§2.4's rationale ("a rename fragments its git history") is about *rename churn*, and it is correct
in that narrow sense, but this design mandates ~4 renames per item — the claim in the first draft
that "the whole item and its history move together" was overstated and is withdrawn.

**On completion**, `git mv … done/<slug>`, and `spec.md`/`plan.md` are deleted with `overview.md`
trimmed to a short reference entry — preserving the existing rule that specs and plans are ephemeral
and that what was learned folds into the durable docs first.

**Except when another live item shares the spec.** This is not hypothetical:
`specs/2026-07-26-poly-surface-verbs.md` is cited 11 times across three board files and covers a
**done** item (step 1 of 5), a **to-plan** item (steps 2-5) and three open owner questions. Deleting
it on step 1's completion would strand steps 2-5. Same shape for
`2026-07-18-warm-editor-materialize.md` (7 citations), `2026-07-24-level-import.md` (8),
`2026-07-27-actor-preview-faces-plan.md` (7) and `2026-07-25-unified-asset-catalog-plan.md` (4).
**Rule:** a shared spec belongs to the item whose work it *last* covers; earlier items link it by
slug and delete nothing. The migration decides ownership per shared spec and records it.

### 3.9 What counts as an item

**"Each bullet is one work item" is false**, and a migration keyed on `^- ` would be wrong in both
directions:

- **`to-build.md`**: of its 7 top-level bullets, **3 are the file's own navigation list** (lines
  7-10, "The upstream queues — …"). Two real items are `##` **sections with no bullet at all**
  (`## 7. BSP-issue detector`, `## 8. \`level import\``). Naive counting creates three junk
  directories and misses two real items.
- **`inbox.md`**: 8 `###` grouping headings with **42 nested bullets** beneath them, where the group
  is often the item and the bullets are its evidence (e.g. the "Level-authoring capability audit").
- **`to-spec.md`**, **`someday.md`**, **`done.md`**: `##`/`###` structure carrying `## Active` vs
  `## Deferred (someday)` and `## Partially done` — see §3.11.

**Rule:** the migration's first pass is an **inventory** that classifies every line of every board
file as *item*, *nested detail of an item*, *group heading*, or *navigation prose*, and that
inventory is reviewed before any directory is created. The per-file totals below are the naive
bullet counts and are **upper bounds on nothing** — they are the starting point for the inventory,
not the answer.

### 3.10 `bin/board`

Bash with `set -euo pipefail`, matching `bin/test` and `bin/uedcli`. It **sources no venv** — the
existing `bin/_venv.sh` hard-fails without python3.12 on PATH, which is far too heavy a dependency
for a read-only board query. It reads the tree and prints; **it also allocates slugs**, which is the
one write:

| Command | Does
|-----------------------|---
| `bin/board questions` | every OPEN question (file present, `## Answer` empty), grouped by item, with its path
| `bin/board answered` | every question with a non-empty `## Answer` — the agent's fold-out queue (§3.6)
| `bin/board ls [<stage>]` | items in a stage (all stages if omitted), sorted by priority then slug, one line each: slug, priority, kind, summary
| `bin/board show <slug>` | resolve a slug to its current path (§3.3)
| `bin/board new <stage> <title>` | create an item directory with a valid stub `overview.md`, allocating a non-colliding slug

`new` exists because capture ergonomics are otherwise a real regression: adding an inbox note goes
from "append one bullet" to "invent a globally-unique slug, mkdir, write frontmatter". `inbox/` is
the low-friction lane and this change must not tax it.

**Conventions:** `-h`/`--help` on every command; exit 0 on success, 2 on a bad stage/slug naming the
offending value (`CLAUDE.md` "No silent half-answers"), 1 on an I/O failure. A malformed item makes
the command **exit 2 naming the item**, never skip it silently. `questions`/`answered` scan all
eight stages. `p?` sorts last. `bin/board` gets its own tests in `uedcli/tests/test_board_script.py`
— an untested new executable is a gap `dev/docs/rules/spikes.md` explicitly warns against.

### 3.11 Structure that has nowhere obvious to go

§3.1 forbids loose files in a stage directory, so the following must each be given a home
*explicitly* rather than being silently dropped:

| What | Where it goes
|--------------------------------------------------|---
| **14 HTML-comment provenance banners** in `inbox.md` (e.g. `<!-- ═══ DOGFOODING FINDINGS (2026-07-12) … -->`) telling a reader where a block of items came from | copied into each affected item's body as a one-line `**Provenance:**` note — duplicated, not lost
| **8 `###` grouping headings** in `inbox.md`, 6 in `someday.md` | where the group is the item, it becomes the item and its bullets become the body; where it is only a category, it is dropped and the fact recorded in the inventory
| `## Active` / `## Deferred (someday)` in `to-spec.md`, `## Backlog — deferred` in `someday.md` | Deferred entries move to `someday/`. **This is the one re-triage the migration performs**, and it is mechanical — the file already declares the split.
| `## Partially done` in `done.md` and the `[~]`-vs-`[x]` marker on 25 bullets | a `**Remnants:**` line in the body. Not a frontmatter field — `done/` is a reference tail, not a queried set.
| **cross-noted duplicates** — `board/README.md` documents "(also in to-build.md #N)" so an item can legitimately appear twice | one directory, in the more advanced stage; the other reference becomes a slug mention in the body
| **positional cross-references** — "the item above", "the two items above", found at `inbox.md:259, 265, 306, 347, 1337, 1340, 1683, 1991, 2473, 2801, 3606` and `done.md:926, 1279` | repointed to the target's slug. This **is** an edit; §4 rule 2 states the exception.

---

## 4. Migration

**Scope.** 488 naive bullets (inbox 293, `to-spec` 55, `to-spike` 3, `to-plan` 9, `to-build` 7,
`someday` 27, `done` 94) — but see §3.9: the real item count comes from the inventory pass, not from
this number. Plus 2 handoff documents, **71 files in `dev/docs/specs/`** and **26 in
`dev/docs/plans/`** (`git ls-files dev/docs/specs | wc -l`).

**Rules:**

1. **No item's text is lost.** A bullet's body moves into its `overview.md`.
2. **Where the migration DOES edit** — the exhaustive list, because rule 1 is otherwise read as
   absolute: relative link targets are re-based (rule 5); positional cross-references are repointed
   to slugs (§3.11); path citations become slug citations (rule 8); the ~30 tag spellings map to six
   kinds (§3.4); a missing title is written (§3.3). Nothing else is reworded.
3. **Priority is copied, never invented** — reading *all* the spellings in §3.4. No priority in any
   form ⇒ `p?`.
4. **Every item is converted in its CURRENT stage.** Nothing is re-triaged and nothing is judged
   stale, with the single mechanical exception of the already-declared Active/Deferred split
   (§3.11).
5. **Relative links are re-based.** An item moves two directory levels deeper
   (`board/inbox.md` → `board/inbox/<slug>/overview.md`), and a spec moves from `dev/docs/specs/` to
   `board/<stage>/<slug>/spec.md`. **46 markdown links inside the board files** and **92 `../` links
   across 42 spec/plan files** must be re-based or they break. `overview.md` is not exempt from
   `test_doc_links.py`, so the board's 46 turn the suite red immediately; the rest would rot
   silently. This is the exception to "verbatim" that the first draft omitted entirely.
6. **The ~68 owner-blocking entries become question files** (§1 problem 3), not ordinary items.
   Without this rule `bin/board questions` is **empty on day one** and the change fails at its
   stated purpose. Where such an entry is not attached to a buildable item — several ask where a
   ruling should be *filed* — it becomes an item directory whose `overview.md` states the topic and
   whose `questions/` holds the question.
7. **A spec or plan with no board item** gets an item directory created in the stage its state
   implies, and appears on the stale list if it looks dead. Nothing is deleted or left behind. This
   includes `HANDOFF-native-full-parity.md`, which is marked SUPERSEDED and has no owning item.
8. **The 400 path citations become slug citations** (§2.9), except where §4.1 forbids the edit.
9. **`dev/docs/specs/` and `dev/docs/plans/` are removed once empty** — no stub, no forwarding note
   (`CLAUDE.md` "no back-compat cruft").
10. **Then, and only then, the stale list is proposed in bulk** (§2.7). `stale/` stays empty until
    it returns confirmed.

### 4.1 Fallout — the measured inventory

**78 tracked files outside `dev/docs/board/` reference a board path**
(`git grep -l -E 'board/(inbox|to-spec|to-spike|to-plan|to-build|someday|done)\.md|board/HANDOFF-' -- . ':!dev/docs/board/*' | wc -l`).
The first draft said "~15 code comments".

| What | Why it breaks | What it needs
|-------------------------------|----------------------------------------------------------------|---
| `uedcli/tests/test_doc_links.py` | `_on_deck()` reads `board/to-build.md` as a **file**; if it is merely missing the function returns an empty set and **every** ephemeral doc is silently unchecked — it fails *open*. `_EPHEMERAL` is a `startswith` **prefix tuple** used at **two** call sites (`_checked_docs`, `test_no_citation_of_a_deleted_doc`), and the replacement rule is a path *shape*, so the constant changes type. | Repoint and change type. **`_on_deck()` is then dead** — if the exemption itself says "except under `to-build/`", the function has no remaining purpose, and keeping both is exactly the dual-mechanism cruft `conventions.md` forbids. Delete it.
| same — **scale** | `_checked_docs()` parametrizes 3 test functions over every non-ephemeral tracked `.md`: ~255 today. After the migration, ~490 `overview.md` files join them, and `_anchors()` re-reads each link target uncached. | Budget for it; memoise `_anchors()` if the suite slows materially. Measure before and after.
| same — **coverage widens** | Today `dev/docs/specs/**` and `dev/docs/plans/**` are wholly exempt. Afterwards every item's `overview.md`, `handoff.md` and notes are checked in every stage. That is a large expansion, and it is the mechanism by which rule 5's 46 links go red. | Intended, but state it.
| `dev/docs/README.md` | Board rows are lines **36-40** (not 36-41); line **34** describes `specs/`+`plans/` as a tree that rule 9 removes; lines **74-77** describe the flow by filename a second time. | All three spots.
| `dev/docs/board/README.md` | Describes seven files, the bullet flow, the tag≈queue rule, the bounce-back rule and the cross-noting convention. | Full rewrite.
| `CLAUDE.md` | Names `board/inbox.md` at 7 places; states the tag≈queue rule (§2.11 retires it) and the bounce-back rule (§3.6 supersedes it). | Repoint and restate.
| **`CLAUDE.md` "Review gates" — a semantic collision, not a repoint** | It defines the round-2 trigger as *"'The artifact' = the files under review, **excluding `dev/docs/board/*`**"*. Once a spec lives at `board/to-plan/<slug>/spec.md`, editing it to resolve a round-1 finding stops being the trigger by the letter of that rule — **every spec and plan round in the repo would lose its round 2.** | Narrow the exclusion to `board/*/*/overview.md` and `board/*/*/questions/`, so `spec.md` and `plan.md` still count as the artifact.
| `dev/docs/architecture.md` (9 refs), `unrealed/*.md` (4 files), `rationale/*.md` (4 files) | Durable docs `CLAUDE.md` says must never be left stale. `rationale/userdocs.md` uses **markdown links**, so it reddens the link test. | Repoint to slugs.
| **~30 files under `dev/docs/spikes/`** | Durable evidence, link-checked. | Repoint to slugs.
| **`uedcli-native/src/{bspcsg,light,zones}.rs`** | Not mentioned in the first draft at all. Additionally invisible to every check — `_tracked(".md",".py",".sh",".toml")` excludes `.rs`. | Repoint; add `.rs` to the slug-reference check in §3.7, or record that Rust comments are unchecked.
| `uedcli/*.py` (8) + `uedcli/tests/*` (5) | Comment citations. | Repoint to slugs.
| **`dev/docs/decisions.md`** (26 refs) | `CLAUDE.md`: **FROZEN**, historical reading only, active entries never reworded. | **Do not edit.** Carve out.
| **`dev/docs/2026-06-20-open-questions-for-andrzej.md`** (2 refs) | `CLAUDE.md`: *"do not touch [it] at all."* | **Do not edit.** Carve out.
| `dev/docs/direction/process.md:51-54` | Carries the sentence this change makes wrong. | **Owner's tree.** §5.

**Because of the last two rows, §7's done-when cannot be "no tracked file references a deleted board
path"** — satisfying that would require editing a frozen doc and a file the rules forbid touching.
It is worded with those two exceptions named.

### 4.2 Migration concurrency — the protocol

`CLAUDE.md` says a feature is built in a worktree and squash-merged. **That is wrong for this
migration**, and the spec rules on it rather than leaving it to the plan, because it is a
correctness question:

35% of recent commits touch `inbox.md`. A worktree that deletes the seven board files and creates
~490 directories, squash-merged days later against a `master` where other sessions have appended
new bullets, produces a modify/delete conflict. The obvious resolution ("we deleted it, take the
delete") **silently discards every item added during the migration** — including review findings,
which `CLAUDE.md` requires to be logged there.

**Protocol:** the migration runs **on the base branch in committed batches**, one stage at a time,
smallest first (`to-spike` 3 → `to-build` → `to-plan` → `someday` → `to-spec` → `done` → `inbox`).
Each batch deletes its source file and lands in one commit, so the window in which a file is
half-migrated is minutes, not days. `inbox.md` goes **last** because it is the contended one, and
its batch is announced before it starts.

**This is a deliberate exception to the worktree rule, which is the owner's rule** — recorded here
rather than taken. If the owner would rather it ran in a worktree with a board freeze, that is their
call and this section changes.

### 4.3 What this migration is NOT

- **Not a re-triage** — except the already-declared Active/Deferred split (§3.11).
- **Not a cleanup** — duplicated, contradictory and obsolete items convert as they are, and are
  dealt with through the stale list.
- **Not a `uedcli` behaviour change** — no verb, flag or output changes.
- **Not a history preservation exercise.** Every item's history currently lives inside a
  4,000-line file and cannot be traced out of it; all ~490 `overview.md` files start their history
  at the migration commit. The board's per-item history begins here.

---

## 5. Text proposed for `dev/docs/direction/process.md` — AWAITING THE OWNER'S YES

`CLAUDE.md` forbids an agent editing `dev/docs/direction/` without an explicit yes. The current text
is a **bullet**, and its final sentence is the one this change makes wrong:

```
51 - **Nothing load-bearing lives only in chat.** A finding left standing, a
52   deferral, a refutation, an assumption, a flag for the owner — each goes on the
53   board (`../board/`) or into the commit message, because chat scrolls away. The
54   board is a set of stage queues named for the *next action* an item needs.
```

Only the final sentence (from "The board is a set…" on line 53) is replaced — the first draft said
"lines 53-54", which would have truncated the previous sentence mid-clause and broken out of the
bullet. **Proposed replacement, verbatim, staying inside the bullet:**

> The board is a set of stages named for the *next action* an item needs, and **each work item is a
> directory** whose stage is the directory it sits in — including the inbox, the someday shelf, the
> stale shelf and the done tail, so advancing an item is a single `git mv`. An item is referenced by
> its **slug**, never by its path, because its path encodes the stage and the stage changes. Its
> directory holds an `overview.md` — priority, kind, a short description, what it depends on, then
> the detail — and may hold the item's `spec.md`, its `plan.md`, and a `questions/` directory. **A
> question file is a blocker**: the thing that must be answered before the item can be planned or
> built. It is answered by writing into its empty `## Answer` section, after which an agent folds
> the decision into its durable home and deletes the file. **Nothing is deleted to tidy the board** —
> work judged stale is shelved, and the shelving list is confirmed in bulk rather than applied
> item by item.

**Deliberately kept short.** `process.md` says of itself that "the **operative procedures** live in
`CLAUDE.md` and `../rules/`; this doc says what they are for and why they are shaped that way", and
it applies that discipline to the review gate already. The mechanics — the eight stage names, the
frontmatter grammar, `bin/board` — therefore live in `CLAUDE.md` and `board/README.md`, and this
text carries only the intent, including owner decisions 2.1, 2.2, 2.3, 2.6, 2.7 and 2.9.

**Owner decisions 2.8 (the `to-build` name), 2.10 (frontmatter), 2.11 (the kind vocabulary) and
2.12 (dependencies) are format choices, not intent**, so they land in `board/README.md` and
`CLAUDE.md` rather than here — but they are the owner's, so they are recorded in the
`[OWNER — confirm]` item alongside this text.

**This text is parked on `board/inbox.md` as an `[OWNER — confirm]` item now**, not at the end of the
build, because `CLAUDE.md` requires the parked copy to exist so the decision survives the session
ending — and this spec is ephemeral.

---

## 6. Durable homes — where §2 and §3 land before this spec is deleted

`CLAUDE.md`: a decision must reach a durable doc before the ephemeral spec goes.

- **The owner's decisions (§2)** → `direction/process.md` per §5, plus the format choices in
  `board/README.md` and `CLAUDE.md`. Every `Rejected` alternative above travels with them; losing
  those is how a settled question gets re-proposed.
- **The agent's decisions (§3)** → a **new `dev/docs/rationale/board.md`**: the frontmatter grammar
  and why YAML over a separator format, the slug derivation and the permanent-reservation cost, the
  `.gitkeep` requirement, the `bin/board` scope and its no-venv choice, the widened link-test
  boundary, the gate-on-absence rule in §3.6, and the batched on-base-branch migration protocol —
  each with its `Rejected` alternatives and `Refs`. §7 has a done-when for it.

---

## 7. Open questions

**Q1 — the stale list.** Deferred by owner decision 2.7 to the very end, asked in bulk.

**Q2 — the migration's worktree exception (§4.2)** is recorded as a proposal, not taken. It changes
one of the owner's own process rules, so it needs a yes. Parked with the §5 text.

---

## 8. Done-when

- [ ] The eight stage directories exist with `.gitkeep`; the seven board `.md` files and both
      `HANDOFF-*.md` are gone.
- [ ] The inventory pass (§3.9) is recorded, and every item it identified is a directory with
      parseable frontmatter.
- [ ] `dev/docs/specs/` and `dev/docs/plans/` are empty and removed; all 71 specs and 26 plans live
      in item directories or are accounted for by rule 7.
- [ ] The ~68 owner-blocking entries are question files, and `bin/board questions` lists them.
- [ ] `uedcli/tests/test_board.py` passes, including the `to-plan/`+`to-build/` no-questions gate
      and the slug-reference check.
- [ ] `bin/board questions|answered|ls|show|new` work and have tests.
- [ ] The 400 path citations are slug citations, except in `decisions.md` and
      `2026-06-20-open-questions-for-andrzej.md`.
- [ ] `CLAUDE.md`'s round-2 trigger exclusion is narrowed (§4.1) so specs and plans still count as
      the artifact.
- [ ] `board/README.md`, `dev/docs/README.md`, `CLAUDE.md`, `architecture.md`, `unrealed/*`,
      `rationale/*`, the spike docs, the Python and the Rust sources describe the new shape. **No
      tracked file except `dev/docs/decisions.md` (frozen) and
      `dev/docs/2026-06-20-open-questions-for-andrzej.md` (the owner's) references a deleted board
      path.**
- [ ] `dev/docs/rationale/board.md` exists and carries §3's decisions (§6).
- [ ] The §5 direction text and the §4.2 worktree exception are confirmed and applied, or still
      parked as `[OWNER — confirm]`.
- [ ] `bin/test` is green; the suite's runtime change is measured and recorded.
- [ ] The stale list is proposed to the owner in bulk (§2.7).
