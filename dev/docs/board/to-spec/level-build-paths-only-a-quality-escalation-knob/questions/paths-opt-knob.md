# Path-optimization level — expose a knob, or always use the default?

## Context

`PATHS BUILD` takes an optimization level: `LOWOPT` (0) / default (1) / `HIGHOPT` (2)
(`commands.md:295`). Options for exposing it:

- Always use the default (1) — simplest, no new flag; revisit if a real need appears.
- A separate `--paths-opt {low,default,high}` — parallel to `--quality`, orthogonal axis.
- Fold into `--quality` (lame→LOWOPT, optimal→HIGHOPT) — fewer flags, but conflates BSP quality with
  path optimization, two unrelated build axes.

Recommend the default-only start (no flag) unless the owner wants path opt tunable now; if tunable, a
separate `--paths-opt` (keep the two axes distinct — do not fold into `--quality`).

## Answer

<!-- Empty = open. -->
