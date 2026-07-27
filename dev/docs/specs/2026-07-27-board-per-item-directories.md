# Spec — the board becomes one directory per work item

**Board item:** [`../board/to-plan.md`](../board/to-plan.md). **Owner decisions:** §2 (implemented as
given). **Agent decisions:** §3, durable home in §6.

**Measurements are pinned to commit `e7d518c`**, the board state when this was written. The board
moves ~35 lines/day, so re-measure at execution.

---

## 1. What changes

Seven markdown files under `dev/docs/board/` become **eight directories of item directories**. The
stage an item is in **is the directory it sits in**; advancing is one `git mv`.

```
dev/docs/board/
  README.md                  the only prose file at the top level
  inbox/ to-spec/ to-spike/ to-plan/ to-build/ someday/ stale/ done/
    <item-slug>/
      overview.md            REQUIRED
      spec.md  plan.md       optional
      questions/<q>.md       optional — one BLOCKING question each
```

**Why.** Three problems, all measured:

1. **Reads.** `inbox.md` is 356,795 bytes / 4,042 lines / 293 bullets; the board is 7,173 lines.
2. **Write collisions.** 49 of 141 commits in three days touched `inbox.md` alone (35%). Several
   agent sessions share this repo and every review round logs findings there.
3. **Questions are invisible.** 70 entries wait on the owner, in thirteen tag spellings.

**Honest cost.** The write-collision fix is permanent. The read saving is partial: fetching one item
gets ~350× cheaper, but **triage — scanning the whole pool — gets worse**, from one read to 293.
`bin/board ls` (§3.9) makes that scan header-only (~35 KB); without it this change is a net loss for
triage.

**What it unlocks.** An agent drafts `spec.md` and parks each unresolved fork as a question file.
The owner walks the files and writes an answer in each. Drafting runs ahead of decisions without
them being guessed.

---

## 2. Owner decisions

**2.1 — Every stage has the identical shape**, inbox and done included. *"Each one … should have the
same setup; So you just git-mv stuff between them."*
*Rejected:* inbox stays flat (leaves the contended file); done/someday stay flat (friction on every
revival).

**2.2 — `questions/` holds BLOCKERS, not a log.** *"questions that need answering before the issue
can be built or planned."* Note **built *or planned*** — §3.6 gates both.
*Rejected:* a per-item Q&A archive — fills with resolved chatter.

**2.3 — The owner writes the answer; an agent folds it out and deletes the file.** The decision goes
to its durable home (`direction/` for the owner's, `rationale/` for an agent's), then `spec.md` is
updated and the question file deleted.
*Rejected:* keeping answered files (accumulates dead questions).

**2.4 — Priority lives in the header, not the directory name.** A rename breaks links.
*Rejected:* a `p1-` name prefix (free sorting, but re-prioritising renames).

**2.5 — The header carries a SHORT description; detail goes in the body.**

**2.6 — Stale items go to `board/stale/`; removal deferred.** Nothing is deleted by this change.

**2.7 — The stale list is proposed at the END, in bulk.** *"do that at the very end … ask me in
bulk."* Convert everything in place first; `stale/` stays empty until the list returns confirmed.
*Rejected:* an agent applying a staleness rule unilaterally.

**2.8 — The build queue keeps the name `to-build`.**
*Rejected:* `ready-to-build` — the only stage not named `to-<verb>`.

**2.9 — Specs and plans live in the item directory; everything references an item by SLUG, never by
path.** *Resolves a structural finding:* 86 files cite a spec or plan by path across 401 lines, 76
of them durable. An item's path contains its stage, so path citations would break on every `git mv`
and the repoint would touch shared files — destroying the disjoint-paths win.
*Rejected:* specs/plans stay put and are linked (nothing breaks, but the item is not self-contained
and two trees stay alive); a stage-free address (nothing can break, but `ls to-build/` stops being
the queue and advancing becomes a file edit).

