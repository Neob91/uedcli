+++
priority = "p1"
kind = "implement"
summary = "`actor move` over a SET (`-`/stdin), `--by`-only for multi-actor"
+++

# `actor move` over a SET (`-`/stdin), `--by`-only for multi-actor

Spec written +
**cold-review gate PASSED** (2 reviewers, no blockers, all findings folded in):
[`dev/docs/specs/2026-07-25-actor-move-set.md`](../../../specs/2026-07-25-actor-move-set.md). Brings `move` to the
`actor rotate`/`brush scale` set contract (`names… | -`); `--by` any count, `--to` rejects >1 (exit 2),
dedupe, empty-stdin no-op, no `--pivot`. Decisions: `decisions.md` 2026-07-25 00:43 UTC. Breaking:
positional `name`→`names` + `args["name"]`→`args["names"]` save shape (unreleased, no shim) — the spec
§5 lists the existing tests to migrate/remove (incl. the "move does NOT accept `-`" test). Small, well-
scoped; next action is a plan (or build directly given the sibling-mirror is so close).
