+++
priority = "p3"
kind = "implement"
summary = "A dangling configured `paths` dir should raise ConfigError at `config.composed_search_files`, tool-wide — not swallow the OSError."
+++

# Dangling configured paths dir should error (tool-wide)

Split from `materialize-should-fail-warn-loudly-instead` (2026-08-02). `config.composed_search_files`
(`config.py:463`) swallows `OSError` per-dir, so a mistyped `paths` config entry silently resolves to
nothing. That surfaces in materialize as a 0-package composed path (handled there as an advisory), but
the typo is a config error that every path-consuming verb should catch at its source.

Proposal: make a configured dir that does not exist a `ConfigError` naming the offending path, raised
where the search dirs are composed, so the typo fails loudly once for every verb rather than
degrading silently. Scope the "does not exist" vs "exists but empty" distinction.
