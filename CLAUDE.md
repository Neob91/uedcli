## The repo this tool lives in

`uedcli` is its own repository, and this file is its **canonical rule file** — there is no rule file
above it. (A sibling `uplayctl` mirrors these rules from a *different* repo; changes here do not
propagate to it.)

- **`_scratch/` (repo root) is THE place for every temporary, throwaway or experimental file** —
  scratch scripts, **every manual `MAP EXPORT`/`BRUSH EXPORT` and preview `.ppm`/`.t3d`**,
  screenshots, texture dumps, spike output, logs. It is gitignored; organize into subdirs
  (`_scratch/shots/`, `_scratch/t3d/`, …). **If a throwaway file is not under `_scratch/`, it is in
  the wrong place — no exceptions.** Never write throwaway output into the tracked tree — not
  `Temp/`, not `Maps/`, not the repo root. (The session-scratch dir named in the environment prompt
  is fine for files that never need to outlive the session.)
- **`TODO.md` (repo root) holds repo-level, cross-cutting items**; uedcli's own backlog is the board.
  When an item is fully done, delete it — never leave it ticked `[x]`.

## Working with the owner

### Ask via the question widget, and explain it properly

**Every decision that is the owner's to make goes through Claude Code's `AskUserQuestion` widget —
never as prose in the chat.** A question buried in a wall of text gets skimmed, answered partially,
or scrolls away. This covers design forks, rulings on `direction/` topics, sequencing calls, and
anything a review gate escalates.

**Write it for someone who does NOT have the spec or the code memorised.** The owner decides *what we
want* and is not carrying a 400-line spec in their head. So:

- **Say what the thing IS before asking about it**, in plain words: "`--faces textured` reads a
  face's texture from the package and paints it into the preview image" — not "the §4.3 fetch path".
- **NEVER make a section number, symbol name, or piece of jargon load-bearing.** Use them only
  *after* the plain-English version, never instead of it.
- **State why it is a decision at all** — what makes it genuinely ambiguous, and why you cannot just
  pick.
- **Make every option self-contained**, with its concrete consequence: what changes, what it costs,
  what breaks or gets slower, what it forecloses.
- **Give the recommendation first** when there is one, marked as such — a recommendation does not
  replace laying out the alternatives.
- **Surface what is genuinely uncertain**, including where your own earlier statement turned out to
  be wrong. A ruling made on a false premise is worse than no ruling.

**Never overrule the owner silently, and never downgrade a real question into a board item to avoid
asking it.** If a rule of theirs points one way and you judge otherwise, that is a question for the
widget — not a deviation recorded in a commit message and moved past. Logging is for a real finding
that is out of scope for the current change. *(Owner ruling, 2026-07-26.)*

### A DECISION is implemented as given — NEVER altered without an explicit yes

This governs the decision itself, wherever it was made: in a spec, in chat, in a one-line answer.

- **Implement the ruling as stated.** Do not add a guard, filter, clamp, fallback or special case
  that changes what it does — not "in the spirit of" it, not to satisfy a different requirement they
  also stated, not because measurement shows it is wrong.
- **Finding a real flaw does NOT authorise a fix.** Measure it, STOP, report the evidence, propose
  the change, wait for the yes.
- **Telling them afterwards is NOT consent.** Flagging an unrequested change in the report is the
  violation, not the remedy.
- **An unanswered question is not an answer.** Ask again; do not fill the gap with a default and call
  it a judgement call.
- **Same rule for reverting:** once told to drop an unapproved change, restore exactly what was ruled
  — including its known costs — and pin those costs in a test or doc so they are recorded rather than
  quietly re-fixed later.

### Direction docs — NEVER revise without confirmation

`dev/docs/direction/<topic>.md` holds what **the owner** decided — product intent and process rulings
alike. It is **MUTABLE**: revised in place, no supersession, no dated history (git keeps that).
Evidence citations and live-finding dates are kept.

