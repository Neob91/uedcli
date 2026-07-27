# Spec — the board becomes one directory per work item

**Belongs to** board item `the-board-becomes-one-directory-per-work-item`. **Owner decisions:** §2 (implemented as
given). **Agent decisions:** §3, durable home in §6.

**Measurements are pinned to HEAD at writing (`1969b0c`), which includes this spec itself** — so the
71 specs and 97 spec+plan files below count this file. The board moves ~35 lines/day; re-measure at
execution. Every non-obvious figure carries the command that produced it: without them the earlier
draft's numbers rotted unnoticed.

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

**Why.** Three measured problems:

1. **Reads.** `board/inbox/` is 356,795 bytes / 4,042 lines / 293 bullets; the board is 7,173 lines.
2. **Write collisions.** 49 of 140 commits in three days touched `board/inbox/` (35%). Sessions share
   this repo and every review round logs findings there.
3. **Questions are invisible.** 62 entries wait on the owner, in 15 tag spellings (§3.4).

**Honest cost.** The write-collision fix is permanent. The read picture is mixed, in both directions:

- Fetching one item gets ~350× cheaper.
- **Triage gets worse in call count, better in bytes.** Today it is one 357 KB read; after, it is
  one `bin/board ls` (~35 KB, a 10× byte reduction) **plus a read of every item you must actually
  judge**. Board titles today are substantial — median 79 characters, 231 of 471 over 80 — so a
  one-line summary will often not be enough to triage on.
- **This depends on ~490 accurate one-line summaries that do not exist yet.** Writing them is
  plausibly the largest hand-labour item in the migration (§4 rule 2, §8).

**What it unlocks.** An agent drafts `spec.md` and parks each unresolved fork as a question file.
The owner walks the files and writes an answer in each.

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
to its durable home (`direction/` for the owner's, `rationale/` for an agent's), `spec.md` is
updated, the question file deleted.
*Rejected:* keeping answered files (accumulates dead questions).

**2.4 — Priority lives in the header, not the directory name.** A rename breaks links.
*Rejected:* a `p1-` name prefix (free sorting, but re-prioritising renames).

**2.5 — The header carries a SHORT description; detail goes in the body.**

**2.6 — Stale items go to `board/stale/`; removal deferred.** Nothing is deleted by this change.

**2.7 — The stale list is proposed at the END, in bulk.** Convert everything in place first;
`stale/` stays empty until the list returns confirmed.
*Rejected:* an agent applying a staleness rule unilaterally.

**2.8 — The build queue keeps the name `to-build`.**
*Rejected:* `ready-to-build` — the only stage not named `to-<verb>`.

**2.9 — Specs and plans live in the item directory; everything references an item by SLUG, never by
path.** *Resolves a structural finding:* 86 files cite a spec or plan by path across 401 lines, 76
durable. An item's path contains its stage, so path citations would break on every `git mv` and the
repoint would touch shared files — destroying the disjoint-paths win.
*Rejected:* specs/plans stay put and are linked (nothing breaks, but the item is not self-contained
and two trees stay alive); a stage-free address (nothing breaks, but `ls to-build/` stops being the
queue and advancing becomes a file edit).

**2.10 — The header is TOML frontmatter, delimited `+++`.** Ruled 2026-07-27, replacing an earlier
YAML ruling whose stated premise was false. The premise was that the test would be *a parser call*;
what is false is that a parser is **available** — this repo has none (`pyproject.toml`:
`dependencies = ["Pillow>=11]`; `bin/_venv.sh`: `_DEPS_SPEC="Pillow>=11 pytest>=8,<9"`), so YAML
costs a second third-party dependency for a docs format. `tomllib` is stdlib on the repo's Python
3.12, and TOML is already a house format (`uedcli.toml` via `config.py`).

