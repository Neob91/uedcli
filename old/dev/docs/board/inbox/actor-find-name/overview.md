+++
priority = "p2"
kind = "unknown"
summary = "`actor find <NAME>` (bare positional) is rejected — must use `--name GLOB`"
+++

# `actor find <NAME>` (bare positional) is rejected — must use `--name GLOB`

The positional
slot is reserved solely for the `-` stdin token, so the natural `actor find Foo` errors ("find takes
no positional name; use --name"). Three independent hits (2 build agents + Andrzej). Consider accepting
a positional name-glob when the token isn't `-`, keeping `-` as the universe pipe — i.e. `actor find
Foo*` would mean `actor find --name Foo*`. **NOTE the premise changed 2026-07-26:** this used to say
"mirrors `actor show <glob>`", but `actor show` no longer globs — it is a pure name resolver, and the
owner's ruling is that patterns belong to `actor find` alone. So the argument for this item is no
longer symmetry with a sibling verb; it is that `find` is now the ONLY verb that globs, which makes a
bare positional there more defensible, not less. (Blind-build test + Andrzej, 2026-07-25; premise
corrected 2026-07-26.)