- **NEVER create, revise, reword, or delete anything under `dev/docs/direction/` — including a single
  `Rejected` bullet — without asking and getting an explicit yes.** Propose the exact text and wait.
  "It follows from what they said" does NOT satisfy this. Moving a topic OUT needs a yes too — it
  removes the protection.
- **When direction looks stale, ASK — never edit.** And **confirm proactively**: when working in a
  topic, ask whether its direction doc is still current.
- **`direction/README.md` is the exception**: its index rows and short model statement may be
  maintained freely. No topic *content* there, and **never** an `@` import.
- **A decision awaiting a yes is parked** with `bin/board new inbox '[OWNER — confirm] …'`,
  `kind = "owner-question"`, carrying the proposed text verbatim in the item's `overview.md`. If it
  blocks an existing item, put it in *that* item's `questions/` instead and leave the item where it is.
- **Commits touching `dev/docs/direction/` carry a `Confirmed: <topic>` trailer**, so
  `git log --grep=confirmed -i -- dev/docs/direction/` shows every confirmed edit and an unconfirmed
  one stands out. (Four commits from 2026-07-26 predate the trailer's rename and use an older
  spelling — the case-insensitive grep catches both.)

**Nothing mechanical enforces any of this**; revise-in-place destroys the prior text, so a bad edit
looks exactly like a good one. Why it is shaped this way anyway: `dev/docs/direction/process.md`.

**`dev/docs/owner-notes.md` and `dev/docs/2026-06-20-open-questions-for-owner.md` are theirs — do not
touch them at all.** Every other doc under `dev/docs/`, including `rationale/` and `rules/`, an agent
maintains on its own.

## After every change

Without being asked, do each of these that applies (a docs-only edit has no tests to run; a code
change with no user-facing docs has none to update):

- **Update every doc the change touches** — no doc may be left stale. **EXCEPT
  `dev/docs/direction/`**: never edit that tree to fix staleness — ask.
- **Cross off the TODOs it completed**, and **add TODOs for anything deferred or left unfinished**.
- **Run the relevant tests and confirm they pass** — via `bin/test`, never bare `pytest`.
- **Commit and push it** (see **Commits**) — explicit pathspecs, one short imperative subject, no AI
  attribution, never rewriting history.
- **Gate it** (see **Review gates**) — batched, per those rules.

## Dispatching subagents

**This section IS the owner's standing request to dispatch subagents** — a blanket yes for this repo,
given once here rather than repeated in every message. It covers every subagent an agent hands work
to: a gate's reviewers, a spike investigator, a wide multi-file search, a long or multi-step task
briefed to completion. A harness rule that permits subagents only when "the user requested it" is
therefore *satisfied*, not overridden.

The grant is about **permission, not judgement.** It does not make delegation always correct — a small
bounded job still belongs inline. What it removes is the need to stop and ask whether dispatching is
allowed.

**Every dispatch carries a briefing obligation** — see **"Read-on-demand docs"**: a subagent inherits
none of your reading, so its prompt must name by path every doc it needs.

## Review gates

**EVERY change gets reviewed** — a trivial one gets only the cheap pass, but nothing ships
unlooked-at. **RUN THE GATE AUTOMATICALLY — NEVER ASK PERMISSION TO REVIEW.** The moment an artifact
is finished, dispatch its round without being told and without announcing the intent first: a gate is
part of finishing the work, exactly like running the tests. Report the OUTCOME, not the intent.

Permission to spawn the reviewers comes from **"Dispatching subagents"** above; this paragraph does
not restate it.

**Read `dev/docs/rules/review-gates.md` before dispatching a round** — it carries the rest: which row
a change takes, what "trivial" excludes, what reviewers are told, how findings are dispositioned, the
round-2 trigger, and how to batch.

### The three moments

At each of these, fan out Claude reviewer subagents in parallel and resolve their findings before the
work is declared done:

1. **After writing a spec** — before planning or implementing.
2. **After writing a plan** — before building.
3. **After building something** — before declaring done.

### How many reviewers, and which model