TOML does **not** remove the string hazard, it trades it: instead of the 97 titles starting with a
backtick, 61 containing `: ` and 12 containing ` #` that break an unquoted YAML scalar, TOML needs
one mechanical escape for the 19 titles containing `"` (§3.4).
*Rejected:* YAML + a PyYAML dependency; a YAML-shaped subset (a trap for an author who assumes real
YAML); a `·`-separated line (`·` occurs 48 times in board prose; lists read badly in it).

**2.11 — `[spec]`, `[plan]` and `[spike]` are not kinds.** *"Why do we need [spec] or [plan]? Each
issue gets a plan."* Kinds are what the pipeline cannot infer: **`implement`, `chore`, `debug`,
`docs`, `owner-question`, `unknown`**.
*Rejected:* keeping them as pre-triage routing hints; keeping all existing spellings.

**2.12 — An item records its dependencies.** On another item: **its slug** (a path breaks on every
advance). On a spike: a **repo-root-relative path** (`dev/docs/spikes/` never moves).

**2.13 — An item ALREADY IN `to-plan/` OR `to-build/` that gains a blocking question moves back to
`to-spec/`.** It replaces today's bounce-*to-inbox* rule, stopping one stage earlier so finished
spec work is not shelved. **Scope matters:** an item in `inbox/`, `someday/`, `stale/` or `done/`
that has a question file does **not** move — otherwise §4 rule 6, which turns ~62 inbox entries into
question files, would relocate the whole inbox. At migration this affects three items (§4 rule 4),
subject to the attribution rule in §4 rule 6.
*Rejected:* gating only post-migration items (the most important blocked items would sit in the
build queue looking ready); keeping the question as a separate inbox entry (the item's own directory
would not show it is blocked).

**2.14 — Docs, docstrings and comments are as succinct as the meaning allows.** Facts, not bloat;
length is earned by what must be explained. **A reviewer flags any doc they cannot fully understand,
or that is ambiguous.** Repo-wide. Already written into `CLAUDE.md`; the `direction/` wording is
parked (§5).

**2.15 — The migration runs on the base branch in committed batches, not in a worktree.** Ruled
2026-07-27 with the counter-argument on the table: a worktree's failure is a *loud* modify/delete
conflict, while the base branch's is *silent* — the commit that removes `board/inbox/` cleanly discards
whatever another session committed meanwhile, and destroys their uncommitted on-disk edits, with
nothing in `git status` afterwards. **That risk is accepted**, and the mitigation offered alongside
it (a re-diff-before-delete reconciliation step) was declined. Batches keep the window to minutes;
§4.2 gives the order.
*Rejected:* a worktree plus a board freeze; base-branch batches with a reconciliation step.

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
no such convention exists today (`git ls-files | grep -ic gitkeep` → 0). `board/README.md` stays the
single prose file.

### 3.2 The item directory

`overview.md` is the only required file — six lines is legitimate for an inbox note. The only
permitted subdirectory is `questions/`. Extra `.md` files are free.

**A logged review finding becomes a NEW item** (`bin/board new inbox …`), as `CLAUDE.md` already
requires — it is not appended to the reviewed item. It therefore lands in that new item's
`overview.md`, never in a free-form extra file, which is what closes the round-2-trigger hole in
§4.1.

The two `HANDOFF-*.md` files become `handoff.md` in their items. Spike evidence stays in
`dev/docs/spikes/` — durable, cited from `architecture.md`, outlives the item.

### 3.3 Slugs and the reference rule

**The slug is the item's permanent identity**: kebab-case, unique board-wide, never renamed.

- **The migration WRITES a short slug.** It does not mechanically derive one and truncate: 359 of
  471 titles exceed 48 characters, so truncation produces permanent identities cut mid-phrase
  (`architecture-md-contradicts`). Authoring a slug is one of §4 rule 2's permitted edits.
- **Strip any leading `[tag]` and `pN` first.** 168 titles carry one; without stripping the slug
  bakes in a priority and an abolished kind, defeating §2.4 and §2.11.
- **16 top-level bullets have no bold title at all** (`inbox.md:2935, 2942, 2999, 3012, 3150, 3594,
  3601, 3610, 3617, 3632, 3640, 3655, 3661, 3696, 3708` +1). Their slug and H1 come from the first
  sentence of the body.
