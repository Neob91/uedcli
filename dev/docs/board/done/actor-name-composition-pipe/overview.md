+++
priority = "p?"
kind = "unknown"
summary = "Actor-name composition pipe — stdin `-` + `actor add` prints Names"
+++

# Actor-name composition pipe — stdin `-` + `actor add` prints Names

— BUILT 2026-07-18
(plan `plans/2026-07-18-actor-name-compose-pipe-plan.md`; spec
`specs/2026-07-18-actor-name-compose-pipe.md`; decisions 2026-07-18 14:03 UTC). `actor add`
prints allocated Names to stdout (after save) + count to stderr; `actor delete/rotate/prop
set|unset|get/show` read `-` = newline name list from stdin via `dispatch._resolve_target_names`
(sole source, empty → no-op exit 0, dedup on canonical name); multi-actor `prop set/unset` is
two-phase-atomic (cross-class), `prop get -` emits `<name>\t<key>=<value>`. Folded into
`architecture.md` (Command API). (Remnant closed 2026-07-18: `actor folder set --to … -` now
reads `-` from stdin via the same `_resolve_target_names` seam — shipped with the folders feature.)
