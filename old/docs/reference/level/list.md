# level list

`level list [--json]` — list the project's levels (trunk dirs under `<maps>`), one name per line to
stdout (pipe-friendly); a count + the active `$UEDCLI_LEVEL` go to stderr. `--json` emits
`[{name, active}, …]`.

See also: [`level create`](create.md), [`level status`](status.md).
