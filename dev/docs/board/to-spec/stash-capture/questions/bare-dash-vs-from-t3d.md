# Add bare `stash capture -` for stdin T3D, replacing `--from-t3d -`?

## Context

Stdin capture already works as `stash capture --from-t3d -`. This item asks for the bare
`stash capture -` form (the `build → add -` convention). Two calls:

1. Is the bare `-` spelling wanted, or is `--from-t3d -` enough — close the item as already served?
2. If wanted: per `conventions.md` (no dual spelling), `-` becomes the only stdin spelling and
   `--from-t3d` drops its `-` value (files only). Confirm that removal, and confirm the shape
   `stash capture - [names…]` (leading `-` = stdin source, remaining positionals = subset filter;
   `-` mutually exclusive with `--from-t3d`/`--tree`).

Recommendation: adopt the bare `-`, drop `--from-t3d -`, keep the leading-`-`-plus-subset shape — it
matches `actor add -` and the pipe in the overview, and loses no capability. Empty stdin stays exit 2
(matching `actor add -`), unless you want a clean no-op instead.

## Answer

<!-- Empty = open. -->
