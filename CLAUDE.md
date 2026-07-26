### The repo this tool lives in

`uedcli` is its own repository — this file sits at its root and **is the
repo's canonical rule file**. There is no rule file above it. (A sibling
`uplayctl` mirrors these rules, but it lives in a *different* repo and is not
reachable from here; changes made here do not propagate to it.)

- **`_scratch/` (at the repo root, beside this file) is THE place for every temporary,
  throwaway, or experimental file.** It is gitignored, so nothing there can
  be committed by accident. If a throwaway file is not under `_scratch/`, it
  is in the wrong place — no exceptions. That includes scratch scripts,
  **every manual `MAP EXPORT`/`BRUSH EXPORT` and preview `.ppm`/`.t3d`**,
  screenshots, texture dumps, spike output, and logs; organize into subdirs
  (`_scratch/shots/`, `_scratch/t3d/`, …). Never write throwaway output into
  the tracked tree — not `Temp/`, not `Maps/`, not the repo root. (This
  session-scratch dir noted in the environment prompt is fine for files that
  never need to outlive the session; `_scratch/` is the in-repo home.)
- **`TODO.md` (repo root) holds repo-level, cross-cutting items**; uedcli's
  own backlog is the board under `dev/docs/board/` (see **TODOs** below).
  When an item is fully done, delete it — never leave it ticked `[x]`.

### After every change

Without being asked, do each of these that applies (a docs-only edit has no
tests to run; a code change with no user-facing docs has none to update):

- **Update every doc the change touches** — no doc may be left stale (see
  **Documentation** below for which doc owns what). **EXCEPT
  `dev/docs/direction/`**: never edit that tree to fix staleness — ask
  The owner (see **Direction docs** below).
- **Cross off the TODOs it completed**, and **add TODOs for anything
  deferred or left unfinished**.
- **Run the relevant tests and confirm they pass** — via `bin/test`, never
  bare `pytest` (`dev/docs/rules/tests.md`).
- **Commit and push it** (see **Commits**) — explicit pathspecs, one short
  imperative subject, no AI attribution, never rewriting history.
- **Gate it** (see **Review gates** below) — batched, per those rules.

### Review gates

**EVERY change gets reviewed** — a trivial one gets only the cheap pass,
but nothing ships unlooked-at. At three moments fan out Claude reviewer
subagents in parallel and resolve their findings before the work is
declared done:

1. **After writing a spec** — before planning or implementing.
2. **After writing a plan** — before building. **Specced pipeline work
   goes through a plan doc, so it gets a plan round**; only stage-less
   `[chore]`/`[debug]` work and one-file fixes have no plan and therefore
   no plan round. Not writing a plan is NOT a way to skip this round —
   `to-build.md` takes a *reviewed* plan (see **TODOs** below and
   `dev/docs/board/README.md`).
3. **After building something** — before declaring done.

**How many reviewers, and which model.** Every reviewer slot outside the
trivial tier is **Opus** (`Agent(model: "opus")`) rather than a cheaper
model: inside a bounded gate, one missed defect costs more than the slot.
That is a rule about *which model fills a slot*, not a licence to add slots
or rounds — the counts below and the two-round ceiling are hard. Headcount
buys breadth, not depth: cold reviewers diverge sharply, so more reviewers
is how an artifact gets covered, not how one finding gets re-checked.

