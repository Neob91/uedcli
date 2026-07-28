## Working with the owner

### Ask via the question widget, and explain it properly

**Every decision that is the owner's to make goes through Claude Code's `AskUserQuestion` widget —
never as prose in the chat.** A question buried in a wall of text gets skimmed, answered partially,
or scrolls away. This covers design forks, rulings on `direction/` topics, sequencing calls, and
anything a review gate escalates.

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

## Workflow

Always ask where to implement the change:
- feature branch on a git worktree
- current checkout (usually master)
- somewhere else


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
