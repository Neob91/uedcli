# actor order

`actor order <names…|-> (--first | --last | --before NAME | --after NAME)` — reorder EXISTING
actors' CSG precedence (no geometry change).

Re-mints `order_value`s to change CSG precedence without touching geometry (CSG order is the
`(order_value, name)` sort). `--first` makes an actor carve/add before everything else. Multiple
actors move as a block preserving their relative order.

See also: [`actor find`](find.md) ("Discover brushes by CSG type").
