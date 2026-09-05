## Working with the owner

Every decision that is the owner's to make goes through Claude Code's `AskUserQuestion` widget, not
prose in the chat, where it gets skimmed, half-answered, or scrolls away. This covers design forks,
`direction/` rulings, sequencing calls, and anything a review escalates.

Never overrule the owner silently, and never downgrade a real question into a board item to avoid
asking it. If a rule of theirs points one way and you judge otherwise, that is a question for the
widget, not a deviation recorded in a commit message and moved past. The board is for a real finding
that is out of scope for the current change. *(Owner ruling, 2026-07-26.)*

### A decision is implemented as given, never altered without an explicit yes

Wherever the decision was made — a spec, chat, a one-line answer:

- Implement the ruling as stated. Do not add a guard, filter, clamp, fallback, or special case that
  changes what it does — not "in the spirit of" it, not to satisfy a different requirement they also
  stated, not because measurement shows it wrong.
- Finding a real flaw does not authorise a fix. Measure it, stop, report the evidence, propose the
  change, and wait for the yes.
- Telling them afterwards is not consent. Flagging an unrequested change in the report is the
  violation, not the remedy.
- An unanswered question is not an answer. Ask again; do not fill the gap with a default and call it
  a judgement call.
- Reverting works the same way: once told to drop an unapproved change, restore exactly what was
  ruled, including its known costs, and pin those costs in a test or doc so they are recorded rather
  than quietly re-fixed later.

### dev/docs — never edit without the owner's approval, except the board

Get the owner's explicit yes before you create, edit, reword, or delete anything under `dev/docs/` —
`architecture.md`, `rationale/`, `rules/`, `unrealed/`, `spikes/`, `direction/`, and the rest. Propose
the exact text and wait; "it follows from what they said" does not satisfy this. When a doc looks
stale, ask — do not edit.

The one exception is `dev/docs/board/`, which stays agent-operated: log findings
(`bin/board new inbox`), move items between stages, and trim `done/` entries without asking.

`dev/docs/direction/<topic>.md` is the strictest case and carries extra handling. **Default to
leaving it alone.** It records a genuinely new or changed *direction* — a shift in what the product
is or how the project is run — not the routine rulings that fall out of building. How one verb
behaves, a render rule, an exit code, a data shape: that folds into the item's `spec.md` (ephemeral)
and, for the why, `rationale/` — never a new or widened `direction/` topic. Touch `direction/` only
when the decision changes the topic-level intent itself; unsure it rises to that, keep it out and
ask. It holds what the
owner decided — product intent and process rulings alike — revised in place, no supersession, no
dated history (git keeps that); evidence citations and live-finding dates stay. Down to a single
`Rejected` bullet, do not touch it without a yes; moving a topic out needs a yes too.
`direction/README.md` is the exception within the exception: its index rows and short model statement
may be maintained freely (no topic content, never an `@` import). Park a decision awaiting a yes in the
`questions/` directory of the board item it concerns — the proposed text verbatim, empty `## Answer` —
added to its respective item, never logged as a standalone issue. A decision NO board item owns is
asked directly (`AskUserQuestion`), not filed as a standalone item. Commits
touching `dev/docs/direction/` carry a `Confirmed: <topic>` trailer.

Nothing mechanical enforces any of this. Why it is shaped this way: `dev/docs/direction/process.md`.

## Workflow

Always ask where to implement a change: a feature branch on a git worktree, the current checkout
(usually master), or somewhere else.

## Code & CLI conventions

The detail and the rejected alternatives live in `dev/docs/direction/conventions.md`; the core:

- No back-compat cruft — uedcli is unreleased. No external users, no scripts in the wild, so nothing
  is kept for backward compatibility. When you remove or rename a flag, verb, option value, output
  format, or code path, delete it outright in the change that adds the replacement — the new spelling
  is the only spelling. Never a deprecated alias, a no-op flag, a migration-error shim, dual-format
  support, or an "old way" branch. *(Superseded only when uedcli is released.)*
- No fallbacks, and no silent half-answers — for any command or script — unless the owner explicitly
  asked for or agreed to one. A command that can't fully satisfy a request exits 2 naming the offending
  value, never a partial result plus a stderr warning that scrolls away, and never a substituted
  default for something it couldn't resolve. Never switch behavior on the environment either: a verb
  does the SAME thing on every host — same code path, same engine, same output — never branching on CPU
  arch, OS, an env var, or the presence/absence of a tool to pick a different implementation. When an
  approach is specified (e.g. a dockerized setup), it is the only path: a missing host tool is a broken
  host to FIX, surfaced as a clear error, never a reason to silently keep a second code path (a host
  path "in case docker isn't there"). *(Owner rulings, 2026-07-27 / 2026-08-06 / 2026-08-24.)* Full rule:
  `dev/docs/direction/conventions.md`.
- Never let a Python exception reach the user. A bad actor/entity name exits non-zero with a clear
  message naming the value (`Actor not found: Foo`), never a bare `KeyError`/`IndexError` traceback.
  Cover each path with a regression test.
