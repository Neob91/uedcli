+++
priority = "p3"
kind = "unknown"
summary = "committed uned/UED22/Engine.u vs substrate Engine.u disagree on Actor.Touching's type"
+++

# committed uned/UED22/Engine.u vs substrate Engine.u disagree on Actor.Touching's type

Found as an unprompted byproduct of the `ArrayProperty` RE for
`dev/docs/board/someday/gui-inspector-dynamic-arrayproperty-support/` (2026-09-23), not chased
further — flagging so it isn't lost, and so nothing later silently assumes the two `Engine.u`
copies in this repo are interchangeable.

`Engine.Actor.Touching`:
- **Committed reference** (`uned/UED22/Engine.u`, checked into this repo) — a dynamic
  `ArrayProperty` (unbounded).
- **Real game substrate** (`dev/games/substrate-deusex/System/Engine.u`) — a fixed
  `array_dim=4` STATIC array.

Different engine builds genuinely disagree on this property's declared type, not a decode bug (both
readings came from the same `uprops.own_class_properties` code path, run against two different real
`.u` files). Whether this matters depends on what else in the codebase assumes these two `Engine.u`
copies agree — not audited here.

## Next step, if picked up

Check whether any other `Engine.Actor` property differs between the two copies (not just
`Touching`) — this was found incidentally scanning for `ArrayProperty` specifically, not from a
full diff of the two schemas. If several properties differ, this may be a build/version mismatch
worth understanding rather than a one-off.
