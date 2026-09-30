# Where does the `web/` refactor happen relative to the `old/` move?

## Context

`web/` moves into `old/` at PR #0 like everything else (per "Repo restructure"), and `web/`'s code
is now confirmed in scope for a refactor (TypeScript, not Rust — rationale: it's built against the
current, being-replaced backend architecture, and was vibe-coded same as the rest).

Not yet decided: does that refactor happen in `old/web/` in place, or does `web/` move back out to
the new root early (e.g. alongside or shortly after PR #0), on its own timeline separate from the
Rust verb-by-verb porting?

Matters because "`old/` stays frozen" was scoped to the Python binary's *behavior* (no bug patches,
so it stays a trustworthy differential-testing oracle) — it's not yet decided whether that freeze
extends to `web/`'s code too, or whether `web/` is exempt since it isn't part of the strangler
fallback and doesn't affect `old/`'s binary at all.

## Answer

