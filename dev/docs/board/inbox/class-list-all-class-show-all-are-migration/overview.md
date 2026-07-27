+++
priority = "p3"
kind = "chore"
summary = "`class list --all` / `class show --all` are migration-error shims, which `conventions.md` forbids"
+++

# `class list --all` / `class show --all` are migration-error shims, which `conventions.md` forbids

`cli.py:1418` and `:1443` define them as `argparse.SUPPRESS`'d flags whose
only job is to `parser.error()` with a pointer to `--depth all` — the exact "a flag defined only to
`parser.error(\"X was renamed to Y\")`" pattern the no-back-compat-cruft rule names. Pre-existing, not
caused by the catalog work, but the catalog build is what next touches both verbs, so delete them then.
Surfaced by a gate reviewer 2026-07-26 as adjacent-but-real. *(2026-07-26.)*
