+++
priority = "p2"
kind = "implement"
summary = "level reimport — reimport a hand-edited .dx/.unr into an existing trunk — BUILT"
+++

# level reimport — reimport a hand-edited .dx/.unr into an existing trunk — BUILT

(2026-08-29.) `level reimport MAPFILE --tree level/NAME [--force]` folds a hand-edited compiled map
back into the trunk that produced it, matching actors by name — unlike `level import --overwrite`'s
wholesale replace, unrelated actors, folders/labels and CSG order stay untouched. Brush
`order_value` is recomputed with minimal churn (longest-increasing-subsequence diff against the
current rank); a 20% modified+deleted blast-radius guard requires `--force` to override; every
added actor gets a shared `reimport-<hex>` label for later review.

A build-time finding (matched-and-changed actors were losing their folder/labels sidecar — see
`level-reimport-drops-folder-labels-sidecar-on-a`) was confirmed and fixed before merge.

Design: `docs/superpowers/specs/2026-08-29-level-reimport-design.md` (`spec.md` here mirrors it).
Plan: `plan.md`. User docs: `docs/usage.md` "`level reimport`".