**A PLAN or BUILD round is ONE reviewer, and the second one is the
escalation.** Each starts with a single Opus reviewer over the finished
artifact. If it finds nothing, the gate is passed on one slot — the common
case, and where almost all of the gate's cost is saved. If resolving its
findings changed the artifact, round 2's single Opus reviewer reads the
updated work cold. So a clean plan or build costs one reviewer and a
defective one costs two, instead of every one paying for breadth up front.
**Only the spec moment still opens wide** (3, then 2) — a spec defect
propagates into the plan and the build stacked on top of it, so that is the
one artifact where breadth is bought before the fact rather than after.
*(Owner ruling, 2026-07-25: the gate had grown to cost more than the work it
guarded — on a mechanical cleanup item the review outran the implementation
several times over. Supersedes the 2 Opus build/plan rounds of the same
day's 18:42 UTC entry.)*

This is a deliberate trade, and it is worth naming what it gives up: cold
reviewers **diverge sharply** — in a 2026-07-25 round the two Opus reviewers
overlapped on only two of eight findings, and the single most severe finding
of the whole run appeared in one reviewer's report and not the other's. A
one-reviewer round will therefore miss things a two-reviewer round would have
caught. The answer when that matters is **not** to quietly re-widen a row:
it is to give the work a **spec** moment (the one round that still opens
wide), or to escalate to the owner.

**A round's headcount IS its parallel width.** Every reviewer in a round is
dispatched concurrently (all `Agent` calls in ONE message). Widening a round
buys less than it looks like it should: this machine runs only ~2 concurrent
subagents before the rest queue, so past that width a round serialises —
costing the wall-clock of two rounds while still being one. That is why the
ceiling is 3, at the spec moment alone, and why the plan and build moments
spend their second slot only when round 1 actually found something.

**Every row but `spec` is now a single reviewer.** Spec is the one moment
that opens wide, because it is the only artifact whose defects get built on
top of. Everything downstream — plan, build, docs — is one Opus, and buys
its second reviewer only by having needed one. Read the table as: *one
reviewer is the gate; a second is what a finding costs.*

| Moment / tier      | Round 1 | Round 2 — only if resolving round 1 changed the artifact
|--------------------|---------|---
| **spec** review    | 3 Opus  | 2 Opus
| **plan** review    | 1 Opus  | 1 Opus
| **build** review   | 1 Opus  | 1 Opus
| **docs-only**      | 1 Opus  | never — ONE round, max
| **trivial** change | 1 Haiku | never — the one round IS the whole gate

- **`build` is the DEFAULT row for anything non-trivial that is not a spec
  or a plan** — a code change, a ledger entry, a chore sweep, a board
  reorganisation. "Build" means *work that is finished*, not *code was
  written*, so no non-trivial change is ever left without a row.
- **A DOCS-ONLY change gets ONE round, maximum** — no round 2, even when the
  round produced fixes. Docs-only means it touches no code and no test:
  `CLAUDE.md`, `dev/docs/*`, `docs/*`, the board. (A **spec** or **plan** is
  a doc but keeps its own row — those two moments exist precisely to catch a
  design before it is built.) Documentation is cheap to correct after the
  fact and its failure mode is a stale sentence, not a silent defect, so a
  second cold round is not worth its cost.
- **The trivial and docs-only rows are TIERS, not moments** — each replaces
  whichever row the change would otherwise have taken, and neither has a
  spec or plan round. **A batch takes its least-trivial member's row:** nine
  doc typos plus one code fix is a build review, not a docs-only or trivial
  one.
- **NO Haiku reviewer rides along.** The trivial tier's single
  `Agent(model: "haiku")` pass is the ONLY place a cheap reviewer appears —
  in every other row, in both rounds, the table's Opus slots are the whole
  round. (A Haiku reviewer used to be added additively to every first
  round; it no longer is, because on this hardware the extra concurrent
  slot costs wall-clock time it did not repay.) The trivial tier's Haiku
  findings face exactly the same observability test below — a finding is
  never discounted for having come from the cheap reviewer.
- **Round 2 is smaller in HEADCOUNT, not in reading.** Its reviewers get
  the full updated artifact *plus* the diff since round 1 — they are cold,
  and a finding anywhere in the updated work counts, not just inside that
  diff. Handing over the diff is not priming; **what round 1 found is
  never disclosed** (see below).
- **A trivial change is one that changes no reader's understanding and no
  tool behavior**: a typo, a formatting fix, a comment, a `help=`
  rewording, a test rename, a broken link.
  - **NOT trivial, at any size:** anything that changes what a rule, doc,
    spec, plan, ledger entry, or engine-fact note *says* — every change to
    `CLAUDE.md`, `dev/docs/direction/*.md`, `dev/docs/rationale/*.md`,
    `dev/docs/rules/*.md`,
    `dev/docs/architecture.md`, `dev/docs/unrealed/*.md`, a spec/plan, or a
    spike write-up is a real change, because a future agent will act on it.
  - **NOT trivial:** anything that changes what the tool does, deletes
    anything, or changes executable behavior — including a one-line change
    to load-bearing code, exactly the case the cheap tier must not swallow.
    (A comment or a test rename does not change executable behavior; a
    `help=` string is user-visible output, so rewording one is **docs-only**,
    not trivial.)
  - **The two NOT-trivial lists WIN over the examples above.** A typo or a
    broken link inside one of the rule/doc files named above is not trivial
    just because typos are listed as trivial.
  - **When it is arguable, it is not trivial.**
  - **If the Haiku pass shows the change was not trivial after all**, it is
    re-gated from scratch at its real tier — the cheap pass does not count
    as that tier's round 1.

**Reviewers get CONTEXT but never PRIMING.** These are two different
things and only one of them is forbidden:

- **Context is REQUIRED.** A reviewer who does not know the conventions
  cannot tell a deliberate choice from a defect. Give every reviewer this
  `CLAUDE.md`, and for a **plan** or **build** review the spec (and plan)
  it implements — a build reviewer who has not read the spec cannot check
  conformance to it.
- **Priming is FORBIDDEN.** Never show a reviewer the previous round's
  findings, never say what you expect them to find, never reuse a reviewer
  from an earlier round. A reviewer told what was already found stops
  looking for what wasn't.

**What blocks the gate.** There is no severity scale to calibrate — cold
reviewers cannot apply one consistently, and a scale invites arguing a
real finding down a tier. The test is observability:

> A finding may be left standing ONLY if fixing it would change nothing
> anyone would ever observe — pure wording, formatting, or naming taste.

Everything else is **fixed**, **logged** to `dev/docs/board/inbox.md` with
enough detail to act on, **escalated to the owner** as an explicit decision,
or **refuted** — the reviewer asserted something the code or doc does not
actually do. A refutation is admissible ONLY with the check that disproves
it recorded (commit message or board), and a round whose findings were all
refuted is still a round that happened, with its evidence written down.
Never waved through because the round was otherwise clean, or because it is
pre-existing. A finding that is real but out of scope still
blocks the round until it is logged — logging is what makes deferring
legitimate; "noted in chat" is not, because chat scrolls away. **The same
standard applies to a finding you leave standing**: its stated reason goes
in the commit message or on the board, never only in chat.

**TWO ROUNDS IS THE CEILING, and the second one is conditional.** Round 2
exists for exactly one reason: **the fixes are themselves unreviewed.** So
the trigger is whether the artifact CHANGED:

- **Round 2 runs iff resolving round 1 changed the artifact.** If round 1's
  findings were all dispositioned WITHOUT touching the artifact — logged to
  `dev/docs/board/inbox.md`, refuted, or escalated — there is no new,
  unreviewed text to look at, and the gate is passed at round 1. Same when
  round 1 came back clean. On small changes this is the common case and it
  is where most of the gate's cost is saved.
  - **"The artifact" = the files under review**, excluding
    `dev/docs/board/*` and the commit message. Logging a finding to the
    board is therefore never itself the trigger, even when board files are
    part of the diff; changing a doc or adding a test to resolve a finding
    IS.
- **This is NOT a licence to log instead of fix.** The disposition rule
  above is unchanged: logging is for a finding that is real but genuinely
  out of scope for *this* change. Choosing to log an in-scope defect so
  that round 2 never fires is gaming the gate, and the finding's stated
  reason (which the rule above requires on the board or in the commit
  message) is exactly where that shows.
- **After round 2, the gate is passed.** Anything still standing is
  **fixed**, **logged** to `dev/docs/board/inbox.md`, or **escalated to
  The owner** — all three outlets of the rule above stay open — and the work
  is declared done. There is no round 3: a third round of cold reviewers
  on a twice-fixed artifact buys less than it costs.
- **A STRUCTURAL finding STOPS the work, in EITHER round.** If a round's
  findings say the *design* is wrong rather than that a detail is wrong,
  stop and escalate to the owner. It **replaces** the remaining round — never
  licenses a third — and it does **NOT pass the gate**: the work is parked,
  not declared done and not merged, until the owner rules, after which the
  artifact re-enters the gate at round 1 of its tier. (So a structural
  escalation is not a cheap "fix-free round 1".) That pattern does not
  converge, and another round would not have landed it either.
- **Expect round 2 to find NEW things** — a fix can introduce a defect, and
  cold reviewers diverge; on 2026-07-25 a round found that the previous
  round's own *fixes* had shipped three wrong measurements and an unpinned
  spike finding (evidence: `dev/docs/direction/process.md`).
  Finding something in round 2 is normal, not a signal that the ceiling is
  wrong.

**NEVER restate the reviewer counts outside this file.** A spec, plan, or
board item that spells out "two cold reviewers" goes stale the moment the
gate changes — and it has, repeatedly. Cite **`CLAUDE.md` "Review gates"**
instead and let the count live in exactly one place.

**BATCH small changes into one round — don't gate each separately.** A
review round costs real tokens, so the unit of review is a coherent batch
of work, not an individual edit. Accumulate small changes (a chore sweep,
a set of doc corrections, several independent one-file fixes) and review
them together in a single round covering the whole diff. Reviewers see
more, not less, this way: a batch diff exposes inconsistencies between
sibling changes that per-change rounds structurally cannot see.

- **Land the batch, then gate it.** Commit each small change as it is
  finished (per **Commits** below) — **pushing deliberately does NOT wait
  for the gate.** The gate runs over the accumulated range before the
  batch is declared done, not before each commit.
- **Flush the open batch** before ending a session, before switching to
  unrelated work, or as soon as it is large enough to be worth a round —
  whichever comes first. A batch is never carried across a context
  boundary, and a lone trivial change with nothing to batch against is
  gated at that flush rather than waiting forever for company.
- **Split a batch when it stops being reviewable** — when the diff is
  large enough that a reviewer would skim, or when one risky change would
  hide among many safe ones. A subtle change to load-bearing code gets its
  own round even if it is one line; a hundred lines of mechanical rename
  does not.
- **Never batch across the three moments.** A spec review, a plan review
  and a build review are different questions over different artifacts.

### Feature worktrees

**A FEATURE is built in its own git WORKTREE and squash-merged back into
the branch it was branched from.** A *worktree* is a second working
directory for the same repository, checked out on its own branch: the
files are separate on disk, the git history is shared, so nothing is
cloned and nothing is pushed to move work between them.

**Why a worktree and not just a branch.** Several agent sessions work this
repo at the same time. `git checkout` in the shared checkout swaps the
files under every other session mid-edit; a worktree cannot, because each
session keeps its own directory. That is also why this process never
switches the main checkout's branch.

**The base is the branch the main checkout is already on — do NOT ask which
branch, and do NOT switch it.** That one branch is both the branch-off
point and the merge target.

1. **Create it**, from the main checkout (repo root, two levels above this
   file):

   ```
   base=$(git rev-parse --abbrev-ref HEAD)
   git worktree add .claude/worktrees/<feature-slug> -b <feature-slug> "$base"
   ```

   `.claude/worktrees/` is gitignored, so the second checkout is invisible
   to git, ripgrep and the test runners. Never name a worktree `agent-*` —
   that prefix belongs to Claude Code's own agent isolation. (The harness
   equivalent is the `EnterWorktree` tool, which creates a worktree in the
   same directory and moves the session into it. It branches from
   `origin/<default-branch>` unless the repo's `.claude/settings.json` sets
   `worktree.baseRef: "head"` — which this repo does, so `EnterWorktree`
   also branches from the current branch.)

