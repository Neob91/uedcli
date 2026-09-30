# `web/` refactor: scope and sequencing

## Context

Confirmed: `web/` is in scope for a refactor as part of this effort — TypeScript, not a Rust
rewrite. Not yet specified:

- **What's driving it?** No specific problems with `web/` have been named yet (unlike the Python
  side's YAGNI/DRY complaint, which came with concrete reasons). Worth a short pass naming what's
  actually wrong before scoping the work.
- **Where does it live during the migration?** `web/` moves into `old/` at PR #0 like everything
  else (per Repo restructure). Does the refactor happen in `old/web/` in place, or does `web/` move
  back out to the new root early (e.g. alongside or shortly after PR #0), separate from the
  Rust-porting timeline? Matters because "`old/` stays frozen" was scoped to the Python binary's
  *behavior* (no bug patches) — it's not yet decided whether that freeze extends to `web/`'s code
  too, or whether `web/` is exempt from it since it's not part of the strangler fallback.
- **Same review discipline?** Presumably yes (every PR reviewed), but not explicitly stated for
  `web/` work specifically.

## Answer

