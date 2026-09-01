+++
priority = "p3"
kind = "chore"
summary = "Batch: 5 lowest-effort inbox chore/debug fixes, bundled for one work session"
depends-on = ["delete-the-ephemeral-spec-specs-2026-07-18", "brush-clip-prints-nothing-on-success", "board-readme-md-still-says-every-issue-gets-a", "native-csg-golden-py-362-calls-ensure-editor", "a-doubly-signed-poly-index"]
+++

# Batch: 5 lowest-effort inbox chore/debug fixes

Five small, independent, already-scoped inbox items bundled into one PR so they land together
instead of five near-empty diffs. See `spec.md` for the per-item fix. Each source item stays in
`inbox/` until this batch lands, then moves to `done/` individually (they are independent fixes,
not one feature — no shared code path).