**2.10 — The header is TOML frontmatter, delimited `+++`.** Chosen after the YAML ruling's premise —
"the test is a parser call" — proved false: this repo has no YAML parser, `pyproject.toml` states
Pillow is its only third-party dependency, and `bin/board` is bash without a venv so it would
hand-roll regardless. `tomllib` is **stdlib** on the repo's Python 3.12, and TOML is already a house
format (`uedcli.toml` via `config.py`). TOML also always quotes strings, which removes the quoting
hazard: 166 of 490 board titles start with a backtick, 81 contain `: `, 19 contain ` #` — all fatal
to an unquoted YAML scalar.
*Rejected:* YAML + a PyYAML dependency (a second third-party dep, for a docs format); a YAML-shaped
subset (a trap for an author who assumes real YAML); a `·`-separated line (`·` occurs 48 times in
board prose, and lists read badly in it).

**2.11 — `[spec]`, `[plan]` and `[spike]` are not kinds.** *"Why do we need [spec] or [plan]? Each
issue gets a plan."* Kinds are what the pipeline cannot infer: **`implement`, `chore`, `debug`,
`docs`, `owner-question`, `unknown`**.
*Rejected:* keeping them as pre-triage routing hints; keeping all 43 existing spellings.

**2.12 — An item records its dependencies.** On another item: **its slug** (a path would break on
every stage advance). On a spike: a **repo-root-relative path** (`dev/docs/spikes/` never moves).

**2.13 — An item that gains a blocking question moves back to `to-spec/`.** One rule for the
migration and for steady state. It replaces today's bounce-*to-inbox* rule, stopping one stage
earlier so finished spec work is not shelved. At migration this re-triages three named items —
`unified-asset-catalog` and `actor-preview-faces` (`to-build`, 2 questions each) and
`poly-surface-verbs` (`to-plan`, 3) — the sole exception to §4 rule 4.
*Rejected:* gating only post-migration items (the three most important blocked items would sit in
the build queue looking ready); keeping the question as a separate inbox entry (the item's own
directory would not show it is blocked).

**2.14 — Docs, docstrings and comments are as succinct as the meaning allows.** No bloat, no cruft,
facts only; length is earned by what must be explained. **A reviewer flags any doc they cannot fully
understand, or that is ambiguous.** Applies repo-wide, not to this spec alone.

---

## 3. Design

### 3.1 Stages

| Directory | Holds | Next action
|--------------|--------------------------------------------------|---
| `inbox/` | un-triaged capture; anything flagged for the owner | triage → `git mv`
| `to-spec/` | needs a spec | write `spec.md`
| `to-spike/` | needs an investigation first | run a spike → `dev/docs/spikes/`
| `to-plan/` | has a reviewed spec | write `plan.md`
| `to-build/` | reviewed plan, ready now | implement
| `someday/` | parked; not in normal triage | `git mv` to `inbox/` when picked up
| `stale/` | judged stale, retained (§2.6) | none
| `done/` | recently finished, or finished with remnants | none

A stage directory holds item directories and a `.gitkeep`, nothing else — so `ls to-build/` is the
queue. `.gitkeep` is needed because git cannot track an empty directory and `stale/` starts empty;
no such convention exists in this repo today. `board/README.md` stays the single prose file.

### 3.2 The item directory

`overview.md` is the only required file — six lines is legitimate for an inbox note. The only
permitted subdirectory is `questions/`. Extra `.md` files are free, **except** that a logged review
finding lands in `overview.md` or a question file and nowhere else (§4.1, round-2 trigger). The two
`HANDOFF-*.md` files become `handoff.md` in their items. Spike evidence stays in
`dev/docs/spikes/` — durable, cited from `architecture.md`, outlives the item.

### 3.3 Slugs and the reference rule

**The slug is the item's permanent identity**: kebab-case, unique board-wide, never renamed.

- **Derived from the title after stripping any leading `[tag]` and `pN`.** Without stripping, 168
  titles would yield slugs like `debug-p3-parse-decimal-…` and `spike-p3-…` — baking a priority and
  an abolished kind into a permanent name, defeating §2.4 and §2.11.
- **The migration WRITES a short slug; it does not truncate a sentence.** 389 of 473 titles exceed
  48 characters, so truncation would produce permanent identities cut mid-phrase
  (`architecture-md-contradicts`). Authoring a slug is explicitly one of §4 rule 2's permitted edits.
- **Collisions** take a `-2` suffix on the later item in file order. Rare in practice — deriving over
  all 473 bold titles gives 471 distinct slugs.

