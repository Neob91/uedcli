+++
priority = "p2"
kind = "debug"
summary = "materialize mishandles a trunk actor named DefaultBrush (silent only under --no-verify)"
+++

# materialize mishandles a trunk actor named DefaultBrush

DONE (commit 25d1409). Removed the two `!= dbrush` exclusion filters in `native/unbuilt.py`, so a
trunk brush named `DefaultBrush` now collides with the reserved builder brush and raises `_reserve`'s
duplicate-name error (clean exit 2 via `apply.py`) instead of being dropped. Install-free regression
test `test_materialize_defaultbrush.py`.