| Moment / tier      | Round 1 | Round 2 — only if resolving round 1 changed the artifact
|--------------------|---------|---
| **spec** review    | 3 Opus  | 2 Opus
| **plan** review    | 1 Opus  | 1 Opus
| **build** review   | 1 Opus  | 1 Opus
| **docs-only**      | 1 Opus  | never — ONE round, max
| **trivial** change | 1 Haiku | never — the one round IS the whole gate

Read the table as: **one reviewer is the gate; a second is what a finding costs.** **Only the spec
moment opens wide up front** — a spec's defects get built on top of. *(Owner ruling, 2026-07-25.)*
**Every reviewer slot outside the trivial tier is Opus** (`Agent(model: "opus")`). That governs
*which model fills a slot* — the counts and the two-round ceiling are hard.

**NEVER restate the reviewer counts outside this file.** A spec, plan, or board item that spells out
"two cold reviewers" goes stale the moment the gate changes — and it has, repeatedly. Cite
**`CLAUDE.md` "Review gates"** instead and let the count live in exactly one place.

### The rules that bind every round

- **`build` is the DEFAULT row** for anything non-trivial that is not a spec or a plan. **A batch
  takes its least-trivial member's row.**
- **Trivial means the change alters no reader's understanding and no tool behavior** — a typo, a
  formatting fix, a comment, a test rename, a broken link. It is **NEVER** an edit to what a rule,
  doc, spec, plan or engine-fact note *says*, and never a change to executable behavior, including a
  one-line change to load-bearing code. **When it is arguable, it is not trivial.**
- **Reviewers get CONTEXT but never PRIMING.** Give every reviewer this file, the spec/plan under
  implementation, and — by path — every doc they must read before acting; a subagent does not inherit
  your reading. Never show them a previous round's findings, never say what you expect, never reuse a
  reviewer.
- **What blocks the gate is observability, not severity:** a finding may be left standing ONLY if
  fixing it would change nothing anyone would ever observe — pure wording, formatting, or naming
  taste. Everything else is **fixed**, **logged** (`bin/board new inbox`), **escalated to the owner**,
  or **refuted** with the disproving check recorded. Never only in chat.
- **TWO ROUNDS IS THE CEILING**, and round 2 runs iff resolving round 1 **changed the artifact**. It
  fires automatically on that trigger. There is no round 3.
- **A STRUCTURAL finding STOPS the work, in EITHER round** — escalate to the owner; the work is
  parked, not done.
- **Batch small changes into one round.** Commit as you go; gate the accumulated range before
  declaring the batch done. Flush the batch before ending a session or switching work. Never batch
  across the three moments.
- **Surface scale, once:** if a single moment would dispatch more than 3 reviewers, or several rounds
  would fire at once, say what is about to run in one line and then run it.

## Commits

**Commit after every change.** Once a change is complete — code, docs, TODO updates, all of it —
commit it before moving on, without waiting to be asked. Short imperative subject, no `type:` prefix,
no AI attribution.

**COMMIT ONLY YOUR OWN HUNKS — never another session's, unless told to.** File-level pathspecs are
NOT sufficient: several agents work this repo at once, so a file you edited may ALSO carry hunks you
did not write, and `git commit -- <path>` commits the whole file including theirs.

- **Read `git diff <path>` for every file before committing it**, and satisfy yourself that every
  hunk is one you made. A file you never touched is obviously not yours; a file you *did* touch is
  the dangerous case.
- **If a file carries foreign hunks, stage only yours** — write your hunks to a patch and
  `git apply --cached` it, then commit the index. (`git add -p` is interactive and unavailable here.)
  Never commit the file wholesale "because most of it is mine".
- **Never `git add .`, `git add -A` or `git commit -a`.**
- **Leave what is not yours alone** — do not revert it, stage it, or tidy it. It belongs to a session
  still working.
- **Check the index is clean before you stage** (`git diff --cached --quiet`): a non-empty index is
  another session mid-commit, and anything already staged will ride along on your `git commit`.

The same care applies to `git push` on a shared branch: it publishes every local commit there,
including other sessions'. That is normally fine and is not a reason to skip pushing your own work —
but never treat a push as "only my change went out".