2. **Build the feature in the worktree, committing locally as you go** —
   **Commits** below applies inside a worktree exactly as it does in the
   main checkout. A fresh worktree has no `.venv/` (it is gitignored), so
   the first `bin/test` there pays the venv-creation cost once.

3. **NEVER push the feature branch.** It is squashed away on merge and a
   remote branch can never be deleted, so pushing one strands permanent
   dead weight on `origin`. In-progress work is protected by local commits
   and by the branch being short-lived. This is the one exception to
   *always push your work* below.

4. **Gate in the worktree, before merging** (see **Review gates** above).
   Reviewers read the worktree's diff against the base:
   `git diff "$base"...HEAD`. Only a **passed gate** earns the merge — a
   clean or fix-free round 1, or a resolved round 2. Never a round 3
   hunting for a clean sheet.

5. **Squash-merge from the MAIN checkout** — a squash merge must run where
   the base branch is checked out, which is the main checkout, one more
   reason not to switch its branch:

   ```
   git diff --cached --quiet || echo "index dirty — another session staged something; STOP"
   git merge --squash <feature-slug>
   git commit -m "<one short imperative subject>"
   git push
   ```

   **Check the index first, as above.** `git merge --squash` stages the
   whole merged result and the following `git commit` commits *everything*
   staged — including whatever a concurrent session had staged. If the
   index is not clean, stop and sort that out rather than committing over
   another session's staged work.

