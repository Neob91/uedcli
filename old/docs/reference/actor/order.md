# actor order

`actor order <names…|-> (--first | --last | --before NAME | --after NAME)` — reorder EXISTING
actors' CSG precedence (no geometry change).

```bash
uedcli actor order <names…|-> (--first | --last | --before NAME | --after NAME)
```

Re-mints `order_value`s to change CSG precedence without touching geometry (CSG order is the
`(order_value, name)` sort). `--first` makes an actor carve/add before everything else; `--last`
places it after everything else; `--before NAME`/`--after NAME` place it adjacent to an existing
actor. Exactly one of the four is required (mutually exclusive; exit 2 on none or more than one).

Takes one or more actor Names (case-insensitive), or the single token `-` to read a
newline-separated name list from stdin (e.g. `actor find … | actor order - --first`) — `-` is the
**sole** source and cannot be mixed with names on the command line. Empty stdin is a clean no-op
(exit 0). Resolution is **all-or-nothing**: an unknown name **exits 2** naming every miss; duplicate
names dedupe on the canonical actor first. Multiple actors move as a block, preserving their
relative CSG order (their current order among themselves is kept, only their position among the
other actors changes).

For `--before`/`--after`, `NAME` must already exist and must **not** be one of the actors being
moved — ordering relative to a member of the same moved set is undefined and **exits 2**
(`cannot order relative to <NAME> — it is in the moved set`); an unknown `NAME` also exits 2.
Reordering into a gap that has no room left to mint a new rank between two adjacent existing ranks
**exits 2** (`cannot reorder: …`) — an edge case of the rank-minting scheme, not something an
ordinary reorder hits.

`order` is **trunk-only**: it always rejects `--tree stash|prefab` (a stash/prefab has no CSG order
to reorder). `move`/`delete`/`rotate` accept `--tree stash|prefab`; `duplicate` is trunk-only too,
but for its own, separate reason (its always-minted batch label — see [`actor
duplicate`](duplicate.md)).

Prints the reordered names to stdout (feed `| verb -`) with a `reordered N actor(s)` count on
stderr.

See also: [`actor find`](find.md) ("Discover brushes by CSG type").
