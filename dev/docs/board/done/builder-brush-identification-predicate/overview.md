+++
priority = "p?"
kind = "unknown"
summary = "Builder-brush identification predicate — CONFIRMED ROBUST"
+++

# Builder-brush identification predicate — CONFIRMED ROBUST

(2026-06-23, Spike 1 in
`spikes/2026-06-23-capability-gaps-round2.md`). Editor always assigns inner model `Model<N>` +
explicit `CsgOper` to authored brushes; uedcli uses `Model_{actorname}`; inner name `Brush` is a
singleton reserved for the live builder brush, never duplicated. No false positive possible.
Documented; no code change needed.
