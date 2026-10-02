+++
priority = "p2"
kind = "implement"
summary = "`brush snap` — round a brush's near-grid LOCAL vertices to a grid (T3D filter)"
+++

# `brush snap` — round a brush's near-grid LOCAL vertices to a grid (T3D filter)

Shipped: stateless `brush snap -|FILE --grid N --tolerance T` filter (`uedcli/snap.py` +
`cli/commands/brush/edit.py`). Rounds each local vertex component to a grid multiple when within
tolerance (round half toward +∞), per-axis, Decimal-exact; validates each brush; SET-in/SET-out,
all-or-nothing. The `level doctor` near-grid-slop detection was deferred to its own item.