- Every command, flag, and argument needs a real `help=` that says what it does, so `-h`/`--help` is
  self-explanatory rather than a restatement of the flag's own name.
- Verbs compose — the core CLI philosophy. Small, single-purpose verbs that pipe together, not big
  verbs grown a bespoke flag at a time:
  - Producer/query verbs print their result to stdout, one item per line; human summaries and counts
    go to stderr; add `--json` where a script needs structure rather than lines.
  - Mutating/consuming verbs read their target set from stdin via `-`, the sole names source
    (mutually exclusive with names as CLI args); empty stdin is a clean no-op (exit 0), not an error.
  - Two stdin conventions, disambiguated by verb: a name list (`find → mutate -`) and a T3D snippet
    (`build → add -`). Keep them distinct.
  - A verb over a set takes the set, and that is the operation — no flag that merely restates
    "operate on this set" (`actor bbox <names…>` has no `--union`).
  - Prefer one stateless `find`/query verb feeding the others over per-verb `--only-*` filter flags.
  - `find` vs `search`, never merged: `find` is a deterministic query over concrete T3D-tree state,
    producing an exact name/selector set to pipe onward; `search` is ranked/fuzzy discovery over a
    catalog or corpus (textures, the asset catalog, docs).

## Keep it short and plain

Each document, docstring, code comment, commit message, and board item — including this file — should
be as short as possible without losing meaning, and written in plain language. These are the rules
most often broken.

- Write plainly: direct, matter-of-fact sentences. Avoid ornate or dramatic phrasing, all-caps
  emphasis, slogan headings, and repetition for effect.
- Delete first. If text can be removed and a reader would still act the same way, remove it —
  sentence, bullet, heading, or example.
- Add length only to explain something a reader needs, not to signal importance or look thorough.
- Cut padding, not explanation. Padding is restatement, hedging, and ceremony; explanation is the
  mechanism. The "write for a stranger" rule under Documentation still applies.
- Leave a doc you edit shorter than you found it, unless the edit added meaning.

*(Owner ruling, 2026-07-27, re-emphasised 2026-07-28.)*

## Documentation

Read `dev/docs/rules/documentation.md` before writing or restructuring docs — it carries the
markdown-table alignment convention, which developer doc owns what, the specs-and-plans-are-ephemeral
rules, and how UnrealEd facts are cited and confidence-tagged. The three rules below bind everywhere:

- Write every doc for a reader with no familiarity with the implementation. Define terms before using
  them, spell out the mechanism, and do not lean on context the reader lacks. An explanation that
  only makes sense if you already know how it works is a bug — rewrite it.
- Keep the user-facing docs current with the CLI. Whenever a change alters behavior a user can
  observe — a new verb, a changed flag, different output, a removed feature — update the matching
  `docs/reference/<family>` page (or `docs/usage/` if the change is workflow-shaped) and
  `docs/leveldesign/` in the same change.
- `docs/` is all user-facing and must never reference the developer tree (`dev/docs/`): a user cannot
  open a spike, the board, or `architecture.md` and must not be sent there.

New level-design knowledge in `docs/` — best practices, craft guidance, recipes, human-scale numbers,
any engine or design claim (mostly `docs/leveldesign/`) — needs the owner's approval before you add
it; inaccurate craft knowledge is costly and hard to catch. Rephrasing existing `docs/` content is
fine, and so is documenting how a uedcli tool behaves (verbs, flags, output in the matching
`docs/reference/<family>` page, or `docs/usage/` if the change is workflow-shaped), which is
checkable against the CLI.

Document new learnings about how UnrealEd functions, our goals, or architectural choices in `dev/docs`
— `dev/docs/unrealed/` for engine findings, back-referenced from code comments. The public
documentation is very lacking and discovering this knowledge is expensive.

## The board — the backlog, and where findings go

