## The refactor

uedcli is being rewritten from Python into Rust, from an empty root, with the old codebase moved
under `old/`. @dev/epics/refactor.md has the plan — read it before any question about scope,
sequencing, or why `old/` is shaped the way it is.

## Working with the owner

Every decision that is the owner's to make goes through Claude Code's `AskUserQuestion` widget, not
prose in the chat, where it gets skimmed, half-answered, or scrolls away. This covers design forks,
sequencing calls, and anything a review escalates.

Never overrule the owner silently, and never downgrade a real question to avoid asking it. If a
rule of theirs points one way and you judge otherwise, that is a question for the widget, not a
deviation recorded in a commit message and moved past.

### Speccing: finer details go through the owner too

Not just top-level design forks. While turning an approved design into an exact spec — config key
names, on-disk layouts, field names, API shapes — surface these as questions too, rather than
silently deciding them or deferring them to later.

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
  ruled, including its known costs, and pin those costs in a test or doc so they are recorded
  rather than quietly re-fixed later.

## Workflow

Always ask where to implement a change: a feature branch on a git worktree, the current checkout
(usually master), or somewhere else.

## Code & CLI conventions

- No back-compat cruft — uedcli is unreleased. No external users, no scripts in the wild, so nothing
  is kept for backward compatibility. When you remove or rename a flag, verb, option value, output
  format, or code path, delete it outright in the change that adds the replacement. Never a
  deprecated alias, a no-op flag, a migration-error shim, dual-format support, or an "old way"
  branch. (This is about the CLI's own external surface — it doesn't apply to the rewrite's
  subprocess-strangler fallback to `old/`, which is migration scaffolding, not back-compat; see
  @dev/epics/refactor.md.)
- No fallbacks, and no silent half-answers, for any command or script, unless the owner explicitly
  asked for or agreed to one. A command that can't fully satisfy a request exits 2, naming the
  offending value — never a partial result plus a warning that scrolls away, never a substituted
  default for something it couldn't resolve. Never switch behavior on the environment either: a verb
  does the same thing on every host — same code path, same output — never branching on CPU arch, OS,
  an env var, or a tool's presence/absence to pick a different implementation. When an approach is
  specified (e.g. a dockerized setup), it is the only path: a missing host tool is a broken host to
  fix, surfaced as a clear error, never a reason to silently keep a second code path.
- Never let a panic reach the user. A bad input exits non-zero with a clear message naming the
  offending value. Cover each path with a regression test.
- Every command, flag, and argument needs a real help string that says what it does, so `--help` is
  self-explanatory rather than a restatement of the flag's own name.
- No abbreviations in names — spell words out (`texture`, not `tex`; `length`, not `vlen`;
  `format`, not `fmt`). A short loop counter (`i`, `n`) or a generic type parameter (`T`) is fine.
- Function names are verbs — what it does, not just the noun it returns (`build_polygon`, not
  `face`; `compute_centroid`, not `centroid`).
- Verbs compose — the core CLI philosophy. Small, single-purpose verbs that pipe together, not big
  verbs grown a bespoke flag at a time:
  - Producer/query verbs print their result to stdout, one item per line; human summaries and counts
    go to stderr; add `--json` where a script needs structure rather than lines.
  - Mutating/consuming verbs read their target set from stdin via `-`, the sole names source
    (mutually exclusive with names as CLI args); empty stdin is a clean no-op (exit 0), not an error.
  - Two stdin conventions, disambiguated by verb: a name list vs. a structured-content snippet.
    Keep them distinct.
  - A verb over a set takes the set, and that is the operation — no flag that merely restates
    "operate on this set."
  - Prefer one stateless `find`/query verb feeding the others over per-verb `--only-*` filter flags.
  - `find` vs `search`, never merged: `find` is a deterministic query over concrete state, producing
    an exact name/selector set to pipe onward; `search` is ranked/fuzzy discovery over a catalog or
    corpus.
- YAGNI, generally — not just output formats. Build only what the actual use case in front of you
  needs; no speculative flags, modes, abstractions, or generality for a future that hasn't arrived.
  Three similar lines beat a premature abstraction.

## Keep it short and plain

Each document, docstring, code comment, commit message — including this file — should be as short
as possible without losing meaning, written in plain language.

- Write plainly: direct, matter-of-fact sentences. Avoid ornate or dramatic phrasing, all-caps
  emphasis, slogan headings, and repetition for effect.
- Delete first. If text can be removed and a reader would still act the same way, remove it —
  sentence, bullet, heading, or example.
- Add length only to explain something a reader needs, not to signal importance or look thorough.
- Cut padding, not explanation. Padding is restatement, hedging, and ceremony; explanation is the
  mechanism.
- Leave a doc you edit shorter than you found it, unless the edit added meaning.

## Documentation

- Write every doc for a reader with no familiarity with the implementation. Define terms before
  using them, spell out the mechanism, and do not lean on context the reader lacks. An explanation
  that only makes sense if you already know how it works is a bug — rewrite it.
- Keep user-facing docs current with the CLI: whenever a change alters behavior a user can observe,
  update the matching doc in the same change.
- Reverse-engineering evidence (engine/file-format facts) comes ONLY from this project's own
  binaries (disassembly, or a live capture against them running) — never a third-party source
  claiming similar lineage, however plausible. A finding built on one is not RE and must not be
  presented as one, at any confidence tier.