**The reference rule.** Nothing outside an item directory writes a path into one. A code comment, a
durable doc, a spike, another item's frontmatter all say ``board item `<slug>` ``.

- **Exact form:** the literal `board item` (or `board items`) followed by one or more backticked
  slugs separated by commas. The tree already contains 26 uses of the bare phrase "board item" with
  no backticked slug; the regex requires the backticks, so those do not match.
- **Scanned suffixes:** `.md .py .sh .toml .rs`. `.rs` is **in** — four Rust files cite the board
  today and the existing checker's `_tracked()` excludes them.
- **Test 9 (§3.7) asserts every reference resolves.** This is what makes the slug form safer than
  the path it replaces: a path citation into `specs/` rots silently today, a dangling slug reddens
  the suite.

**`done/` is pruned** — `CLAUDE.md` and `board/README.md` both say it keeps only a short tail. So a
slug is *not* reserved forever. **Pruning a done item is legal only when nothing cites it**, which
test 9 enforces; otherwise the citation would silently resolve to a later item reusing the name.

### 3.4 `overview.md`

```markdown
+++
priority = "p1"
kind = "implement"
summary = "Replace the align flag group with subcommands."
depends-on = ["native-texture-decode"]
spikes = ["dev/docs/spikes/2026-07-26-unrealed-texalign-semantics/"]
+++

# Per-surface texture verbs — steps 2-5

The body: detail, background, links.
```

| Key | Req | Values
|--------------|-----|---
| `priority` | yes | `p1` `p2` `p3` `p?` — **`p?` legal in every stage**
| `kind` | yes | the six of §2.11
| `summary` | yes | one line, non-empty after stripping, no newline
| `depends-on` | no | item **slugs**
| `spikes` | no | repo-root-relative paths

No other key is permitted. A frontmatter that fails to parse is a **test failure**; `bin/board`
reports it against that item and continues with the rest (§3.9).

**`p?` is legal everywhere.** 181 items carry no priority in any spelling, 122 outside the inbox
(`done` 93 alone) — restricting `p?` would make the migration impossible to complete.

**The migration must read every priority spelling.** Only 82 of 293 inbox bullets use `` `p1` ``;
234 carry one once `**[debug] p3 …**`, `` `p2 [tag]` `` and trailing `p1.` are counted. Reading only
the backticked form would silently downgrade 152 prioritised items.

**Kind mapping**, from a 43-spelling census (measured on full lines — a `cut -c1-45` census
undercounts every tag past column 45):

| Existing | → kind
|---|---
| `[implement]` `[build]` `[implement?]` | `implement`
| `[chore]` `[chore/bug]` `[chore/flag]` `[process/flag]` | `chore`
| `[debug]` `[debug?]` `[debug/perf]` `[finding]` | `debug`
| `[docs]` `[note]` | `docs`
| `[OWNER — confirm]` `[OWNER — decide]` `[ANDRZEJ — decide]` `[FLAG-FOR-ANDRZEJ]` `[decide]` `[flag]` `[flag for Andrzej]` `[flag→Andrzej]` `[question]` and the `→Andrzej` compounds | `owner-question`
| `[spec]` `[spike]` `[plan]` `[verify live]` and their compounds | dropped (§2.11); the item keeps the kind of *work* it is, else `unknown`
| `[resolved …]` `[RESOLVED → …]` `[DECISION-MADE / …]` | the item is a stale-list candidate
| no tag — 113 items, 91 in `done/` | `unknown`

Applying the mapping is a rewording; §4 rule 2 permits it. **`[OWNER — confirm]` keeps that exact
spelling in the item's title**, because `CLAUDE.md` mandates the string; `kind` is an addition, not
a rename.

### 3.5 Question files

```markdown
# <the question>

## Context
<plain words: what the thing IS, before asking about it>

## Options
- **<option>** — consequence.

## Recommendation
## Answer
<!-- Empty = open. -->
```

- **`## Context` and `## Answer` are mandatory.** A missing `## Answer` is a **failure**, not an open
  question — worded the other way round, a malformed file would satisfy the gate.
