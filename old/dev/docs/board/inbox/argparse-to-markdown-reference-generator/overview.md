+++
priority = "p3"
kind = "implement"
summary = "generate docs/reference/ from argparse instead of hand-authoring it"
+++

# generate docs/reference/ from argparse instead of hand-authoring it

Deferred from the `usage.md` split
(`dev/docs/superpowers/specs/2026-08-30-usage-md-split-design.md`, "Non-goals"): `docs/reference/`
is now hand-authored, dry, per-command pages mirroring the CLI's own parser structure. A generator
that derives those pages from `uedcli/cli/parsers/*.py` (argparse) would remove the hand-sync risk
between a verb's flags/help and its doc page, at the cost of real, separable engineering: format
design, a generation script, and a CI drift-guard (same shape as the deferred
`bundle-the-user-facing-docs-into-the-wheel` item).

Scope, per the split spec: generation would only ever target `docs/reference/` (the mechanical
per-command layer) — `docs/usage/`'s workflow prose is inherently hand-authored and stays that way.
The split spec measured that generation timing doesn't change the token-economics win (the split
alone delivers the reduction), so this is a fast-follow, not a blocker, and was explicitly not
built as part of that spec.

A post-ship review of the hand-authored tree (2026-09-01) found the ~49 pages vary in shape — some
have runnable examples and an exit-status callout, most don't; no page tabulates its flags. A
generator would also fix this for free by imposing one template, rather than needing a separate
hand-retrofit pass.