**Always push your work — never lose it** — with exactly one exception, a feature branch in a
worktree, below. **NEVER REWRITE HISTORY, locally OR on `origin`.** No
`git push --force` (or `--force-with-lease`), no `git commit --amend`, no `git rebase` that rewrites
already-pushed commits. Only ever add new commits on top; mistakes are corrected with a fresh commit
or a `git revert`.

**A FEATURE is built in its own git worktree and squash-merged back** — read
`dev/docs/rules/worktrees.md` before creating one or merging one. Three things there are dangerous to
get wrong from memory:

- **NEVER push the feature branch** — it is squashed away on merge and a remote branch can never be
  deleted, so pushing one strands permanent dead weight on `origin`. This is the one exception to
  "always push your work" above; local commits are what protect the work instead.
- **Run `git diff --cached --quiet` before `git merge --squash`** — omitting it commits over a
  concurrent session's staged work.
- **Ask the owner before `git branch -D`** — deleting a branch is destructive.

A change that is not a feature — a doc correction, a chore sweep, a one-file fix — needs no worktree.

## Code & CLI conventions

- **NO BACK-COMPAT CRUFT — uedcli is UNRELEASED.** There are no external users and no scripts in the
  wild, so nothing is ever kept for backward compatibility. When you remove or rename a flag, verb,
  option value, output format, or code path, **delete it outright** in the same change that adds the
  replacement — the new spelling is the only spelling. Never add or keep: a deprecated alias, a no-op
  flag "so old invocations still work", a migration-error shim (a flag defined only to
  `parser.error("X was renamed to Y")`), dual-format support kept to avoid re-writing callers, or an
  "old way" branch in code/tests/docs.
  *(`dev/docs/direction/conventions.md`. Superseded only when uedcli is released.)*
- **No silent half-answers.** A command that can't fully satisfy a request exits 2 naming the
  offending value, rather than emitting a partial result plus a stderr warning — stderr scrolls away
  and the caller takes the partial answer for a complete one.
- **Every command and argument needs a `help=` string** that explains what it actually does, so
  `-h`/`--help` is self-explanatory — never just a restatement of the flag name.
- **Never let a Python exception reach the CLI user.** A bad actor/entity name must raise a clear
  error naming the offending value (`Actor not found: Foo`) and exit non-zero — never a bare
  `KeyError`/`IndexError` traceback. Cover each path with a regression test.
- **Verbs compose — this is the CORE CLI philosophy.** Build small, single-purpose verbs that pipe
  together; do NOT grow big verbs with many bespoke flags. Concretely:
  - **Producer/query verbs print their result to stdout, one item per line** — pipe-friendly
    (`actor find` prints matching names; `actor add` prints the allocated names; a generator prints a
    T3D snippet). Human summaries/counts go to **stderr** so they never pollute the pipe. Add
    **`--json`** where a script needs structured output rather than lines.
  - **Mutating/consuming verbs read their target set from stdin via `-`** — so
    `actor find --folder castle.tower | actor prop set - Texture=…` and `brush build cube | actor add -`
    close the loop instead of copy-paste / `$(…)`. `-` is the SOLE names source (mutually exclusive
    with names as CLI args); empty stdin is a clean no-op (exit 0), not an error.
  - **Two stdin conventions, disambiguated by verb:** a **name list** (`find → mutate -`) vs a **T3D
    snippet** (`build → add -`). Keep them distinct; don't blur them.
  - **A verb over a SET takes the set, and that IS the operation** — pass names (or `-`); the
    multi-item behaviour needs no extra flag. E.g. `actor bbox <names…>` returns the box enclosing ALL
    of them, so there is **no `--union`**. Never add a flag that merely restates "operate on this set."
  - **Prefer a stateless `find`/query verb** that prints matching names (by folder, class, property,
    …) for other verbs to consume, over per-command `--only-groups`/`--only-actors` filter flags
    sprinkled on every verb.
  - **`find` vs `search` — name by what's queried, never merge them.** `find` = a deterministic query
    over concrete **T3D-tree state** (actors/polys/brushes that exist in the trunk), producing an
    exact name/selector set to pipe onward (`actor find`, `brush poly find`). `search` = ranked/fuzzy
    **discovery over a catalog or corpus** (textures, the asset catalog, docs) — *what exists* by
    relevance, not a known set (`texture search`; future `catalog search`/`docs search`).
    *(`dev/docs/direction/conventions.md`.)*

