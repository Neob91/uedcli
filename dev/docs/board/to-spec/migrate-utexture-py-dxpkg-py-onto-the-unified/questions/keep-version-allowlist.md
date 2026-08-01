# Keep dxpkg's (61,68,69) package-version allowlist after the migration?

## Context

`dxpkg._parse_header` refuses any package version outside `(61, 68, 69)` — "refusing to guess offsets
for an unverified version". The canonical core `upackage.load_package` has no such allowlist: it reads
any version whose table layout it understands (it only branches ver<64 vs >=64 for the name table).

Migrating `dxpkg` onto the core would drop the allowlist unless re-added as a thin post-load check on
`Package.version`.

- **Keep it** (as a `dxpkg`-side check): preserves today's "refuse unverified versions" behavior for
  the closure extractor. But `direction/packages.md` frames uedcli as a *generic* UE1 tool ("a decoder
  that needs a game's own code package … cannot read a lone `.utx` from an engine we have never
  seen"), and a hard version gate is the opposite instinct — it refuses an engine we haven't catalogued
  even when the layout parses fine.
- **Drop it:** the core reads what it can; a genuinely unreadable layout still fails via the integrity
  checks (bad magic, table overrun). More generic, but removes an explicit guard that has caught real
  truncation in testing.

Recommendation: drop the hard allowlist and rely on the core's structural integrity checks, consistent
with the generic-tool direction — unless you want the closure extractor to stay conservative about
unknown versions. Note this only affects `dxpkg`'s closure path; `utexture` never gated on version.

## Answer

<!-- Empty = open. -->
