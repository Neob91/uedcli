+++
priority = "p3"
kind = "implement"
summary = "level doctor: detect near-grid vertex slop (a vertex just off a grid line) and advise `brush snap`."
+++

# level doctor: flag near-grid vertex slop

Split from `brush-snap-round-a-brush-s-vertices-to-a-nearby` (owner deferred it, 2026-08-02): ship the
`brush snap` filter first, detection separately. `brush snap` cleans near-grid float noise on demand;
`level doctor` could *detect* it — a vertex within a small band of a grid line but not on it — and
advise running `brush snap`, so an author finds the problem without knowing to look.

Open design (why it was deferred): doctor has no `--grid`, so it needs its own grid/band definition;
a severity; and care not to flood already-off-grid retail imports. Answer those against real use of
the filter before building.