6. **Clean up — but verify before deleting anything.** Confirm the base now
   contains the work (`git diff <feature-slug> HEAD` prints nothing), then
   `git worktree remove .claude/worktrees/<feature-slug>`. The branch
   itself needs `git branch -D`, because `-d` refuses — a squash merge
   records no merge — and **deleting a branch is destructive, so ask
   the owner first.** Leaving the local branch costs nothing; never delete it
   while that `git diff` is non-empty. (`ExitWorktree` with
   `action: "remove"` is the harness equivalent and needs
   `discard_changes: true` after a squash merge, for the same reason `-d`
   refuses — say so plainly when asking, since that flag is what discards
   the pre-squash commits.)

**A change that is not a feature** — a doc correction, a chore sweep, a
one-file fix — needs no worktree: it stays on the checked-out branch and
follows the batching rules above.

### Commits

**Commit after every change.** Once a change is complete — code, docs,
TODO updates, all of it — commit it before moving on, without waiting
to be asked. Stage only the specific files you touched by explicit
pathspec (`git commit -- <paths> ...`); never `git add .` or `git
commit -a` (a concurrent agent may have staged its own files). Short
imperative subject, no `type:` prefix, no AI attribution.

**Always push your work — never lose it.** After committing, `git push`
so the work lands on the remote and is never stranded only in a local
checkout. **NEVER REWRITE HISTORY, locally OR on `origin`.** No `git push
--force` (or `--force-with-lease`), no `git commit --amend`, no `git
rebase` that rewrites already-pushed commits — nothing of that kind. Only
ever add new commits on top; mistakes are corrected with a fresh commit
(or a `git revert`), never by rewriting what is already there.

