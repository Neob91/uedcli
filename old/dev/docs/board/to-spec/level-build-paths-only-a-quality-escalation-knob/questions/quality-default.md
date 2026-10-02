# `level materialize --quality` default — `lame` or `good`?

## Context

Today materialize always runs `MAP REBUILD` == `BSP REBUILD GOOD` (coplanar-merge pass). Adding
`--quality {lame,good,optimal}` forces a default choice.

- `lame` (overview's proposal): fastest, skips coplanar detection — good for the inner iteration
  loop, worse BSP for a ship build. Changes today's behavior.
- `good` (current): keeps today's behavior; a bit slower.

BSP quality does not affect post-verify (the compare is over authored brush polys + typed props, not
the built BSP Model), so either default is verify-safe. The trade is purely speed vs BSP quality on
the default (unqualified) build. Recommend confirming the overview's `lame`, since `optimal`/`good`
stay one flag away for a final pass — but this changes the default a `level materialize` produces.

## Answer

<!-- Empty = open. -->
