# Should `list` show a per-value actor count, and if so how?

## Context

The overview asks whether each listed folder/label carries how many actors use it. Options:

- **A — pure value producer (recommended).** Distinct values only to stdout, one per line; a single
  total (`N folders in use`) to stderr. Keeps the pipe clean and the shape identical to
  `actor find`. A per-value count is still reachable ad hoc: `actor find --folder X | wc -l`.
- **B — opt-in `--count` TSV column.** Default stays pure; `--count` prints `count<TAB>value`
  (and `--json` becomes `{value: count}`). One extra flag, one extra output shape to keep documented.
- **C — count always on stdout.** Rejected up front: it pollutes the producer pipe (the exact
  anti-pattern `direction/conventions.md` calls out — the human summary belongs on stderr).

Recommendation: **A** now. Add `--count` (B) later only if a real need appears; don't gold-plate.

## Answer

<!-- Empty = open. -->