### Code & CLI conventions

- **NO BACK-COMPAT CRUFT — uedcli is UNRELEASED.** There are no external
  users and no scripts in the wild, so nothing is ever kept for backward
  compatibility. When you remove or rename a flag, verb, option value,
  output format, or code path, **delete it outright** in the same change
  that adds the replacement — the new spelling is the only spelling.
  Never add or keep: a deprecated alias, a no-op flag "so old invocations
  still work", a migration-error shim (a flag defined only to
  `parser.error("X was renamed to Y")`), dual-format support kept to
  avoid re-writing callers, or an "old way" branch in code/tests/docs.
  Every shim is permanent maintenance surface and a second thing to keep
  true in the docs. *(`dev/docs/direction/conventions.md` "No
  back-compat cruft". Superseded only when uedcli is released.)*
- **No silent half-answers.** A command that can't fully satisfy a
  request exits 2 naming the offending value, rather than emitting a
  partial result plus a stderr warning — stderr scrolls away and the
  caller takes the partial answer for a complete one. *(decision
  2026-07-24 21:58)*
- **Every command and argument needs a `help=` string** that explains
  what it actually does, so `-h`/`--help` is self-explanatory — never
  just a restatement of the flag name.
- **Never let a Python exception reach the CLI user.** A bad
  actor/entity name must raise a clear error naming the offending value
  (`Actor not found: Foo`) and exit non-zero — never a bare
  `KeyError`/`IndexError` traceback. Cover each path with a regression
  test.
- **Verbs compose — this is the CORE CLI philosophy.** Build small,
  single-purpose verbs that pipe together; do NOT grow big verbs with
  many bespoke flags. Concretely:
  - **Producer/query verbs print their result to stdout, one item per
    line** — pipe-friendly (`actor find` prints matching names; `actor
    add` prints the allocated names; a generator prints a T3D snippet).
    Human summaries/counts go to **stderr** so they never pollute the
    pipe. Add **`--json`** where a script needs structured output rather
    than lines.
  - **Mutating/consuming verbs read their target set from stdin via
    `-`** — so `actor find --folder castle.tower | actor prop set -
    Texture=…` and `brush build cube | actor add -` close the loop
    instead of copy-paste / `$(…)`. `-` is the SOLE names source
    (mutually exclusive with names as CLI args); empty stdin is a clean
    no-op (exit 0), not an error.
  - **Two stdin conventions, disambiguated by verb:** a **name list**
    (`find → mutate -`) vs a **T3D snippet** (`build → add -`). Keep them
    distinct; don't blur them.
  - **A verb over a SET takes the set, and that IS the operation** — pass
    names (or `-`); the multi-item behaviour needs no extra flag. E.g.
    `actor bbox <names…>` returns the box enclosing ALL of them, so there
    is **no `--union`** — `actor find --folder X | actor bbox -` already
    gives the union. Never add a flag that merely restates "operate on
    this set."
  - **Prefer a stateless `find`/query verb** that prints matching names
    (by folder, class, property, …) for other verbs to consume, over
    per-command `--only-groups`/`--only-actors` filter flags sprinkled on
    every verb.
  - **`find` vs `search` — name by what's queried, never merge them.**
    `find` = a deterministic query over concrete **T3D-tree state**
    (actors/polys/brushes that exist in the trunk), producing an exact
    name/selector set to pipe onward (`actor find`, `brush poly find`).
    `search` = ranked/fuzzy **discovery over a catalog or corpus**
    (textures, the asset catalog, docs) — *what exists* by relevance, not a
    known set (`texture search`; future `catalog search`/`docs search`).
    *(`dev/docs/direction/conventions.md` "`find` vs `search`".)*

### Direction docs — NEVER revise without confirmation

`dev/docs/direction/<topic>.md` holds what **the owner** decided — product intent
and process rulings alike. It is **MUTABLE**: revised in place, no supersession,
no dated-entry history (git keeps that). Evidence citations and live-finding
dates ARE kept, per **Documentation** below.

Be clear-eyed about what that costs. The old append-only ledger meant a
violation still **preserved the prior text**, and stood out because the file's
diffs were otherwise pure appends. Revise-in-place destroys the prior text and
makes a bad edit look exactly like a good one. **Nothing mechanical replaces
that** — no hook, no check. The rule below is a convention, and the trailer is
an audit marker, not a gate.

- **NEVER create, revise, reword, or delete anything under
  `dev/docs/direction/` — including a single `Rejected` bullet — without asking
  The owner and getting an explicit yes.** Propose the exact text and wait.
  "It follows from what he said" does NOT satisfy this.
- **`direction/README.md` is the exception**: its index rows and its short model
  statement may be maintained freely. No topic *content* goes there, and it may
  **never** contain an `@` import.
- **Moving a topic OUT of `direction/` needs their yes too** — it removes the
  protection, so it is as much a change as an edit.
- **When direction looks stale, ASK — never edit.**
- **Confirm proactively.** When working in a topic, ask whether its direction
  doc is still current.
- **A decision awaiting their yes is parked** as an `[OWNER — confirm]` item on
  `board/inbox.md` carrying the proposed text verbatim.
- Commits touching `dev/docs/direction/` carry a `Confirmed: <topic>` trailer,
  so `git log --grep='Confirmed' -- dev/docs/direction/` shows every confirmed
  edit and an unconfirmed one stands out on inspection. (Four commits from
  2026-07-26 predate the rename and carry `Andrzej-confirmed:` instead —
  history is never rewritten, so grep for both when auditing that day.)

**`dev/docs/andrzej.md` and `dev/docs/2026-06-20-open-questions-for-andrzej.md`
are also theirs — do not touch them at all.**

Every other doc under `dev/docs/`, including `rationale/` and `rules/`, an agent
maintains on its own.

### Documentation

**Keep the user-facing docs current with the CLI — this is not optional.**
Whenever a change alters behavior a user can observe — a new verb, a changed
flag, different output, a new capability, a removed feature — update the
user-facing docs in the same change so they never describe a CLI that no longer
exists. The user-facing surface is `docs/usage.md` (the CLI reference: verbs,
flags, output) and `docs/leveldesign/` (level-design craft mapped onto the
verbs). The whole-tree "which doc is for what" table — authoritative on which
doc owns what — lives in `dev/docs/README.md` (`docs/README.md` is itself just
the user-facing index). Add a new doc (or a new section) when a verb or feature is
substantial enough that a user would look for it and not find it — err toward
documenting. (The dev docs track *how it's built*; keep them current too, per
below — but the user-facing docs are the first thing to update when functionality
changes.)

**`docs/` is ALL user-facing; developer docs are a SEPARATE tree.** Everything
under `docs/` (`usage.md`, `leveldesign/`) is written for uedcli *users* — the
LLM level-designer driving the CLI. The developer/internal docs (architecture,
direction, decisions, spikes, board, the `unrealed/` engine notes, the dev `kb/`)
are for uedcli *developers*, a different audience. **User-facing docs must NEVER
reference the developer docs** — no links or paths to spikes, the board,
decisions, architecture, etc.: a user cannot open them and must not be sent
there. State the fact plainly in the user doc instead (with a confidence marker
if it's an engine claim), and put the evidence pointer in the *developer* doc.
Symmetrically, developer docs freely cite spikes/decisions/each other. (The
developer tree lives at `dev/docs/` — renamed from the old `docs/dev/` — so
`docs/` is physically all user-facing and any dev reference from a user doc is
an obvious leak.)

**Markdown tables — align for a plain-text editor (vim).** Pad every column to
its widest cell so the interior pipes line up vertically, **except the final
column**: leave its content unpadded so a long prose column doesn't spawn huge
trailing-whitespace runs or 200+ char lines. Separator dashes fill each padded
column's width; the final column's separator stays a short `---`. The result:
the label/short columns are scannable, the wide prose column flows to its
natural length. (Applies to all docs, not just `dev/docs`.)

Always document new learnings about how UnrealEd functions, what our goals are, or architectural choices/changes in `dev/docs`.

UnrealEd knowledge is ESPECIALLY important, because the public documentation is very lacking and discovering the knowledge is expensive.

**Write every doc for a reader with NO familiarity with the implementation.** Assume the
reader does not know the code, the substrate, the prior conversation, or the jargon. Be clear,
concrete, and very explicit: define terms before using them, spell out the mechanism, and never
lean on context the reader doesn't have. An explanation that only makes sense if you already
know how it works is a bug — rewrite it.

**The dev docs split by role — keep each in its lane, and keep each current:**
- **`architecture.md` + `unrealed/*.md`** — *what IS* (current implementation + verified engine
  facts). **MUST be updated to match whenever the implementation changes** — no doc may be left
  describing code that no longer exists or behavior that changed.
- **`direction/<topic>.md`** — *what the OWNER decided*: product intent AND process rulings.
  **Revised in place** to state the current answer — no supersession, no dated-entry history
  (git keeps that). A gap between `direction/` and `architecture.md` is expected (it's work not
  yet done). **You may NEVER write this tree without their explicit yes** — see **Direction docs**
  above.
- **`rationale/<topic>.md`** — *why the CODE is the way it is*: the engineering decisions an
  agent made (a tolerance, a scope limit, a format choice), keyed by module or subsystem. Also
  **revised in place**; agents maintain it freely. Every entry states **Why it is this way**,
  **Rejected** (alternatives killed, so nobody re-proposes them) and **Refs** (spike/code
  pointers). Point a durable doc here for rationale — never at an ephemeral spec.
- **`specs/` + `plans/`** — ephemeral per-feature scratch (below). **`spikes/`** — durable evidence.

**`dev/docs/specs/` and `dev/docs/plans/` are ephemeral** — scratch for designing
and sequencing a piece of work, expected to go stale or get deleted once that
work lands. They are NEVER the durable record. Once something is implemented,
fold what was actually built, any design decision made along the way, and the
resulting general direction into the global docs (`architecture.md`,
`unrealed/*.md`, or another `dev/docs/*.md` as fits) — so the knowledge survives
even if the originating spec/plan is later removed. (`spikes/` is different: it's
kept as durable evidence, cited from `architecture.md`/`unrealed/quirks.md` etc.)

**When speccing, record every decision I make** — the choice, the alternatives
rejected, and the reason — as I make it. A spec must capture what *I* decided,
not just your proposal; my answers to the design questions are the load-bearing
part and must not be lost or silently overridden. Because specs are ephemeral,
the decision must land in a **durable** doc before the spec is deleted:

- **A decision I made** → `dev/docs/direction/<topic>.md`, **revised in place**
  to state the new current answer. Propose the exact wording and wait for my
  yes (see **Direction docs** above). While it waits, park it as an
  `[OWNER — confirm]` item on `board/inbox.md` carrying the proposed text
  verbatim, so it survives the session ending.
- **A decision you made** (an implementation choice) →
  `dev/docs/rationale/<topic>.md`, revised in place, with its `Rejected`
  alternatives and its `Refs`.

**There is NO decisions ledger.** Nothing is append-only and nothing is
superseded — a doc is *edited* to say the current answer, and git holds what it
used to say. Never point a durable doc at a spec for "the rationale and rejected
alternatives"; point it at the owning `direction/` or `rationale/` topic.

**Every claim about how UnrealEd behaves carries its evidence.** Cite the
`spikes/` file it came from, and date any live finding (`confirmed live
2026-06-20`) — the editor is undocumented and crash-prone, so an undated,
uncited assertion can't be trusted or re-verified later.

**Tag UnrealEd facts in `unrealed/*.md` with a confidence marker:** ✅ =
uedcli-used / live-verified, 🔬 = live-probed, 📖 = extracted from the binary
string table (vocabulary real, semantics inferred). Don't state an extracted
fact with the certainty of a verified one.

### Read-on-demand docs — the router

Only `direction/README.md` (the topic index) is auto-loaded. **Every doc below is
NOT in your context — you MUST `Read` the relevant one before the action it
names.** These one-liners are a *router, not a substitute*: never answer a
question about UnrealEd behavior, the T3D format, uedcli internals, **or a
process rule** from this summary or from training memory — the editor is
undocumented and crash-prone, and these docs are the only ground truth. If a
task touches any row below and you have not read that doc **this session**,
read it first. (The docs cross-link each other, so one read surfaces the rest;
`dev/docs/README.md` has the full "which doc is for what" table.)

**A dispatched subagent does NOT inherit your reading.** When you hand work to
a subagent — a reviewer, a spike investigator, anything — its prompt MUST name
the docs it has to read before acting, by path. A subagent that has not read
`unrealed/t3d.md` will flag correct T3D handling as a bug; one that has not read
this file will flag deliberate conventions as defects. The rule above ("read the
relevant doc before the action it names") binds the subagent too, and only its
prompt can tell it so.

- **@dev/docs/direction/README.md** — *(auto-loaded, already in context)* the index of what we WANT. **Read the topic doc itself before any design question, spec or plan** — the index is a router, not the content.
- `dev/docs/direction.md` — **being retired.** Holds only the topics `direction/README.md` still marks *(pending)*; every other section is a pointer.
- `dev/docs/architecture.md` — **Read BEFORE any uedcli code change or design question**: the layer/module map, the model-side write pattern, invariants D1–D8, the session-store shape.
- `dev/docs/decisions.md` — **FROZEN, historical reading only — never append.** The retired ledger, migrating into `dev/docs/direction/` (the owner's decisions) and `dev/docs/rationale/` (yours). `dev/docs/rationale/MIGRATION.md` records where each entry went and is the map from an old dated citation to its new home.
- `dev/docs/unrealed/commands.md` — **Read BEFORE driving the editor console**: the exec-verb reference (what to type).
- `dev/docs/unrealed/t3d.md` — **Read BEFORE authoring/parsing T3D or editing surfaces/geometry**: block nesting, property forms, winding, authored-vs-computed taxonomy.
- `dev/docs/unrealed/quirks.md` — **Read BEFORE driving UnrealEd or debugging editor behavior**: the non-obvious traps (IMPORTADD grid-snap, demand-load, selectability, CSG).
- `dev/docs/unrealed/rendering.md` — **Read BEFORE taking a screenshot/render**: render modes, `CAMERA OPEN`, the black-viewport traps.
- `dev/docs/unrealed/extracting-from-dll.md` — **Read BEFORE mining the binaries** for command/behavior facts.
- `dev/docs/parallel-editors.md` — **Read BEFORE running many ephemeral editors** concurrently.

**Process rules** (`dev/docs/rules/README.md` indexes them). Each line carries the one fact you
cannot afford to miss; the doc carries the rest:

- `dev/docs/rules/tests.md` — **Read BEFORE running tests.** Run them via **`bin/test`**, never
  bare `pytest`; uedcli and its suite are **host-native, not containerised**.
- `dev/docs/rules/spikes.md` — **Read BEFORE starting or finishing a spike.** Commit the harness to
  `dev/docs/spikes/<slug>/`, never leave it in `_scratch/`; **pin every checkable finding with a
  committed regression test** or it rots.
- `dev/docs/rules/background-work.md` — **Read BEFORE starting a background job or long wait.**
  Never leave one on a single open-ended wait — the editor wedges *silently*; pair a tracked job
  with a ~20-minute hang-detector, and never poll on short wake-ups.

New UnrealEd findings go in `dev/docs/unrealed/` (and back-reference them from code comments).

### TODOs (`dev/docs/board/` — the stage-queue cluster)

The backlog is a set of **stage queues** under `dev/docs/board/`, each named
for the *next action* an item needs (read `dev/docs/board/README.md` for the
full flow). An item lives in exactly ONE queue and advances by moving its
line to the next file:

- `inbox.md` — raw, **un-triaged** capture; the pre-pipeline pool AND the
  head of stream (not a queue). Everything lands here first: ideas/gaps/
  bugs/chores, **anything you'd flag for the owner** (a provisional call, an
  assumption, a risk, a deviation from spec/plan, or work you deliberately
  didn't do — put it here INSTEAD of only saying it in chat, which scrolls
  away), and **their own open questions**. Triage moves each entry out to the
  queue for its next action; a question raised mid-pipeline bounces back
  here until answered. There is **no separate `flagged`/`to-resolve` lane** —
  The owner resolves their own items by deleting or triaging them forward
  (recording any real choice in the owning `dev/docs/direction/` topic).
- `to-spec.md` → `to-spike.md` → `to-plan.md` → `to-build.md` — the
  pipeline. `to-build.md` is the reviewed on-deck **build queue / source
  of truth** for what to build next.
- `done.md` — a short tail of recently-done + partially-done-with-remnants.
- *(Transitional: the general `[implement]`/`[chore]`/`[debug]` backlog,
  Active vs Deferred, still sits in `to-spec.md` pending a move to
  `inbox.md`.)*

The **bracket tag ≈ the queue**: `[spec]`→`to-spec`, `[spike]`→`to-spike`,
`[plan]`→`to-plan`. `[implement]` sits in `to-spec.md`'s backlog until a
**reviewed plan** lands it on `to-build.md`; `[chore]`/`[debug]` are one-shot
and **stage-less**, so they go straight to `to-build.md` with no plan — and
therefore no plan review round (this is the distinction **Review gates**
relies on to decide whether that round fires). `[spike]` is used only when a
spec flags a live unknown (findings fold back into that spec). Use `[a→b]` while
transitioning. `pN` (`p1`/`p2`/`p3`) priority rides each line.

When a TODO is fully finished, remove it from the list entirely — don't
leave it ticked `[x]` (`done.md` keeps only a short reference tail). If
something gets deferred mid-implementation, add a new, separate TODO for it
rather than letting the original entry quietly cover both the done part and
the deferred part.