- **Collisions: the author picks a distinguishing slug** — there is no `-2` suffix. Hand-written
  short slugs collide readily where mechanical full-length ones do not: shortening to the first
  three words gives 16 colliding groups over 37 items, including
  `per-surface-texture-verbs` (a `done/` item and a `to-plan/` item that are genuinely different
  work) and `the-unified-asset-catalog`. A numeric suffix would give one of them a meaningless
  permanent name.

**The reference rule.** Nothing outside an item directory writes a path into one. A code comment, a
durable doc, a spike, another item's frontmatter all say ``board item `<slug>` ``.

- **Exact form:** the literal `board item` / `board items` followed by one or more backticked slugs,
  comma-separated. The phrase already occurs 75 times in the tree across 34 files, almost always
  bare; the backticks are what make it a reference.
- **Scanned suffixes:** `.md .py .sh .toml .rs`. `.rs` is **in** — three Rust files
  (`bspcsg.rs`, `light.rs`, `zones.rs`) cite the board today and the existing checker's `_tracked()`
  excludes them. One of those citations is line-wrapped across two source lines; a line-oriented
  rewrite mangles it.
- **Exemptions, required.** The docs that *define* the form must write it. `board/README.md`,
  `CLAUDE.md`, `dev/docs/rationale/board.md` and the test module are exempt, as
  `test_doc_links.py`'s `_MAY_NAME_DELETED` already does for the same class of problem. One live
  counter-example existed: the plan in board item `csg-order-control-actor-order-actor-add-order`
  wrote the phrase followed by a backticked *filename* rather than a slug. It has since been
  reworded.
- **Test 9 (§3.7) asserts every reference resolves** — a path citation into `specs/` rots silently
  today; a dangling slug reddens the suite.

**`done/` is pruned** — `CLAUDE.md` and `board/README.md` both say it keeps only a short tail. A
slug is therefore **not** reserved forever. **Pruning a done item is legal only when nothing cites
it**, which test 9 enforces; otherwise the citation would resolve to a later item reusing the name.

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
| `summary` | yes | one line, non-empty
| `depends-on` | no | item **slugs**
| `spikes` | no | repo-root-relative paths

No other key. Frontmatter that fails to parse is a **test failure**; `bin/board` reports it against
that item and continues with the rest (§3.9).

