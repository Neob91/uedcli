## The refactor

uedcli is being rewritten from Python into Rust, from an empty root; the old codebase lives under
`old/`. @dev/epics/refactor.md has the plan — read it before any question about scope, sequencing,
or `old/`'s shape.

This is a greenfield rewrite, not a byte-exact transliteration. Match old/'s behavior for the
normal case (verified by differential tests, per @dev/epics/refactor.md) — but don't hand-replicate
its exact quirky edge-case behavior (parser corner cases, Python-specific formatting) just to chase
parity. Real improvements are the point.

## Working with the owner

Every decision that's the owner's to make goes through the `AskUserQuestion` widget, not chat prose
(which gets skimmed, half-answered, or scrolls away) — design forks, sequencing calls, anything a
review escalates. Never override the owner silently, and never downgrade a real question to avoid
asking it.

This applies below the top level too: while turning an approved design into an exact spec (config
keys, on-disk layouts, field names, API shapes), ask about those details rather than deciding or
deferring them silently.

### A decision is implemented as given, never altered without an explicit yes

- Implement a ruling exactly as stated, wherever it was given (a spec, chat, a one-line answer) — no
  added guard, clamp, or special case, even one that "fits the spirit" or fixes a flaw you found. A
  flaw doesn't authorise a fix: report it and wait for a yes.
- Telling the owner afterward isn't consent — flagging an unrequested change in the report is itself
  the violation.
- An unanswered question isn't an answer — ask again rather than filling the gap with a default.
- Reverting follows the same rule: restore exactly what was ruled, including its known costs, and
  pin those costs in a test or doc so they aren't silently re-fixed later.

## Workflow

Always ask where to implement a change: a feature branch on a git worktree, the current checkout
(usually master), or somewhere else.

## Code & CLI conventions

- No back-compat cruft — uedcli is unreleased, so nothing is kept for compatibility. Removing or
  renaming a flag, verb, value, format, or code path means deleting it outright in the same change,
  never a deprecated alias, no-op flag, migration shim, or dual-format support. (This is about the
  CLI's own external surface, not the subprocess-strangler fallback to `old/`, which is migration
  scaffolding — see @dev/epics/refactor.md.)
- No fallbacks or silent half-answers, unless the owner agreed to one — a command that can't fully
  satisfy a request exits 2 naming the offending value, never a partial result or a substituted
  default. No branching on environment either: a verb behaves identically on every host. When an
  approach is specified (e.g. a dockerized setup), it's the only path — a missing host tool is a
  broken host to fix, not a reason to keep a second code path.
- Never let a panic reach the user. A bad input exits non-zero with a clear message naming the
  offending value, covered by a regression test.
- Every command, flag, and argument needs a real help string — `--help` should explain what it does,
  not restate its own name.
- Before putting a new type or function in a feature-specific module, check how broadly its old/
  equivalent is actually used (grep `old/`) — broad usage means it belongs under `core::`, not the
  feature that first needed it.
- Keep argument parsing separate from logic: a `cli::<verb>` module parses args (a real library,
  e.g. clap) and dispatches; the verb's own logic function takes typed parameters and knows
  nothing about the CLI.
- Names are explicit: no abbreviations (`texture`, not `tex`; `format`, not `fmt` — a loop counter
  like `i` or a generic `T` is fine), and function names are verbs (`build_polygon`, not `face`). A
  generic-sounding name belongs in a module that supplies the missing context (`vectors::subtract`,
  not bare `subtract`) and should be called through that qualified path, not a bare import.
- Verbs compose — small, single-purpose verbs that pipe together, not one verb growing a flag at a
  time:
  - Query verbs print results to stdout, one per line; summaries and counts go to stderr. Add
    `--json` only where a script needs structure.
  - Mutating verbs take their target set from stdin via `-` (never mixed with names as CLI args);
    empty stdin is a clean no-op.
  - Two stdin conventions exist — a name list vs. a content snippet — and verbs must not blur them.
  - A verb over a set just takes the set; no flag that merely restates "operate on this set."
  - Prefer one stateless `find` feeding other verbs over per-verb `--only-*` filters.
  - `find` (exact query over current state) and `search` (fuzzy/ranked discovery) stay separate
    verbs, never merged.
- YAGNI, not just for output formats — build only what's actually needed now; three similar lines
  beat a premature abstraction. When you consciously defer a generalization (a hardcoded special
  case that should eventually go through a more general mechanism), flag it with a `TODO` naming
  what's deferred, rather than building that mechanism speculatively or leaving the hardcoding
  unflagged.

## Keep it short and plain

Every doc, docstring, comment, and commit message — including this file — should be as short as
possible without losing meaning, in plain language.

- Write plainly: direct sentences, no ornate phrasing, no all-caps emphasis, no repetition for
  effect.
- Delete first: if removing a sentence, bullet, or example wouldn't change what a reader does,
  remove it. Add length only to explain, never to signal importance.
- Leave a doc shorter than you found it, unless your edit added meaning.
- Default to no code comment. Add one only to explain a genuinely non-obvious why (a race, an
  ordering requirement, a correctness subtlety) — never to restate what the code already shows.

## Documentation

- Keep user-facing docs current with the CLI: whenever a change alters behavior a user can observe,
  update the matching doc in the same change.
- Reverse-engineering evidence (engine/file-format facts) comes ONLY from this project's own
  binaries — disassembly or a live capture — never a third-party source with similar lineage,
  however plausible. A finding based on one isn't RE and must not be presented as one.
