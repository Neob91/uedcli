# actor move

`actor move <names…|-> (--to X,Y,Z | --by DX,DY,DZ)` — translate a set of actors by a world delta,
or set one actor's `Location` to an absolute point.

```bash
uedcli actor move <names…|-> (--to X,Y,Z | --by DX,DY,DZ) [--tree KIND/NAME]
```

Takes one or more actor Names, or the single token `-` to read a newline-separated name list from
stdin (`-` is the sole source, not mixable with named args) — the same `names…|-` set contract as
`actor rotate` and `brush scale`. So a query pipes straight in:

```bash
uedcli actor find --folder castle.props | uedcli actor move - --by 0,0,-64   # drop the set 64uu
```

Requires **exactly one** of `--by` or `--to` (the parser rejects both together or neither, exit 2):

- **`--by DX,DY,DZ`** — a world delta added to **every** target's `Location`. Works for any count
  (negatives allowed — nudging a selection *down* `0,0,-64` is the common case). The delta adds onto
  each actor's **stored** `Location`; an actor with none deltas from the world origin `(0,0,0)`, not
  from its class default (contrast `actor rotate`, which resolves the class default for a missing
  `Location` when it needs a pivot).
- **`--to X,Y,Z`** — an absolute world target for **one** actor only. A resolved set of more than one
  actor **exits 2** (moving several to one point would stack them; use `--by` for a set). Empty stdin
  is the standard no-op (exit 0); a single name — including one piped, even piped twice — proceeds.

There is no `--pivot`: a move is a pure translation, the same delta on every actor, so there is
nothing to orbit about (unlike `rotate`/`scale`). Names resolve case-insensitively and are deduped on
their canonical form (a repeat is one actor — `--by` never double-moves it); an unknown Name **exits
2** naming it, and nothing is moved (all-or-nothing). `--tree KIND/NAME` retargets the edit onto a
named level/stash/prefab tree instead of the ambient `$UEDCLI_LEVEL` (default) — `move`, unlike
`order`, is not trunk-only.

Prints each moved actor's canonical Name to stdout, one per line, in piped order (feed `| verb -`),
and a `moved N actor(s)` summary to stderr.

See also: [`actor rotate`](rotate.md), [`brush scale`](../brush/core.md), [`actor duplicate`](duplicate.md).