**The TOML subset is pinned, so a bash reader can be simple and the agreement test has a contract:**
single-line **basic** strings (`"…"`) only — no literal strings, no `"""` multi-line, no comments,
one array per line, `key = "value"` spacing. The only escapes are `"` → `\"` and `\` → `\\`. Test 4
enforces the subset, not just TOML validity. **19 titles contain a `"`** (`Two different UIs for
"read a T3D from file-or-stdin".`), so `bin/board new` must apply the escape — without it the first
capture reddens the suite.

**`p?` is legal everywhere.** 181 items carry no priority in any spelling, 122 outside the inbox
(`done` 93 alone); restricting `p?` would make the migration impossible to complete.

**Read every priority spelling.** Only 82 of 293 inbox bullets use `` `p1` ``; 234 carry one once
`**[debug] p3 …**`, `` `p2 [tag]` `` and trailing `p1.` are counted. Reading only the backticked
form would silently downgrade 152 prioritised items.

**Kind mapping.** The census
(`grep -h '^- ' *.md | grep -oE '\[[A-Za-z][^]]*\]' | sort | uniq -c | sort -rn`) returns 43 rows,
of which **three are not tags** — `[x]` (a checkbox), `[inbox.md]` and `[to-spec.md]` (link labels)
— leaving 40 real spellings.

| Existing | → kind
|---|---
| `[implement]` `[build]` `[implement?]` | `implement`
| `[chore]` `[chore/bug]` `[chore/flag]` `[process/flag]` | `chore`
| `[debug]` `[debug?]` `[debug/perf]` `[finding]` | `debug`
| `[docs]` `[note]` | `docs`
| `[OWNER — confirm]` `[OWNER — decide]` `[OWNER — review]` `[ANDRZEJ — decide]` `[FLAG-FOR-ANDRZEJ]` `[decide]` `[flag]` `[flag for Andrzej]` `[flag→Andrzej]` `[question]` | `owner-question`
| `[spec]` `[spike]` `[plan]` `[verify live]` | dropped (§2.11); the item keeps the kind of *work* it is, else `unknown`
| `[resolved …]` `[RESOLVED → …]` `[DECISION-MADE / …]` | stale-list candidate
| no tag — 113 items, 91 in `done/` | `unknown`

**A compound claimed by two rows resolves to `owner-question`** — `[spec→plan / FLAG-FOR-ANDRZEJ]`,
`[flag→Andrzej / spike→spec]`, `[flag→Andrzej + spike]` are owner questions that also note a stage;
the stage half is dropped per §2.11.

Applying the mapping is a rewording; §4 rule 2 permits it. **`[OWNER — confirm]` keeps that exact
spelling in the item's title**, because `CLAUDE.md` mandates the string; `kind` is an addition.

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
  ignoring HTML comments. A `?` or `TBD` **is** content.
- **Reopening.** If the owner's answer is itself a question, the agent appends its reply under
  `## Answer` and adds `## Reopened` — `bin/board answered` skips a file with a `## Reopened`
  section later than its answer, so it leaves the fold-out queue without anyone erasing the owner's
  words.
- **Where the answer would change a `direction/` doc, the file also carries the proposed replacement
  text**, succinct, so answering settles the decision and approves the wording in one pass.
  Otherwise `CLAUDE.md`'s "propose the exact text and wait" makes it two round trips. This is the
  minority case, not the norm.
- **A question needing a measurement** moves the item to `to-spike/` and **the question file is
  deleted**, its text carried into the spike's brief. Left in place it survives the spike and
  reddens test 8 the moment the item reaches `to-plan/`.

### 3.6 The gate

