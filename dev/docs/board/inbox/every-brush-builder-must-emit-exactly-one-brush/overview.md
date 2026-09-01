+++
priority = "p1"
kind = "implement"
summary = "Every brush builder MUST emit exactly one brush (spiral emits N+1)"
+++

# Every brush builder MUST emit exactly one brush (spiral emits N+1)

**Owner ruling (2026-08-24):** every `brush build <shape>` generator MUST output exactly ONE brush
actor. A single verb producing multiple brushes is not allowed.

Current offender: **`brush build spiral`** — its help says it "prints N+1 actors" (a central column
plus one wedge tread per step). Building a 12-step spiral emits 13 actors (`Stair0…`, column, …).

The `staircase` generator already proves one non-convex brush is enough for stepped geometry
("ONE non-convex brush", per its help), so a spiral staircase should likewise be a single
non-convex brush.

## Scope
- Audit all `brush build` shapes (cube, cylinder, cone, sheet, staircase, spiral, extrude, revolve):
  each must emit one brush. Only `spiral` is known to violate this today; confirm the rest.
- Reshape `spiral` to a single non-convex brush (column + treads as one brush), matching how
  `staircase` is authored.
- If any shape genuinely cannot be one brush, that's an owner decision — surface it, don't split.

## Why
Verbs compose one brush at a time; a generator that fans out to N actors breaks the mental model,
the naming (`Stair0…`), and downstream by-name selection. It also leaked into the MegaGrant demo,
which had to swap spiral → staircase to avoid showcasing the multi-brush behaviour.
