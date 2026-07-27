# Spec — the board becomes one directory per work item

**Status:** written 2026-07-27, awaiting spec review.
**Board item:** [`../board/to-plan.md`](../board/to-plan.md) (this spec's entry).
**Owner decisions in this doc:** §2. **Agent decisions:** §3.

---

## 1. What this changes, in one paragraph

Today the uedcli backlog is **seven big markdown files** under `dev/docs/board/`
(`inbox.md`, `to-spec.md`, `to-spike.md`, `to-plan.md`, `to-build.md`, `someday.md`,
`done.md`). Each file is a bullet list; each bullet is one work item, anywhere from one line
to sixty. An item advances through the pipeline by having its bullet **cut out of one file and
pasted into the next**.

After this change, **each work item is a directory**, and the stage it is in **is the directory
it sits in**:

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

### Why (the three problems being fixed)

1. **Reads are enormous.** `inbox.md` is **357 KB / 4,042 lines / 293 items**. The whole board
   is **7,173 lines**. An agent that wants one item reads all 293 of them. After the change a
   read is one small file.
2. **Writes collide.** Every review round appends its findings to `inbox.md`, and several agent
   sessions work this repo at once. Two agents finishing at the same moment edit the same file,
   and then spend time working out what happened to their edit. Per-item files make two agents
   touching two items touch two different files.
3. **Questions are unfindable.** A question that blocks an item is currently a paragraph inside
   a 4,000-line file, indistinguishable from a note. After the change every open question is its
   own file at a predictable path, so "show me everything waiting on a decision" is a glob.

### What this unlocks

**Pre-speccing.** An agent can draft `spec.md` for an item and park each unresolved fork as a
question file. The owner later walks the question files, writes an answer in each, and an agent
folds the answers into the spec. The item cannot reach `to-build/` while a question is
unanswered (§3.6), so the drafting can run ahead of the decisions without the decisions being
lost or silently guessed.

---

## 2. Owner decisions

Recorded as made, 2026-07-27, in the order they were decided. These are load-bearing: an
implementation may not quietly deviate from one.

**2.1 — Every stage has the identical shape, including `inbox` and `done`.**
There is no special-cased stage. *Owner: "Each one: inbox, ready-to-build, etc. should have the
same setup; So you just git-mv stuff between them when you need to."* Uniformity is the point:
one rule, and advancing an item is always the same single command.
**Rejected:** *inbox stays a flat capture file* (cheapest capture, but leaves the 357 KB file and
its collisions exactly as they are — that file is the problem). *`done`/`someday` stay flat files*
(saves converting 121 finished/parked entries, but puts a hand-conversion step on the boundary
every time a `someday` item is pulled back).

**2.2 — `questions/` holds questions that BLOCK the item, not a conversation log.**
*Owner: "questions.md is not questions I asked, it's questions that need answering before the
issue can be built or planned."* A question file is a **gate**: the thing that must be settled
before this item can be planned or built. It is not a record of things discussed.
**Rejected:** reading `questions/` as a per-item Q&A archive — it would fill with resolved chatter
and stop being a reliable list of what is actually blocking.

**2.3 — Answering a question: the owner writes into the file; an agent folds it out and deletes it.**
Each question file carries an empty `## Answer` section. The owner fills it in — that is the whole
job. An agent then copies the decision to its durable home (`dev/docs/direction/` for the owner's
decisions, `dev/docs/rationale/` for an agent's, per `CLAUDE.md`), updates the item's `spec.md`,
and **deletes the question file**. **Open** therefore means *the `## Answer` section is empty*.
Git keeps the deleted text.
**Rejected:** *answered files stay, marked answered* (item directories accumulate dead questions
and "what is open" becomes a status-field read instead of an emptiness check). *Answered files move
to an `answered/` subdirectory* (same accumulation, one more directory per item).

**2.4 — Priority lives in a fixed header line at the top of `overview.md`.**
Not in the directory name. Changing a priority must not rename a directory, because a rename
breaks every link pointing at the item and fragments its git history.
**Rejected:** *a `p1-`/`p3-` directory-name prefix* (a plain `ls` would come back sorted for free,
but re-prioritising an item renames it). *No priority at all* (loses a distinction the board uses
today).

**2.5 — The header line carries a SHORT description; detail goes in the body.**
*Owner, 2026-07-27: "Header in overview.md should contain a SHORT description. More detail will be
added in the main body."* The header is the thing read when scanning a stage, so it must be
skimmable on one line; the body is what is read once the item is chosen.

**2.6 — Stale items go to `board/stale/`; removal is deferred.**
*Owner: "Put stale issues into board/stale, let's defer removal."* `stale/` is an ordinary stage
directory of the same shape, so `git mv` moves an item into or out of it. Nothing is deleted by
this change.

**2.7 — The stale list is proposed at the VERY END of the migration, in bulk.**
*Owner: "Agent proposes, I confirm the list, BUT do that at the very end, ok? And then ask me in
bulk."* So the migration **converts every item in place first**, in whatever stage it currently
sits, and only then produces one list of proposed-stale items with a one-line reason each, as a
single question for the owner. No item is moved to `stale/` before that list is confirmed.
**Rejected:** *an agent applies a written staleness rule unilaterally* (mechanical tests misfire on
vague one-liners, and live work would disappear into a directory nobody reads).

**2.8 — The build queue keeps the name `to-build`, matching its siblings.**
The stages are `inbox`, `to-spec`, `to-spike`, `to-plan`, `to-build`, `someday`, `stale`, `done`.
**Rejected:** `ready-to-build` (the owner's first sketch; it says the thing that matters about that
lane, but it is then the one stage not named `to-<verb>`, needing a carve-out in the naming rule
the board README already states).

---

## 3. The design

### 3.1 The stage directories

Exactly eight, all siblings of `README.md`, all the same shape:

| Directory | Holds | Next action
|--------------|--------------------------------------------------------|---
| `inbox/` | raw, un-triaged capture — ideas, gaps, bugs, chores, anything flagged for the owner | triage → `git mv` to a stage
| `to-spec/` | needs a spec/design written | write `spec.md` in the item directory
| `to-spike/` | an open question needs a live/offline investigation first | run a spike (evidence lands in `dev/docs/spikes/`)
| `to-plan/` | has a reviewed spec, needs a plan | write `plan.md` in the item directory
| `to-build/` | reviewed plan, ready to implement now | implement it
| `someday/` | parked nice-to-have, not surfaced in normal triage | `git mv` back to `inbox/` when picked up
| `stale/` | judged stale, retained rather than deleted (§2.6) | none — revisit or eventually delete
| `done/` | recently finished, or finished with deferred remnants | none — reference tail

**A stage directory contains item directories and nothing else** — no per-stage `README.md`, no
loose `.md` files. `ls dev/docs/board/to-build/` is therefore exactly the queue, with no noise.
The one exception is a **`.gitkeep`** file in each stage directory, because git cannot track an
empty directory and `to-spike/` will legitimately empty out. `board/README.md` remains the single
place the flow and the stage meanings are documented.

### 3.2 The item directory

```
<stage>/<item-slug>/
  overview.md         REQUIRED. The item. Always present, in every stage.
  spec.md             optional — the design (was dev/docs/specs/<date>-<name>.md)
  plan.md             optional — the implementation plan (was dev/docs/plans/…)
  questions/<q>.md    optional — one file per blocking question
  <anything>.md       optional — handoff notes, measurements, findings
```

- **`overview.md` is the only required file.** For a one-line inbox note it is legitimately four
  lines long. Nothing forces a directory to be filled out.
- **`<item-slug>`** is kebab-case, derived from the item's title, and **never renamed** once
  created — a rename breaks links and fragments the item's history. It is unique across the
  *whole* board, not just within a stage, so a link written while an item sat in `to-plan/`
  can be repointed mechanically after it moves.
- **Extra files are free.** The two existing handoff documents
  (`HANDOFF-level-import.md`, 338 lines; `HANDOFF-native-full-parity.md`, 191 lines) become
  `handoff.md` inside their items rather than top-level board files.
- **Spike evidence does NOT move here.** `dev/docs/spikes/` is durable evidence, cited from
  `architecture.md` and `unrealed/*.md`; it outlives the board item and stays where it is. An
  item links its spike.

### 3.3 `overview.md` — the required header

```markdown
# Per-surface texture verbs — steps 2-5

> `p1` · `[plan]` · Replace the align flag group with subcommands and adopt the editor's
> projection family.

The body starts here: the full detail, background, links, whatever the item needs.
```

Line 1 is an H1 title. Line 3 is the **header line**: a blockquote of three `·`-separated fields,
in this fixed order.

| Field | Values | Meaning
|-----------------|-----------------------------------------------|---
| priority | `p1` `p2` `p3` `p?` | `p?` = not yet prioritised. **Permitted only in `inbox/` and `stale/`** — triaging an item out of the inbox is where a priority gets assigned. This matters: only **82 of 293** inbox items carry a `pN` today, so inventing one for the other 211 during migration would be fabrication.
| kind | `[implement]` `[chore]` `[debug]` `[owner-confirm]` | What sort of work it is. **Not the stage** — the stage is the directory (§3.4).
| short description | one sentence, may wrap | Per §2.5. Enough to decide whether to open the item.

**The kind tag no longer duplicates the stage.** Today `CLAUDE.md` says "the bracket tag ≈ the
queue" (`[spec]`→`to-spec`, `[plan]`→`to-plan`), which is two places stating one fact and a
standing opportunity for them to disagree. With the stage in the path, `[spec]`/`[spike]`/`[plan]`
are retired as tags; what survives is the *kind* of work, which the path genuinely does not say.

### 3.4 Advancing an item

```
git mv dev/docs/board/to-plan/<slug> dev/docs/board/to-build/<slug>
```

One rename, one command, whole item and its history move together. Two agents advancing two
different items touch disjoint paths, which is the collision fix from §1.

**On completion** (`git mv … done/<slug>`), the item's **`spec.md` and `plan.md` are deleted** and
`overview.md` is trimmed to a short reference entry. This preserves the existing rule that specs
and plans are ephemeral and that what was learned is folded into the durable docs
(`architecture.md`, `unrealed/*.md`, `direction/`, `rationale/`) before the scratch is dropped —
`CLAUDE.md` "Documentation". `done/` stays a *reference tail*, not an archive; git holds the rest.

### 3.5 A question file

Path: `<stage>/<item-slug>/questions/<question-slug>.md`.

```markdown
# Should `--faces` slices S1-S3 land before the texture decoder?

## Context

`actor preview --faces` draws brush faces as solid or textured pictures instead of
outlines. Its plan has five slices; only the fourth reads any texture data. …

## Options

- **Keep the ruled order.** … Consequence: …
- **Let S1-S3 land first.** … Consequence: …

## Recommendation

…

## Answer

<!-- Empty = open. Write the decision here. -->
```

- **`## Context` is mandatory and is written for a reader who has not got the spec or the code in
  their head.** This is `CLAUDE.md` "Asking the owner" applied to a written artifact: say what the
  thing *is* in plain words before asking about it, never make a section number or a symbol name
  load-bearing, make each option self-contained with its concrete consequence, and give the
  recommendation first where there is one.
- **`## Answer` empty ⇒ the question is open.** The HTML comment is not content; an answer is any
  other non-blank text.
- **A question the owner cannot settle by deciding — one that needs a measurement — is not a
  question file.** It moves the item to `to-spike/`, which is what that stage is for.
- **This does not replace the `AskUserQuestion` widget.** `CLAUDE.md` requires decisions to be put
  through the widget in-session. A question file is the *durable* form: how a question survives the
  session ending, and how a batch of them is walked later. A question asked live and answered live
  never needs a file; a question raised while the owner is not there gets one.

### 3.6 The blocking rule, and the test that pins it

**An item with an open question may not sit in `to-build/`.** That is what §2.2 means by a
question being a gate — `to-build/` is the queue an agent pulls from without asking anything, so an
unanswered question there would be guessed at rather than answered.

A regression test asserts it, alongside the header-format checks. Without a test this is a
sentence in a README that nothing enforces:

- every item directory has an `overview.md`;
- every `overview.md`'s header line parses, with a priority, a kind, and a non-empty description;
- `p?` appears only under `inbox/` and `stale/`;
- no item under `to-build/` has a question file with an empty `## Answer`;
- item slugs are unique across the whole board;
- every stage directory contains only item directories (plus `.gitkeep`).

### 3.7 `bin/board` — the helper that makes the questions walkable

The owner's stated motivation is *"I could easily look at questions, not have to scan huge Claude
responses"*. A glob gets close, but "open" is an emptiness test inside the file, which a glob
cannot do. So a small script:

```
bin/board questions              # every OPEN question, grouped by item, with its path
bin/board ls [<stage>]           # items in a stage, sorted by priority, one line each
```

Nothing else. It reads the tree and prints; it never writes. Deliberately **not** a `uedcli` verb —
`uedcli` is the level-editing tool for users, and the board is developer process, so it has no
business in the shipped CLI surface.

---

## 4. Migration

**~581 items** convert: 293 `inbox` + 55 `to-spec` + 3 `to-spike` + 8 `to-plan` + 7 `to-build` +
27 `someday` + 94 `done`, plus the 2 handoff documents. Also **30 files in `dev/docs/specs/`** and
**26 in `dev/docs/plans/`** move into their items' directories.

**Rules the migration must not break:**

1. **No item's text is lost or rewritten.** A bullet's body is moved into its `overview.md`
   verbatim; only the H1 and the header line are new. The header's short description is drawn from
   the bullet's own bolded lead sentence where it has one.
2. **Priority is copied, never invented.** An item with no `pN` today gets `p?` (§3.3).
3. **Every item is converted in its CURRENT stage.** Nothing is re-triaged, nothing is judged
   stale, nothing moves between stages during the conversion — §2.7.
4. **Then, and only then, the stale list is proposed in bulk**, as one question for the owner with
   a one-line reason per item. `stale/` stays empty until that comes back.
5. **A spec or plan with no board item** (an orphan in `dev/docs/specs/`) gets an item directory
   created for it, in the stage its state implies, and appears on the stale list if it looks dead.
   It is not deleted and not left behind.
6. **`dev/docs/specs/` and `dev/docs/plans/` are removed once empty.** Per `CLAUDE.md` "no
   back-compat cruft", the new location is the only location — no stub, no forwarding note.

**Ordering within the migration is a planning question**, not a spec question; the plan slices it.
The one hard sequencing constraint is rule 3 → rule 4.

### 4.1 Known fallout, to be handled in the same change

| What | Why it breaks | What it needs
|-------------------------------|----------------------------------------------------------------|---
| `uedcli/tests/test_doc_links.py` `_on_deck()` | Reads `dev/docs/board/to-build.md` as a **file** to derive which ephemeral specs/plans are on-deck and therefore link-checked. That file stops existing. | Repoint at the `to-build/` **directory**. The carve-out gets simpler, not harder: an on-deck plan is now literally `to-build/*/plan.md`.
| same file, `_EPHEMERAL` | Exempts `dev/docs/specs/` and `dev/docs/plans/` from link checking. Those prefixes disappear, so **every** board `spec.md`/`plan.md` silently becomes link-checked, including rough drafts in `inbox/`. | Decide and state it explicitly: exempt `board/*/*/spec.md` and `plan.md` **except** under `to-build/`, preserving today's boundary exactly.
| `dev/docs/README.md` rows 36-41 | Five rows link `board/inbox.md`, `board/to-spec.md`, … by path. | Rewrite as the eight directories.
| `dev/docs/board/README.md` | Describes seven files, the bullet flow, and the tag↔queue rule. | Rewritten for the new shape; it stays the single prose file on the board.
| `CLAUDE.md` — "TODOs", "Review gates", "Direction docs", "Documentation" | Names `board/inbox.md` at 7 places as the log/park destination, and states the tag≈queue rule that §3.3 retires. | Repoint at `board/inbox/` and restate the tag rule.
| `dev/docs/direction/process.md:53-54` | States *"The board is a set of stage queues named for the next action an item needs."* — the sentence this change makes wrong. | **Owner's tree — cannot be edited without an explicit yes.** Proposed replacement text in §5; parked as an `[OWNER — confirm]` item meanwhile.
| ~15 code comments and docstrings | `preview.py`, `dispatch.py`, `model.py`, `eventgraph.py`, `cli.py`, `polyalign.py`, `native/materialize.py`, `driver.py`, and 4 test files cite `board/inbox.md` or `board/to-spec.md` as *"see the board"*. | Mostly repoint to `board/inbox/`; where a comment cites a specific item, point at that item's directory.

### 4.2 What this migration is NOT

- **Not a re-triage.** No item changes stage, gains a priority it did not have, or is reworded
  (§2.7, rule 3).
- **Not a cleanup.** Duplicated, contradictory and obsolete items convert as they are and are dealt
  with through the stale list.
- **Not a `uedcli` behaviour change.** No verb, flag or output changes. The only code touched is
  `test_doc_links.py`, the new board test, `bin/board`, and comment text.

---

## 5. Text proposed for `dev/docs/direction/process.md` — AWAITING THE OWNER'S YES

`CLAUDE.md` forbids an agent editing `dev/docs/direction/` without an explicit yes, and this
change makes one of its sentences wrong. **Proposed replacement for the second half of the
"the board" paragraph (currently lines 53-54), verbatim:**

> The board is a set of stages named for the *next action* an item needs. **Each work item is a
> directory**, and the stage it is in is the directory it sits in; an item advances by a single
> `git mv` into the next stage. The directory always holds an `overview.md` — a title, a one-line
> header giving priority, kind and a short description, then the detail — and may hold the item's
> `spec.md`, its `plan.md`, and a `questions/` directory. **A question file is a blocker**: the
> thing that must be answered before the item can be planned or built. It is answered by writing
> into its empty `## Answer` section, after which an agent folds the decision into its durable home
> and deletes the file. An item with an open question never reaches the build queue.

Until that yes lands, this is parked as an `[OWNER — confirm]` board item carrying the text
verbatim, and `process.md` is left untouched.

---

## 6. Open questions

**Q1 — the stale list.** Deferred by the owner's own ruling (§2.7) to the very end of the
migration, asked in bulk. Not a blocker on the plan.

Nothing else is open. Everything in §2 is decided; §3 is agent-side design, revisable by review.

---

## 7. Done-when

- [ ] The eight stage directories exist, each with a `.gitkeep`; the seven top-level `.md` files
      and the two `HANDOFF-*.md` files are gone.
- [ ] All ~581 items are item directories with a parsing `overview.md`, text preserved verbatim.
- [ ] `dev/docs/specs/` and `dev/docs/plans/` are empty and removed; every spec and plan lives in
      its item's directory.
- [ ] The board test (§3.6) passes, including the `to-build/` no-open-questions rule.
- [ ] `bin/board questions` and `bin/board ls` work.
- [ ] `test_doc_links.py` passes with `_on_deck()` and `_EPHEMERAL` repointed; the whole suite is
      green via `bin/test`.
- [ ] `board/README.md`, `dev/docs/README.md`, `CLAUDE.md` and the ~15 code comments describe the
      new shape; no tracked file references a deleted board path.
- [ ] The `direction/process.md` text (§5) is either confirmed and applied, or parked as an
      `[OWNER — confirm]` item.
- [ ] The stale list is proposed to the owner in bulk (§2.7).
