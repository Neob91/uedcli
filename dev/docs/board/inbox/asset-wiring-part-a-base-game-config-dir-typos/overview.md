+++
priority = "p3"
kind = "chore"
summary = "Asset-wiring Part A: base-game config dir typos are silently skipped (diagnosability cost)"
+++

# Asset-wiring Part A: base-game config dir typos are silently skipped (diagnosability cost)

p3. `config.resolve_dirs` skips a NON-existent dir even under `require_absolute=True` (the
games config) — the intended offline-safety behavior (decisions.md 2026-07-14 03:30: model verbs
must run without the base game installed). Cost: a typo in `~/.uedcli/config.toml`'s game `paths`
degrades to a generic downstream error (empty schema code-path → `SchemaError`; incomplete load
set → materialize "missing package"), never "configured dir X does not exist". Both cold reviewers
flagged it (2026-07-14). Consider an OPT-IN existence check / `uedcli doctor`-style config lint for
the games config, where existence is not offline-optional. Not a bug — a UX follow-up.