The board is one directory per work item (`dev/docs/board/<stage>/<slug>/overview.md`, plus optional
`spec.md`, `plan.md`, and `questions/<q>.md`). The stage queues are named for the next action an item
needs: `inbox/` (un-triaged capture, including anything you'd flag for the owner) → `to-spec/` →
`to-spike/` → `to-plan/` → `to-build/` (the ready-to-build queue), plus `someday/`, `stale/`, and
`done/`. An item advances with a single `git mv`. Read `dev/docs/board/README.md` before working the
board — stages, frontmatter, slugs, and the question flow.

Two rules bind every session:

- Run `bin/board answered` at session start, and before pulling work off `to-build/`. A question the
  owner has answered is invisible otherwise. The commit that folds an answer out also deletes the
  question file — if you find it already gone, another session has done it; stop.
- A question raised mid-pipeline does not move its item. Write it into that item's own `questions/`
  directory and leave the item in whatever stage it had reached. *(Owner ruling, 2026-07-27.)*

`bin/board questions|answered|ls|show|new` — `bin/board --help`. It needs no venv.

## Read-on-demand docs — the router

`direction/README.md` (the topic index), the root `NATIVE-MATERIALIZE.md` (the native-materialize
→ UED22 byte-parity campaign), and the root `USCRIPT-COMPILER.md` (the UnrealScript compiler →
UCC.exe byte-parity campaign) are auto-loaded. Every other doc below is not in your context;
read the relevant one before the action it names. These one-liners are a router, not a substitute: do
not answer a question about UnrealEd behavior, the T3D format, uedcli internals, or a process rule
from this summary or from training memory — the editor is undocumented and crash-prone, and these
docs are the only ground truth. If a task touches any row below and you have not read that doc this
session, read it first. (`dev/docs/README.md` has the full "which doc is for what" table.)

A dispatched subagent does not inherit your reading. When you hand work to a subagent — a spike
investigator, a wide multi-file search, anything — its prompt must name the docs it has to read
before acting, by path. A subagent that has not read `unrealed/t3d.md` will flag correct T3D handling
as a bug; one that has not read this file will flag deliberate conventions as defects.

- @dev/docs/direction/README.md — *(auto-loaded)* the index of what we want. Read the topic doc itself before any design question, spec, or plan — the index is a router, not the content.
- @NATIVE-MATERIALIZE.md — *(auto-loaded)* the native-materialize → UED22 full-byte-parity campaign: the goal, the UED22 reference recipe (MAP IMPORT + sacrificial dummy builder), the exact parity bar and its opus-confirmed exclusions, the lockstep-ladder method, and the ONE canonical parity script (`parity_gate.py`). Read and obey it before ANY native-materialize or parity work — do not re-derive it.
- @USCRIPT-COMPILER.md — *(auto-loaded)* the UnrealScript compiler → UCC.exe byte-parity campaign: the goal, the three reference substrates (UED22/UT99/DXORIG) and why each exists, the parity bar, current status + byte-exact package table, the crux RE findings (ordering algorithm, CRC, flags, conversation `#exec`), and the open gaps. Read and obey it before ANY uscript-compiler work — do not re-derive it. Detailed RE facts live in `dev/docs/unrealed/unrealscript/` (the sole home for that knowledge).
- `dev/docs/architecture.md` — read before any uedcli code change or design question: the layer/module map, the model-side write pattern, invariants D1–D8, the session-store shape.
- `dev/docs/unrealed/commands.md` — read before driving the editor console: the exec-verb reference (what to type).
- `dev/docs/unrealed/t3d.md` — read before authoring/parsing T3D or editing surfaces/geometry: block nesting, property forms, winding, authored-vs-computed taxonomy.
- `dev/docs/unrealed/quirks.md` — read before driving UnrealEd or debugging editor behavior: the non-obvious traps (IMPORTADD grid-snap, demand-load, selectability, CSG).
- `dev/docs/unrealed/rendering.md` — read before taking a screenshot/render: render modes, `CAMERA OPEN`, the black-viewport traps.
- `dev/docs/unrealed/extracting-from-dll.md` — read before mining the binaries for command/behavior facts.
- `dev/docs/unrealed/unrealscript/` — the SINGLE home for reverse-engineered UnrealScript + `UCC.exe` compilation knowledge (language, bytecode, `.u` script-object serialization, the compile model). Read the relevant topic before any UnrealScript-compiler work; record new RE facts here and nowhere else.
- `dev/docs/parallel-editors.md` — read before running many ephemeral editors concurrently.

Process rules (`dev/docs/rules/README.md` indexes them). Each line carries the one fact you cannot
afford to miss; the doc carries the rest:

- `dev/docs/rules/building-features.md` — read before building a `to-build/` item and merging it. The runbook: build in a worktree, verify (checks + tests + exercise it), one subagent review, move the item to `done/`, squash-merge as one commit.
- `dev/docs/rules/build-run.md` — read before running a batch of `to-build/` items in one pass. The loop over the per-item runbook: worktree each, serialize the squash-merges onto fresh master, queue new items last, retry-once-then-file-a-finding on a failure.
- `dev/docs/rules/documentation.md` — read before writing or restructuring docs. Table alignment, which dev doc owns what, ephemeral specs/plans, UnrealEd evidence and confidence markers.
- `dev/docs/rules/worktrees.md` — read before creating a worktree or squash-merging one. Never push a feature branch; check the index before `git merge --squash`; ask before `git branch -D`.
- `dev/docs/rules/tests.md` — read before running tests. Run them via `bin/test`, never bare `pytest`; uedcli and its suite are host-native, not containerised.
- `dev/docs/rules/spikes.md` — read before starting or finishing a spike. Commit the harness to `dev/docs/spikes/<slug>/`, never leave it in `_scratch/`; pin every checkable finding with a committed regression test or it rots.
- `dev/docs/rules/background-work.md` — read before starting a background job or long wait. Never leave one on a single open-ended wait — the editor wedges silently; pair a tracked job with a ~20-minute hang-detector, and never poll on short wake-ups.
