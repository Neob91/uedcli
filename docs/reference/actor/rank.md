# actor rank

`actor rank <names…|-> [--json]` — print each actor's 1-based position in the level's CSG
evaluation order.

CSG evaluation order decides which brush carves/adds first: rank 1 is evaluated first, higher
ranks later. `actor order` is the verb that *changes* this order; `actor rank` only reads it.

Prints one line per actor **in argument order** (not CSG order — an actor named later on the
command line still prints later, even if its rank is numerically lower):

```
Name<TAB>RANK
```

`RANK` is a bare base-10 integer. Example, a level whose CSG order is `Wall, Room, Door`:

```bash
$ uedcli actor rank Door Wall
Door	3
Wall	1
```

A human summary (count ranked, level's total actor count) goes to stderr, never stdout. `--json`
emits a JSON object mapping each canonical actor Name to its integer rank instead
(`{"Door": 3, "Wall": 1}` for the example above) — the summary still goes to stderr.

Takes one or more actor Names (case-insensitive), or the single token `-` to read a
newline-separated name list from stdin (e.g. `actor find --folder castle | actor rank -`) — `-` is
the **sole** source and cannot be mixed with names on the command line. Empty stdin is a clean
no-op (exit 0). Names dedupe on their canonical form, order-preserving (first occurrence wins).

Resolution is **all-or-nothing**: an unknown name exits 2 naming every miss at once
(`Actors not found: <names>`), with no partial output.

Works on any T3D tree — a level, a stash, or a prefab (`--tree stash|prefab`) — since all three
carry a CSG order.

See also: [`actor order`](order.md) (changes the order this verb reads), [`actor find`](find.md)
(the usual way to build the `names` set to pipe in).