**An item with any question file may not sit in `to-plan/` or `to-build/`** (§2.2: "built or
planned"). `to-spec/` is not gated — drafting a spec is how questions are found.

**The gate keys on the file being GONE, not on the answer being present.** Otherwise typing an
answer would unblock the item before any durable doc recorded the decision. Folding out and deleting
is what unblocks, making the durable write a precondition of planning.

`bin/board answered` lists questions with a non-empty `## Answer` and no later `## Reopened`: the
agent's fold-out queue, and the only way an agent learns answers are waiting. **`CLAUDE.md` must
tell agents to run it** — at session start and before pulling work off `to-build/` — or the owner
answers into files nobody reads (§4.1).

**Fold-out is claimed by the deleting commit.** The commit that writes the decision to its durable
home also deletes the question file; a session that finds the file already gone stops. Without this
two sessions can fold the same answer into `direction/` twice.

A question **mooted** by another answer is deleted with a one-line note in `overview.md` naming the
**durable doc** that now carries the mooting decision (not the answer file, which is deleted).

### 3.7 `uedcli/tests/test_board.py`

The path matters: `pytest.ini` sets `testpaths = uedcli` and `bin/test` runs `pytest uedcli`, so a
test elsewhere never runs.

1. `board/` holds exactly the eight stages plus `README.md`; each stage has a `.gitkeep`.
2. Each stage holds only directories (plus `.gitkeep`).
3. Each item has `overview.md`; no subdirectory but `questions/`.
4. Frontmatter parses via `tomllib` **and conforms to §3.4's subset**; three required keys; no key
   outside §3.4; `priority` and `kind` in range; `summary` non-empty and single-line.
5. `depends-on` slugs resolve; `spikes` paths exist; **no dependency cycle**; a `to-build/` item may
   not depend on a `stale/` item.
6. Slugs unique board-wide.
7. Every question file has `## Context` and `## Answer`.
8. No item under `to-plan/` or `to-build/` has any question file (§3.6 — absence, so no emptiness
   parsing and a malformed file cannot fool it).
9. Every ``board item `<slug>` `` reference in tracked `.md .py .sh .toml .rs` resolves, outside
   §3.3's exemption list.

**Landing order matters, because §2.15 migrates one stage per batch.** From the first batch to the
last, `board/` holds stage directories *and* leftover `.md` files — which assertions 1 and 2 forbid.
So **3–9 land with the scaffold** (they are per-item and true from the first converted item) and
**1–2 land in the final commit**. `direction/process.md` forbids leaving a test red.

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
board item `the-per-surface-verb-split` is cited 11 times and covers a done item, a to-plan item
and open questions; four more specs have the same shape. **A shared spec is deleted only when every
item citing it is in `done/` or `stale/`**; until then it lives with the least-advanced live item
and the others link it by slug.

### 3.9 `bin/board`

Bash, `set -euo pipefail`, matching `bin/test`/`bin/uedcli`. **No venv** — `bin/_venv.sh` hard-fails
without python3.12 (and there is no system `python3` on this machine at all), far too heavy for a
board query. Its frontmatter reader handles only §3.4's pinned subset.

| Command | Does
|-----------------------|---
| `questions` | open questions, by item
| `answered` | answered, not-reopened questions — the fold-out queue
| `ls [<stage>] [--json]` | items sorted by priority (`p?` last) then slug; `--json` because this is the triage scan and an agent consumes it
| `show <slug>` | resolve a slug to its current path
| `new <stage> <title>` | create an item with a **test-passing** stub: authored slug, `summary` from the title with §3.4's escaping applied, `kind`/`priority` defaulting to `unknown`/`p?`

`new` exists because capture must stay cheap; `CLAUDE.md` routes every logged review finding through
it (§4.1). **It checks all eight stages for the slug before creating** — `mkdir` without `-p` is
atomic and stops a same-stage race, but slug uniqueness is board-wide (test 6), so a same-stage
check alone would redden the suite for whoever ran next.

`--json` escaping must survive the same hostile strings as the frontmatter (quotes, backslashes).
**A malformed item is reported and skipped, not fatal** — `bin/board show <other-slug>` must not fail
because a third item is mid-write in a concurrent session. Exit 2 only when the command's *own*
request cannot be satisfied (unknown stage, unknown slug), naming the value. Human counts to stderr.
Tested in `uedcli/tests/test_board_script.py`, including an **agreement test** running the bash
reader and `tomllib` over every real `overview.md` plus a fixture set covering each escape.

### 3.10 Structure with nowhere obvious to go

| What | Where
|---|---
| 14 HTML provenance banners in `board/inbox/` | a one-line `**Provenance:**` in each affected item's body
| headings: 8 `###` + `## From the 2026-07-18 unattended build chain` in `board/inbox/`; 6 `###` + 3 `##` in `board/someday/`; `## Needs a spec` + `## Backlog — active` in `board/to-spec/`; `## Partially done` + `## Done` in `board/done/`; 4 prose-only `##` in `board/to-build/` | a heading that *is* an item becomes one; a heading carrying prose becomes **its own item** (not merged into a neighbour — `to-build.md:193`'s neighbours are unrelated to it and to each other); a bare category is dropped and recorded in the inventory
| the 25 `[x]` / 17 `[~]` markers in `board/done/` | a `**Remnants:**` body line
| **6 top-level blockquotes, 22 lines** — `to-build.md:100-105` (**"DO NOT START THIS"**, the only record that the unified-asset-catalog item is not buildable), `to-plan.md:49, 61, 155`, `to-spec.md:131`, `inbox.md:1934` | the `to-build` banner becomes body text of its item; the three `to-plan` pointers are live cross-notes and become `depends-on`/body slug references
| positional and cross-file references — "the item above", "see the item in `board/inbox/`" | **rule, not a list:** every intra-board reference is repointed to a slug; the inventory enumerates them

The literal `(also in to-build.md #N)` spelling has **zero** live instances, but the *practice* is
alive in the three `board/to-plan/` blockquote pointers above — so the convention is replaced by slug
references, not simply dropped.

`board/to-spec/` has **no Deferred section** (only `## Needs a spec` and `## Backlog — active`); the
claim in `board/README.md` and `CLAUDE.md` is stale, and there is no Active/Deferred re-triage.

### 3.11 What counts as an item

"Each bullet is one item" is false. `board/to-build/`: 3 of its 7 bullets are its own navigation list,
two real items are `##` sections with no bullet, 4 more `##` sections are prose. `board/inbox/` carries
a 4-bullet navigation list at **lines 657-660**, orphaned ~650 lines below the sentence at line 7
that introduces it — cite it by its text, not its coordinates, because lines 690-693 are four `p1`
owner items that a literal reading would delete.

So the migration's **first pass is an inventory** classifying every line as *item*, *detail*,
*heading*, *blockquote* or *navigation prose*, reviewed before any directory is created. The
per-file bullet counts are its input, not its answer.

---

## 4. Migration

**Scope:** 487 naive bullets (inbox 293, to-spec 55, to-spike 3, to-plan 8, to-build 7, someday 27,
done 94) — real count from the inventory — plus 2 handoffs, **71 specs**, **26 plans**.

1. **No item's text is lost.**
2. **The only permitted edits:** re-base relative links (rule 5); repoint intra-board references to
   slugs (§3.10); path citations → slug citations (rule 8); map the 40 tag spellings to six kinds
   (§3.4); **author a slug and a one-line `summary` for every item** (~490 of them — the largest
   hand-labour item here, and the thing `bin/board ls` depends on).
3. **Priority copied, never invented** — all spellings. None ⇒ `p?`.
4. **Every item converts in its current stage**, except items §2.13 moves.
5. **Relative links are re-based.** Items drop two levels deeper; specs move tree. **45 markdown
   links in board files** (which redden the suite immediately — `overview.md` is not exempt) and
   **92 `../` links across 42 spec/plan files**. Plus **30 same-directory spec↔spec links across 9
   files**, which a prefix re-base cannot fix — those become slug references.
6. **The 62 owner-blocking entries become question files.** **Attribution rule:** an entry becomes a
   question file on item X only where its own text names X's work as blocked; otherwise it becomes a
   standalone `owner-question` item in `inbox/`. This decides which items §2.13 demotes, so it is
   not left to judgement — e.g. `to-plan.md:68-72` names two blockers for `poly-surface-verbs` and a
   third that "affects step 1", which is **done**, so it does not demote the to-plan item.
7. **A spec or plan with no board item** gets an item directory. **18 of the 97 have no board
   mention**, including board item `package-schema-cache`, cited live from `uedcli/config.py:260`.
   Where the work already shipped it lands in `done/` and §3.8's deletion applies — **unless a
   source file cites it**, in which case the citation is first repointed to the durable doc that
   owns that fact (`architecture.md`, `unrealed/*.md` or a `rationale/` topic), named per case in
   the inventory. Covers `HANDOFF-native-full-parity.md` (SUPERSEDED, no owning item).
8. **The 401 path citations become slug citations**, except where §4.1 forbids the edit.
9. **`dev/docs/specs/` and `dev/docs/plans/` are removed once empty** — no stub, no forwarding note.
10. **Then the stale list is proposed in bulk** (§2.7).

### 4.1 Fallout

Two censuses are needed, because the obvious one misses bare filenames:

```
git grep -l -E 'board/(inbox|to-spec|to-spike|to-plan|to-build|someday|done)\.md|board/HANDOFF-' \
    -- . ':!dev/docs/board/*'                                              # 76 files, path-prefixed
git grep -lE '(^|[^/])`?(inbox|to-spec|to-spike|to-plan|to-build|someday|done)\.md' \
    -- . ':!dev/docs/board/*'                                              # 55 more, bare-name
```

The bare-name set adds **33 files the first census cannot see**, including the **repo-root
`README.md`**, which describes the whole flow by filename.

| What | Needs
|---|---
| `test_doc_links.py` `_on_deck()` | Reads `board/to-build/` as a file and **fails open** if absent — every ephemeral doc would go unchecked. Delete it **in the `to-build` batch commit**, not later, or the exemption is silently wide for five batches. It has a **second call site** in `test_no_citation_of_a_deleted_doc`, which must take the same shape-based exemption; that test is currently inert (both docs it names still exist), so a green suite will not catch getting it wrong.
| `_EPHEMERAL` | Becomes a shape test: `board/*/*/spec.md` and `board/*/*/plan.md` exempt **except** under `to-build/`. **This NARROWS coverage and the spec must say so:** today's boundary is "linked from `board/to-build/`", which covers 15 ephemeral files, and §2.13 moves `unified-asset-catalog` and `actor-preview-faces` out of `to-build/` — so **7 currently-checked files lose checking, invisibly**. §8 pins the before/after list.
| **`dev/docs/decisions.md`** | FROZEN, and carries two *markdown links* into `dev/docs/specs/` (lines 8, 7286) that rule 9 deletes — the suite reddens and the file may not be edited. Exempt those two links in `test_doc_links.py` (a code change, not a doc edit). Its 26 board-path citations are prose; leave them.
| **`dev/docs/2026-06-20-open-questions-for-andrzej.md`** | The owner's — *do not touch*. 2 prose refs, no markdown links, so nothing reddens.
| `dev/docs/rationale/MIGRATION.md` | markdown links into `../plans/` and `../specs/` (lines 7-8) — reddens; repoint.
| **suite scale** | `_checked_docs()` is **270** docs × 3 parametrized tests = 810 of 822 collected. After: ~820 docs → ~2,460 cases. `_anchors()` re-reads targets uncached — memoise if it slows. Measure before/after.
| `CLAUDE.md` — **cite by text, not line number**, since this change edits the file | the 7 `board/inbox/` mentions; the tag≈queue rule (§2.11 retires it); the bounce-to-inbox rule (§2.13 replaces it); the **"`specs/` + `plans/`" bullet** and the **"`dev/docs/specs/` and `dev/docs/plans/` are ephemeral"** paragraph; **route logged findings through `bin/board new`**; **tell agents to run `bin/board answered`** (§3.6 — without this the owner's answers are never read); **rewrite the `[OWNER — confirm]` parking rule**, which currently mandates parking on `board/inbox/`
| **`CLAUDE.md` round-2 trigger** | It excludes `dev/docs/board/*` from "the artifact", so once specs live under the board **every spec and plan round loses its round 2**. Narrow the exclusion to `board/*/*/overview.md` and `board/*/*/questions/`; §3.2 keeps findings out of any other file, closing the hole.
| `dev/docs/README.md` | board rows 36-40; **line 34** (the `specs/`+`plans/` row rule 9 invalidates); **lines 74-77** (the flow described a second time).
| **repo-root `README.md`** | describes the flow by filename; invisible to the first census.
| `board/README.md` | Full rewrite.
| `architecture.md` (9 refs), `unrealed/*.md` (4 files), `rationale/*.md` (4), `dev/docs/reviews/` | repoint to slugs
| **17 spike files** (board paths); **30** (spec paths) | repoint to slugs
| `uedcli/*.py` (8), `uedcli/tests/*` (5), `uned/*` (4, incl. a `.sh`), `uedcli-native/src/{bspcsg,light,zones}.rs` | repoint
| `dev/docs/specs/` (21) + `dev/docs/plans/` (9) | they cite board paths too, and move with their items
| `direction/process.md` | the owner's tree — §5

### 4.2 Batch order (owner decision 2.15)

Base branch, one stage per commit, smallest first:
`to-spike` → `to-build` → `to-plan` → `someday` → `to-spec` → `done` → `inbox`.

Three hard orderings, because other sessions read `CLAUDE.md`, not chat:

- **`bin/board new` ships before the first batch** — otherwise a session that must log a review
  finding has no sanctioned path, and an unlogged finding blocks its round.
- **`CLAUDE.md` is repointed away from `board/inbox/` BEFORE the inbox batch starts**, not in the commit
  that deletes it. Otherwise sessions are told to append to a file that is mid-conversion for the
  whole window, and `git rm` discards their appends with no conflict.
- **`_on_deck()`/`_EPHEMERAL` change in the `to-build` batch commit** (§4.1).

§2.15 records the residual risk that remains after all three: another session's *uncommitted*
on-disk edits to a board file are still lost silently.

### 4.3 Not

Not a re-triage (except §2.13). Not a cleanup — stale items convert as they are. No `uedcli`
behaviour change.

---

## 5. Parked for the owner

Two items, both on `board/inbox/` as `[OWNER — confirm]`, verbatim, because this spec is ephemeral.

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

**(B) §2.14, succinctness** — proposed for `direction/process.md`:

> Docs, docstrings and comments are as succinct as the meaning allows — facts, not bloat; length is
> earned by what must be explained. A reviewer flags any doc they cannot fully understand, or that
> is ambiguous.

*(The worktree exception is no longer parked — it was ruled live as §2.15.)*

---

## 6. Durable homes

- **§2** → `direction/process.md` (§5) plus format choices in `board/README.md` and `CLAUDE.md`.
  Every `Rejected` line travels with them.
- **§3** → a new **`dev/docs/rationale/board.md`**: the TOML choice and its pinned subset, slug
  authoring and the pruning rule, `.gitkeep`, `bin/board`'s scope and no-venv choice, the narrowed
  link-test boundary, gate-on-absence, the reopen and fold-out-claim rules, and the batch order —
  each with `Rejected` and `Refs`.

---

## 7. Open questions

**Q1** the stale list — deferred to the end by §2.7. **Q2** the two §5 items awaiting a yes.

---

## 8. Done-when

- [ ] Eight stage directories with `.gitkeep`; the seven board files and both handoffs gone.
- [ ] The inventory (§3.11) is recorded; every item it found is a directory with parsing frontmatter
      conforming to §3.4's subset, and an authored slug and summary.
- [ ] `dev/docs/specs/` and `dev/docs/plans/` empty and removed; all 71 specs and 26 plans placed or
      accounted for by rule 7.
- [ ] The 62 owner-blocking entries are question files or standalone owner-question items per rule
      6's attribution rule; `bin/board questions` lists them.
- [ ] `test_board.py` passes: 3–9 from the scaffold commit, 1–2 from the final commit.
- [ ] `bin/board` works, with tests including the bash↔`tomllib` agreement test over every real
      `overview.md`.
- [ ] The 401 path citations are slug citations, except `decisions.md` and
      `2026-06-20-open-questions-for-andrzej.md`.
- [ ] `CLAUDE.md`: round-2 exclusion narrowed; findings routed through `bin/board new`; agents told
      to run `bin/board answered`; the `[OWNER — confirm]` parking rule rewritten; the two
      `specs/`+`plans/` passages updated.
- [ ] The two `decisions.md` markdown links and `rationale/MIGRATION.md`'s are handled.
- [ ] **The before/after list of link-checked ephemeral files is recorded**, so §4.1's narrowing is
      visible rather than silent.
- [ ] Every file in BOTH censuses of §4.1 — including the repo-root `README.md` — describes the new
      shape. **No tracked file except `decisions.md` (frozen) and
      `2026-06-20-open-questions-for-andrzej.md` (the owner's) references a deleted board path**,
      checked with both census commands.
- [ ] `dev/docs/rationale/board.md` exists (§6).
- [ ] §5's two parked items are confirmed and applied, or still parked.
- [ ] `bin/test` green; suite runtime change measured and recorded.
- [ ] The stale list is proposed in bulk (§2.7).
