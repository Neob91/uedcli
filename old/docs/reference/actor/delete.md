# actor delete

`actor delete <names…|->` — delete one or more actors, restoring swept neighbours.

```bash
uedcli actor delete <names…|-> [--tree KIND/NAME]
```

Takes one or more actor Names (case-insensitive), or the single token `-` to read a
newline-separated name list from stdin (e.g. `actor find … | actor delete -`) — `-` is the **sole**
source and cannot be mixed with names on the command line (exit 2). Empty stdin is a clean no-op
(exit 0) rather than an error, since a filter that matched nothing isn't a mistake.

Resolution is **all-or-nothing**: every name is resolved to its canonical stored form first, and
any unknown name **exits 2** naming every miss at once (`Actors not found: A, B`) — nothing is
deleted. Duplicate names (including case variants of the same actor) are deduped before the delete
loop, so piping a name twice deletes it once, not twice. `--tree KIND/NAME` retargets the edit onto
a named level/stash/prefab tree instead of the ambient `$UEDCLI_LEVEL` (default) — `delete`, unlike
`order`, is not trunk-only.

Deleting drops each actor and removes it from the level's CSG order list; deleting a subtracting
brush restores whatever geometry it had swept away once the level is rebuilt, the same as deleting
it in the editor.

For `delete` the stdout is the removed names — a log, since they no longer exist to pipe into an
edit — with a `deleted N actor(s)` count on stderr.

See also: [`actor find`](find.md).
