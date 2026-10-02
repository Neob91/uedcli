# level status

`level status [--tree KIND/NAME] [--json]` — thin read-only dashboard for the current level (or a
`--tree` box): actor counts, duplicate `order_value`s, git state. `--json` emits a `{kind, name,
actors, duplicate_order_values, git, texture_packages}` object (`{"selected": null}` when no level
is set).

See also: [`level create`](create.md), [`level doctor`](doctor.md).
