## Working with the owner

Every decision that is the owner's to make goes through Claude Code's `AskUserQuestion` widget, not
prose in the chat, where it gets skimmed, half-answered, or scrolls away. This covers design forks,
`direction/` rulings, sequencing calls, and anything a review escalates.

Never overrule the owner silently, and never downgrade a real question into a bd issue to avoid
asking it. If a rule of theirs points one way and you judge otherwise, that is a question for the
widget, not a deviation recorded in a commit message and moved past. The tracker is for a real
finding that is out of scope for the current change. *(Owner ruling, 2026-07-26.)*

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

### dev/docs — never edit without the owner's approval

Get the owner's explicit yes before you create, edit, reword, or delete anything under `dev/docs/` —
`architecture.md`, `rationale/`, `rules/`, `unrealed/`, `spikes/`, `direction/`, and the rest. Propose
the exact text and wait; "it follows from what they said" does not satisfy this. When a doc looks
stale, ask — do not edit.

Issue tracking is agent-operated and lives in beads (`bd`), not under `dev/docs/`. The residual
`dev/docs/board/` (one in-flight item cluster plus `bd-id-map.tsv`) is also agent-operated.

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
may be maintained freely (no topic content, never an `@` import). Park a decision awaiting a yes on
the bd issue it concerns: append an `## Open question` section with the proposed text verbatim and
set the issue `blocked` — never a standalone issue. Only when NO issue owns the decision do you file
one standalone (`bd create '[OWNER — confirm] …' -t task -l owner-question`, status `blocked`).
Commits touching `dev/docs/direction/` carry a `Confirmed: <topic>` trailer.

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

Each document, docstring, code comment, commit message, and bd issue — including this file — should
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

## Issues — the backlog, and where findings go

Issues live in beads (`bd`); the Beads Issue Tracker section below has the command reference. The
2026-09-02 migration from `dev/docs/board/` is mapped in `dev/docs/board/bd-id-map.tsv`; old
``board item `slug``` citations resolve through it. Specs live in an issue's design field, plans in
its notes field.

Three rules bind every session:

- Log a finding with `bd create '<title>'`. Anything that would otherwise live only in chat goes
  here: a provisional call, an assumption, a risk, a deviation from spec/plan, work you deliberately
  didn't do. If something gets deferred mid-implementation, file a separate issue rather than letting
  the original cover both halves.
- Check `bd list --status blocked` at session start and before pulling work off `bd ready`. A
  blocked issue carries an `## Open question` for the owner; when the owner has answered (a comment
  or an edit), fold the decision into its durable home (`direction/` for the owner's rulings,
  `rationale/` for an agent's), then unblock the issue.
- A question raised mid-pipeline does not close or re-queue its issue. Append it to that issue and
  set it `blocked`. *(Owner ruling, 2026-07-27.)*

## Read-on-demand docs — the router

Only `direction/README.md` (the topic index) is auto-loaded. Every doc below is not in your context;
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
- `dev/docs/architecture.md` — read before any uedcli code change or design question: the layer/module map, the model-side write pattern, invariants D1–D8, the session-store shape.
- `dev/docs/unrealed/commands.md` — read before driving the editor console: the exec-verb reference (what to type).
- `dev/docs/unrealed/t3d.md` — read before authoring/parsing T3D or editing surfaces/geometry: block nesting, property forms, winding, authored-vs-computed taxonomy.
- `dev/docs/unrealed/quirks.md` — read before driving UnrealEd or debugging editor behavior: the non-obvious traps (IMPORTADD grid-snap, demand-load, selectability, CSG).
- `dev/docs/unrealed/rendering.md` — read before taking a screenshot/render: render modes, `CAMERA OPEN`, the black-viewport traps.
- `dev/docs/unrealed/extracting-from-dll.md` — read before mining the binaries for command/behavior facts.
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


<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:6cd5cc61 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Agent Context Profiles

The managed Beads block is task-tracking guidance, not permission to override repository, user, or orchestrator instructions.

- **Conservative (default)**: Use `bd` for task tracking. Do not run git commits, git pushes, or Dolt remote sync unless explicitly asked. At handoff, report changed files, validation, and suggested next commands.
- **Minimal**: Keep tool instruction files as pointers to `bd prime`; use the same conservative git policy unless active instructions say otherwise.
- **Team-maintainer**: Only when the repository explicitly opts in, agents may close beads, run quality gates, commit, and push as part of session close. A current "do not commit" or "do not push" instruction still wins.

## Session Completion

This protocol applies when ending a Beads implementation workflow. It is subordinate to explicit user, repository, and orchestrator instructions.

1. **File issues for remaining work** - Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Handle git/sync by active profile**:
   ```bash
   # Conservative/minimal/default: report status and proposed commands; wait for approval.
   git status

   # Team-maintainer opt-in only, unless current instructions forbid it:
   git pull --rebase
   git push
   git status
   ```
5. **Hand off** - Summarize changes, validation, issue status, and any blocked sync/commit/push step

**Critical rules:**
- Explicit user or orchestrator instructions override this Beads block.
- Do not commit or push without clear authority from the active profile or the current user request.
- If a required sync or push is blocked, stop and report the exact command and error.
<!-- END BEADS INTEGRATION -->
