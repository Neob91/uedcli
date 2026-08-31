# brush vertex

list / move

`brush vertex list <name> [--json]` — welded brush corners: world coord + the polys sharing each.

**`brush vertex move`** moves one or more welded corners selected by their current world coordinate
(`--at`, repeatable). `--to` needs exactly one `--at`; `--by` applies a delta to every `--at` corner.
`brush vertex move` is **rotation-aware** — a world coord is mapped into the brush's local frame, so
it edits a rotated brush correctly and preserves `Rotation` (as does [`brush clip`](core.md)).

See also: [`brush poly`](poly.md), [`actor bbox`](../actor/bbox.md).