- **"Empty"** = no non-whitespace text between `## Answer` and the next same-or-higher heading,
  ignoring HTML comments. A `?` or `TBD` **is** content; second-guessing the owner is not the
  parser's job.
- **Where the answer would change a `direction/` doc — sometimes, not usually — the file also carries
  the proposed replacement text**, succinct, so answering settles the decision and approves the
  wording in one pass. Otherwise `CLAUDE.md`'s "propose the exact text and wait" would make every
  such question two round trips.
- A question needing a **measurement** is not a question file: the item goes to `to-spike/`.
- This does not replace the live `AskUserQuestion` widget. A question file is the durable form — how
  a question survives the session ending.

### 3.6 The gate

**An item with any question file may not sit in `to-plan/` or `to-build/`** (§2.2: "built or
planned"). `to-spec/` is not gated — drafting a spec is how questions are found.

**The gate keys on the file being GONE, not on the answer being present.** Otherwise typing an
answer would unblock the item before any durable doc recorded the decision. So folding out and
deleting is what unblocks — making the durable write a precondition of planning.

`bin/board answered` lists questions with a non-empty `## Answer`: the agent's fold-out queue, and
the only way an agent learns answers are waiting. A question **mooted** by another answer is deleted
with a one-line note in `overview.md` saying which answer mooted it.

### 3.7 `uedcli/tests/test_board.py`

The path matters: `pytest.ini` sets `testpaths = uedcli` and `bin/test` runs `pytest uedcli`, so a
test elsewhere never runs.

1. `board/` holds exactly the eight stages plus `README.md`; each stage has a `.gitkeep`.
2. Each stage holds only directories (plus `.gitkeep`).
3. Each item has `overview.md`; no subdirectory but `questions/`.
4. Frontmatter parses via `tomllib`; the three required keys present; no key outside §3.4;
   `priority` and `kind` in range; `summary` non-empty and single-line.
5. `depends-on` slugs resolve; `spikes` paths exist; **no dependency cycle**; a `to-build/` item may
   not depend on a `stale/` item.
6. Slugs unique board-wide.
7. Every question file has `## Context` and `## Answer`.
8. No item under `to-plan/` or `to-build/` has any question file (§3.6 — absence, so no emptiness
   parsing and a malformed file cannot fool it).
9. Every ``board item `<slug>` `` reference in tracked `.md .py .sh .toml .rs` resolves (§3.3).

### 3.8 Advancing, and completion

`git mv board/to-plan/<slug> board/to-build/<slug>`. Disjoint paths; nothing outside needs
repointing because references are slugs.

**Git history, accurately:** `git log <dir>` after a move shows only the move; `--follow` traces
content but takes a file, not a directory. An item crossing four stages needs one `--follow` per
file. The migration itself is a **history reset** — every `overview.md` starts at the migration
commit, because a bullet's history cannot be traced out of a 4,000-line file.

**On completion** `git mv … done/<slug>`; `spec.md`/`plan.md` are deleted and `overview.md` trimmed,
preserving the rule that specs and plans are ephemeral and their knowledge folds into durable docs
first — **unless another live item shares the spec**. That is real:
`specs/2026-07-26-poly-surface-verbs.md` is cited 11 times and covers a done item, a to-plan item
and three open questions; same shape for four more specs. **A shared spec belongs to the item whose
work it last covers**; earlier items link it by slug and delete nothing.

### 3.9 `bin/board`

Bash, `set -euo pipefail`, matching `bin/test`/`bin/uedcli`. **No venv** — `bin/_venv.sh` hard-fails
without python3.12, far too heavy for a board query.

| Command | Does
|-----------------------|---
| `questions` | open questions (file present, `## Answer` empty), by item
| `answered` | questions with a non-empty answer — the fold-out queue
| `ls [<stage>] [--json]` | items, sorted by priority (`p?` last) then slug; `--json` because this is the triage scan and an agent consumes it
| `show <slug>` | resolve a slug to its current path
| `new <stage> <title>` | create an item with a **test-passing** stub: slug from the title, `summary` from the title, `kind`/`priority` defaulting to `unknown`/`p?`

`new` exists because capture must stay cheap; `CLAUDE.md` routes every logged review finding through
it. **It refuses to overwrite an existing directory** (`mkdir` without `-p`, which is atomic), so two
concurrent sessions cannot silently clobber each other — the loser is told and picks another slug.

**A malformed item is reported and skipped, not fatal** — `bin/board show <other-slug>` must not fail
because some third item is mid-write in a concurrent session. Exit 2 only when the command's *own*
request cannot be satisfied (unknown stage, unknown slug), naming the value. Human counts to stderr.
Tested in `uedcli/tests/test_board_script.py`, including an **agreement test** pinning its bash
frontmatter reader to `tomllib`.

### 3.10 Structure with nowhere obvious to go

| What | Where
|---|---
| 14 HTML provenance banners in `inbox.md` | a one-line `**Provenance:**` in each affected item's body
| 8 `###` headings in `inbox.md`, 6 in `someday.md`, 3 `##` in `someday.md`, `## Needs a spec` + `## Backlog — active` in `to-spec.md`, 4 prose-only `##` sections in `to-build.md` | where the heading *is* the item, it becomes one; where it carries prose but no items, the prose moves into the nearest item or its own item; a bare category is dropped and recorded in the inventory
| `## Partially done` and the 13 `[~]` / 25 `[x]` markers in `done.md` | a `**Remnants:**` body line
| positional and cross-file references — "the item above", "see the item in `inbox.md`" — ~21 sites in `inbox.md`, plus `to-spec.md` and `done.md` | **rule, not a list:** every intra-board reference is repointed to a slug; the inventory enumerates them
| the `(also in to-build.md #N)` cross-noting convention | documented but has **zero** live instances; drop the convention

`to-spec.md` has **no Deferred section** (only `## Needs a spec` and `## Backlog — active`), so there
is no Active/Deferred re-triage to perform — the claim in `board/README.md` and `CLAUDE.md` is stale.

### 3.11 What counts as an item

"Each bullet is one item" is false. `to-build.md`: 3 of its 7 bullets are its own navigation list,
two real items are `##` sections with no bullet, and 4 more `##` sections are prose. `inbox.md`
carries a 4-bullet navigation list at lines 690-693, orphaned ~684 lines below the sentence that
introduces it. So the migration's **first pass is an inventory** classifying every line as *item*,
*detail*, *heading*, or *navigation prose*; it is reviewed before any directory is created. The
per-file bullet counts are its input, not its answer.

---

## 4. Migration

**Scope at `e7d518c`:** 488 naive bullets (inbox 293, to-spec 55, to-spike 3, to-plan 8, to-build 7,
someday 27, done 94) — real count from the inventory — plus 2 handoffs, **71 specs**, **26 plans**.

1. **No item's text is lost.**
2. **The only permitted edits** — rule 1 is otherwise read as absolute: re-base relative links
   (rule 5); repoint intra-board references to slugs (§3.10); path citations → slug citations
   (rule 8); map the 43 tag spellings to six kinds (§3.4); author a slug and a `summary` (§3.3).
3. **Priority copied, never invented** — reading all spellings. None ⇒ `p?`.
4. **Every item converts in its current stage**, except the three items §2.13 names.
5. **Relative links are re-based.** Items drop two levels deeper; specs move tree. **46 markdown
   links in board files** (which redden the suite immediately, since `overview.md` is not exempt) and
   **92 `../` links across 42 spec/plan files**. Plus **30 same-directory spec↔spec links across 9
   files**, which a prefix re-base cannot fix — those become slug references.
6. **The 70 owner-blocking entries become question files**, else `bin/board questions` is empty on
   day one and the change fails at its purpose. An entry not attached to a buildable item becomes an
   item whose `overview.md` states the topic and whose `questions/` holds the question.
7. **A spec or plan with no board item** gets an item directory. **18 of the 97 have no board
   mention** — including `2026-07-18-package-schema-cache.md`, cited live from `uedcli/config.py`.
   For one whose work already shipped, §3.8's completion rule wins over this rule: it lands in
   `done/` and its `spec.md` is deleted — **unless a source file cites it**, in which case the
   citation is repointed to a durable doc first. This covers `HANDOFF-native-full-parity.md`
   (SUPERSEDED, no owning item).
8. **The 401 path citations become slug citations**, except where §4.1 forbids the edit.
9. **`dev/docs/specs/` and `dev/docs/plans/` are removed once empty** — no stub, no forwarding note.
10. **Then the stale list is proposed in bulk** (§2.7).

### 4.1 Fallout

**76 tracked files outside the board reference a board path**
(`git grep -l -E 'board/(inbox|to-spec|to-spike|to-plan|to-build|someday|done)\.md|board/HANDOFF-' -- . ':!dev/docs/board/*' | wc -l`).

| What | Needs
|---|---
| `test_doc_links.py` `_on_deck()` | Reads `to-build.md` as a file and **fails open** if absent — every ephemeral doc would go unchecked. Delete it: with specs/plans gone the exemption is a path shape, not a prefix. It has a **second call site** in `test_no_citation_of_a_deleted_doc` (currently inert — both named docs still exist); state that function's new exemption too.
| `_EPHEMERAL` | Changes from a `startswith` prefix tuple to a shape test. **New value, stated:** `board/*/*/spec.md` and `board/*/*/plan.md` are exempt **except** under `to-build/` — preserving today's boundary. `overview.md`, `handoff.md` and question files are checked in every stage.
| **`dev/docs/decisions.md`** | **Blocker.** It is FROZEN, and it carries two *markdown links* into `dev/docs/specs/` (lines 8, 7286) which rule 9 deletes — so the suite reddens and the file may not be edited. Resolution: exempt those two links in `test_doc_links.py` (a code change, not a doc edit). Its 26 board-path citations are prose and no check covers them; leave them.
| **`dev/docs/2026-06-20-open-questions-for-andrzej.md`** | The owner's — *do not touch*. 2 prose refs, no markdown links, so nothing reddens.
| **suite scale** | `_checked_docs()` is **270** docs × 3 parametrized tests = 810 cases (822 collected). After: ~820 docs → ~2,460 cases, ~3×. `_anchors()` re-reads targets uncached — memoise if it slows materially. Measure before/after.
| `CLAUDE.md` | 7 `inbox.md` mentions; the tag≈queue rule (§2.11 retires it); the bounce-to-inbox rule (§2.13 replaces it); **and lines 639, 641, 653**, which describe `specs/`+`plans/` as living trees.
| **`CLAUDE.md` round-2 trigger** | It excludes `dev/docs/board/*` from "the artifact". Once specs live under the board, **every spec and plan round would lose its round 2.** Narrow the exclusion to `board/*/*/overview.md` and `board/*/*/questions/` — and §3.2 forbids logging a finding to any other file, closing the residual hole.
| `dev/docs/README.md` | Board rows 36-40; **line 34** (the `specs/`+`plans/` row rule 9 invalidates); **lines 74-77** (the flow described a second time).
| `board/README.md` | Full rewrite.
| `architecture.md` (9 refs), `unrealed/*.md` (4 files), `rationale/*.md` (4 files, `userdocs.md` uses **markdown** links so it reddens), **`dev/docs/reviews/`** | repoint to slugs
| **17 spike files** (board paths) / 30 (spec paths) | repoint to slugs
| `uedcli/*.py` (8), `uedcli/tests/*` (5), **`uned/*`** (4, incl. a `.sh`), **`uedcli-native/src/{bspcsg,light,zones}.rs`** | repoint. One `.rs` citation is line-wrapped across two source lines — a line-oriented rewrite mangles it.
| `dev/docs/specs/` (21) + `dev/docs/plans/` (9) | they cite board paths too, and move with their items
| `direction/process.md` | the owner's tree — §5

**§7's done-when therefore names two exceptions** rather than claiming no file references a deleted
path.

### 4.2 Concurrency — not a worktree

`CLAUDE.md` says a feature is built in a worktree and squash-merged. **Unsafe here:** 35% of recent
commits touch `inbox.md`; a worktree that deletes it and merges days later hits a modify/delete
conflict whose obvious resolution discards every item added meanwhile — including review findings.

**Protocol:** run on the base branch in committed batches, one stage at a time, smallest first
(`to-spike` → `to-build` → `to-plan` → `someday` → `to-spec` → `done` → `inbox`), so a file is
half-migrated for minutes, not days. Two hard orderings, because other sessions read `CLAUDE.md`,
not chat:

- **`bin/board new` ships before the inbox batch** — otherwise a session that must log a finding
  during the window has no sanctioned path, and an unlogged finding blocks its round.
- **The commit that deletes `inbox.md` also repoints `CLAUDE.md`** — otherwise sessions keep being
  told to append to a deleted file.

**This is an exception to the owner's worktree rule**, proposed in §5, not taken.

### 4.3 Not

Not a re-triage (except §2.13's three items). Not a cleanup — stale items convert as they are. No
`uedcli` behaviour change.

---

## 5. Parked for the owner

Both live on `board/inbox.md` as `[OWNER — confirm]`, verbatim, because this spec is ephemeral.

**(A) `direction/process.md`** — replacing only the final sentence of the "Nothing load-bearing lives
only in chat" bullet (from "The board is a set…" on line 53), staying inside the bullet:

> The board is a set of stages named for the *next action* an item needs, and **each work item is a
> directory** whose stage is the directory it sits in, so advancing it is a single `git mv`. An item
> is referenced by its **slug**, never its path, because the path encodes the stage. **A question
> file is a blocker** — answered by writing into its empty `## Answer`, and it is **deleting** it,
> after the decision reaches its durable home, that unblocks the item. Work judged stale is shelved,
> never deleted, and the shelving list is confirmed in bulk.

Mechanics (stage names, frontmatter, `bin/board`) stay in `CLAUDE.md` and `board/README.md`:
`process.md` says of itself that operative procedure lives there.

**(B) The worktree exception** of §4.2.

**(C) §2.14, succinctness** — proposed for `direction/process.md`:

> Docs, docstrings and comments are as succinct as the meaning allows — facts, not bloat; length is
> earned by what must be explained. A reviewer flags any doc they cannot fully understand, or that
> is ambiguous.

---

## 6. Durable homes

- **§2** → `direction/process.md` (§5) plus format choices in `board/README.md` and `CLAUDE.md`.
  Every `Rejected` line travels with them.
- **§3** → a new **`dev/docs/rationale/board.md`**: the TOML choice, slug derivation and the
  pruning rule, `.gitkeep`, `bin/board`'s scope and no-venv choice, the widened link-test boundary,
  gate-on-absence, and the batched migration protocol — each with `Rejected` and `Refs`.

---

## 7. Open questions

**Q1** the stale list — deferred to the end by §2.7. **Q2** the worktree exception — parked (§5B).
**Q3** succinctness wording — parked (§5C).

---

## 8. Done-when

- [ ] Eight stage directories with `.gitkeep`; the seven board files and both handoffs gone.
- [ ] The inventory (§3.11) is recorded; every item it found is a directory with parsing frontmatter.
- [ ] `dev/docs/specs/` and `dev/docs/plans/` empty and removed; all 71 specs and 26 plans placed or
      accounted for by rule 7.
- [ ] The 70 owner-blocking entries are question files; `bin/board questions` lists them.
- [ ] The three items of §2.13 sit in `to-spec/`.
- [ ] `test_board.py` passes, including gate 8 and the slug-reference check over `.rs`.
- [ ] `bin/board` works, with tests including the bash↔`tomllib` agreement test.
- [ ] The 401 path citations are slug citations, except `decisions.md` and
      `2026-06-20-open-questions-for-andrzej.md`.
- [ ] `CLAUDE.md`'s round-2 exclusion is narrowed; its lines 639/641/653 updated.
- [ ] The two `decisions.md` markdown links are exempted in `test_doc_links.py`.
- [ ] `board/README.md`, `dev/docs/README.md`, `CLAUDE.md`, `architecture.md`, `unrealed/*`,
      `rationale/*`, `reviews/*`, the spikes, and the Python/shell/Rust sources describe the new
      shape. **No tracked file except `decisions.md` (frozen) and `2026-06-20-open-questions-for-andrzej.md`
      (the owner's) references a deleted board path.**
- [ ] `dev/docs/rationale/board.md` exists (§6).
- [ ] §5's three parked items are confirmed and applied, or still parked.
- [ ] `bin/test` green; suite runtime change measured and recorded.
- [ ] The stale list is proposed in bulk (§2.7).
