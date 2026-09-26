+++
priority = "p1"
kind = "debug"
summary = "csg carves misses a carve entirely interior to its victim's volume, dropping a fact raw gets right"
+++

# csg carves misses a carve entirely interior to its victim's volume

Found in the final whole-branch review of `actor-survey-and-relation` (Task 17's own per-task review
did not catch this — every Task 17 fixture happens to use a carve that breaks one of the victim's own
authored faces).

`removed_by` (`uedcli/actor_survey.py`) decides whether a Subtract carved an Add by re-solving the
neighborhood without the Subtract and comparing the ADD's OWN surviving face area across both solves.
That is the right check when the carve breaks one of the Add's own faces — but a Subtract wholly
INTERIOR to an Add's volume (never reaching any of the Add's own authored faces) removes real matter
without changing the Add's own surviving face area at all, so `gained == 0` and no `carves` fact is
reported.

Measured on the committed `an_oversized_corridor_past_its_room` fixture:

```
raw Room --carves--> Rock            # correct
csg  (nothing for Room/Rock, either direction)
csg Corridor --carves--> Rock        # fires — Corridor cuts Rock's outer face, so it's detected
Rock surviving 25149440.0 / authored 25165824.0
removed_by(Room, Rock) -> False
```

This inverts the two-tier design's own "csg is authoritative" contract: here the raw tier gets the
fact right and the csg tier drops it. It is not the same defect as
`crosses-fires-on-a-subtract-s-carve-victim` (that one is a false POSITIVE on `crosses`; this is a
false NEGATIVE on `carves`) or `authored-volume-poisoned-by-unbounded-plane` (that one is about
`authored_volume`'s own correctness on a degenerate case, not about which faces a check looks at).

A real fix needs an owner ruling on the comparison basis — likely a volume-based check (compare the
Add's own solid volume, or the Subtract's overlap with it, rather than only its face area) — since
switching the basis could interact with the counterfactual solve's existing cost profile and the
already-settled exact-duplicate-region rule (`spec.md:471-475`). Not fixed here per the owner's
standing "log issues, ship a minimal working version" instruction; `docs/reference/actor/survey.md`'s
`carves` row already discloses this limitation so the shipped docs do not overclaim.