## MINIMAL. SUCCINCT. AS SHORT AS POSSIBLE WITHOUT LOSING MEANING.

**The first rule of every doc, every docstring, every code comment, every commit message, every board
item — and of THIS FILE — and the one most often broken.**

- **The test: delete it. If a reader would still do the same thing, it stays deleted.** Sentence,
  bullet, heading, example — all of it.
- **Length is EARNED by what must be explained**, never by importance or by wanting to look thorough.
- **Cut padding, NOT explanation.** Padding is restatement, throat-clearing, hedging, ceremony.
  Explanation is mechanism — the cold-reader rule under **Documentation** still binds.
- **A doc that GREW is a doc to CUT.** Leave a doc you touch shorter than you found it unless the
  change genuinely added meaning.

*(Owner ruling, 2026-07-27; re-emphasised at the owner's request 2026-07-28.)*

## Documentation

**Read `dev/docs/rules/documentation.md` before writing or restructuring docs** — it carries the
markdown-table alignment convention, which developer doc owns what, the specs-and-plans-are-ephemeral
rules, and how UnrealEd facts are cited and confidence-tagged. The three rules below bind everywhere:

- **Write every doc for a reader with NO familiarity with the implementation.** Assume the reader
  does not know the code, the substrate, the prior conversation, or the jargon. Define terms before
  using them, spell out the mechanism, and never lean on context the reader doesn't have. An
  explanation that only makes sense if you already know how it works is a bug — rewrite it.
- **Keep the user-facing docs current with the CLI — not optional.** Whenever a change alters
  behavior a user can observe — a new verb, a changed flag, different output, a removed feature —
  update `docs/usage.md` and `docs/leveldesign/` in the same change.
- **`docs/` is ALL user-facing and must NEVER reference the developer tree** (`dev/docs/`) — a user
  cannot open a spike, the board, or `architecture.md` and must not be sent there.

**Always document new learnings about how UnrealEd functions, our goals, or architectural
choices/changes in `dev/docs`** — `dev/docs/unrealed/` for engine findings, back-referenced from code
comments. The public documentation is very lacking and discovering this knowledge is expensive.

## The board — the backlog, and where findings go

The board is **one directory per work item** (`dev/docs/board/<stage>/<slug>/overview.md`, plus
optional `spec.md`, `plan.md` and `questions/<q>.md`). The stage queues are named for the *next
action* an item needs — `inbox/` (un-triaged capture, including anything you'd flag for the owner) →
`to-spec/` → `to-spike/` → `to-plan/` → `to-build/` (the reviewed build queue), plus `someday/`,
`stale/` and `done/`. An item advances with a single `git mv`. **Read `dev/docs/board/README.md`
before working the board** — stages, frontmatter, slugs, and the question flow.

Three rules bind every session:

- **LOG A FINDING WITH `bin/board new inbox '<title>'`.** It creates a valid item and prints its
  path; write the detail into that `overview.md`. There is no capture file to append to. Anything
  that would otherwise live only in chat goes here: a provisional call, an assumption, a risk, a
  deviation from spec/plan, work you deliberately didn't do. If something gets deferred
  mid-implementation, file a *separate* item rather than letting the original cover both halves.
- **RUN `bin/board answered` AT SESSION START**, and before pulling work off `to-build/`. A question
  the owner has answered is invisible otherwise. **The commit that folds an answer out also deletes
  the question file** — if you find it already gone, another session has done it; stop.
- **A question raised mid-pipeline does NOT move its item.** Write it into that item's own
  `questions/` directory and leave the item in whatever stage it had reached. *(Owner ruling,
  2026-07-27.)*

`bin/board questions|answered|ls|show|new` — `bin/board --help`. It needs no venv.

## Read-on-demand docs — the router

Only `direction/README.md` (the topic index) is auto-loaded. **Every doc below is NOT in your context
— you MUST `Read` the relevant one before the action it names.** These one-liners are a *router, not
a substitute*: never answer a question about UnrealEd behavior, the T3D format, uedcli internals,
**or a process rule** from this summary or from training memory — the editor is undocumented and
crash-prone, and these docs are the only ground truth. If a task touches any row below and you have
not read that doc **this session**, read it first. (`dev/docs/README.md` has the full "which doc is
for what" table.)

**A dispatched subagent does NOT inherit your reading.** When you hand work to a subagent — a
reviewer, a spike investigator, anything — its prompt MUST name the docs it has to read before
acting, by path. A subagent that has not read `unrealed/t3d.md` will flag correct T3D handling as a
bug; one that has not read this file will flag deliberate conventions as defects.

- **@dev/docs/direction/README.md** — *(auto-loaded)* the index of what we WANT. **Read the topic doc itself before any design question, spec or plan** — the index is a router, not the content.
- `dev/docs/architecture.md` — **Read BEFORE any uedcli code change or design question**: the layer/module map, the model-side write pattern, invariants D1–D8, the session-store shape.
- `dev/docs/unrealed/commands.md` — **Read BEFORE driving the editor console**: the exec-verb reference (what to type).
- `dev/docs/unrealed/t3d.md` — **Read BEFORE authoring/parsing T3D or editing surfaces/geometry**: block nesting, property forms, winding, authored-vs-computed taxonomy.
- `dev/docs/unrealed/quirks.md` — **Read BEFORE driving UnrealEd or debugging editor behavior**: the non-obvious traps (IMPORTADD grid-snap, demand-load, selectability, CSG).
- `dev/docs/unrealed/rendering.md` — **Read BEFORE taking a screenshot/render**: render modes, `CAMERA OPEN`, the black-viewport traps.
- `dev/docs/unrealed/extracting-from-dll.md` — **Read BEFORE mining the binaries** for command/behavior facts.
- `dev/docs/parallel-editors.md` — **Read BEFORE running many ephemeral editors** concurrently.
- `dev/docs/decisions.md` — **FROZEN, historical reading only — never append.** The retired ledger; its entries migrated into `dev/docs/direction/` (the owner's decisions) **and** `dev/docs/rationale/` (yours). `dev/docs/rationale/MIGRATION.md` is the map from an old dated citation to its new home.
- `dev/docs/direction.md` — **RETIRED, a stub; never append.** All 12 topics migrated to `dev/docs/direction/`.

**Process rules** (`dev/docs/rules/README.md` indexes them). Each line carries the one fact you cannot
afford to miss; the doc carries the rest:

- `dev/docs/rules/review-gates.md` — **Read BEFORE dispatching a review round.** Which row a change takes, what "trivial" excludes, priming vs context, how findings are dispositioned, the round-2 trigger, batching. **The counts stay in this file, not there.**
- `dev/docs/rules/documentation.md` — **Read BEFORE writing or restructuring docs.** Table alignment, which dev doc owns what, ephemeral specs/plans, UnrealEd evidence + confidence markers.
- `dev/docs/rules/worktrees.md` — **Read BEFORE creating a worktree or squash-merging one.** Never push a feature branch; check the index before `git merge --squash`; ask before `git branch -D`.
- `dev/docs/rules/tests.md` — **Read BEFORE running tests.** Run them via **`bin/test`**, never bare `pytest`; uedcli and its suite are **host-native, not containerised**.
- `dev/docs/rules/spikes.md` — **Read BEFORE starting or finishing a spike.** Commit the harness to `dev/docs/spikes/<slug>/`, never leave it in `_scratch/`; **pin every checkable finding with a committed regression test** or it rots.
- `dev/docs/rules/background-work.md` — **Read BEFORE starting a background job or long wait.** Never leave one on a single open-ended wait — the editor wedges *silently*; pair a tracked job with a ~20-minute hang-detector, and never poll on short wake-ups.
