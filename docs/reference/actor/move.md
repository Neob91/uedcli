# actor move

`actor move <name> (--to X,Y,Z | --by DX,DY,DZ)` — set or shift one actor's `Location`.

```bash
uedcli actor move <name> (--to X,Y,Z | --by DX,DY,DZ) [--tree KIND/NAME]
```

Requires **exactly one** of `--to X,Y,Z` (an absolute world target) or `--by DX,DY,DZ` (a delta
added to the actor's current `Location`); the parser rejects both together or neither (exit 2).
`--by` adds onto the actor's **stored** `Location` — an actor with none deltas from the world
origin `(0,0,0)`, not from its class default (contrast `actor rotate`, which resolves the class
default for a missing `Location` when it needs a pivot).

Unlike its siblings (`duplicate`, `rotate`, `delete`, `order`), `move` takes a **single** actor
Name — there is no `names…|-` batch form or stdin pipe; to move several actors, loop the shell.
Case-insensitive; an unknown Name **exits 2** naming it (`Actor not found: …`). `--tree KIND/NAME`
retargets the edit onto a named level/stash/prefab tree instead of the ambient `$UEDCLI_LEVEL`
(default) — `move`, unlike `order`, is not trunk-only.

Prints the moved actor's canonical Name to stdout (feed `| verb -`) and a `moved <name>` summary to
stderr.

See also: [`actor rotate`](rotate.md), [`actor duplicate`](duplicate.md).
