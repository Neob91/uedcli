+++
priority = "p2"
kind = "unknown"
summary = "`level doctor` should flag an actor that is EMBEDDED IN world geometry"
+++

# `level doctor` should flag an actor that is EMBEDDED IN world geometry

A
world-colliding actor whose collision volume sinks into solid space is a real level-design bug —
the engine shoves it out, drops it through the floor, or leaves it blocking movement — and
nothing currently catches it. **Rule Andrzej gave: report when the overlap exceeds 2 uu OR 10% of
the actor's own size** (either, not both — so a small decoration is judged proportionally and a
large one absolutely). Scope is actors that actually collide with the world; a non-colliding
decoration or a light may sit inside a wall legitimately.
- **Open for the spec, do not guess:** which dimension "10% of its size" measures against
  (`CollisionRadius`, `CollisionHeight`, or the smaller of the two — they differ a lot for a tall
  thin pawn); whether the collision volume is taken as the engine's cylinder or the mesh bbox;
  and whether a resting-on-a-floor contact of a fraction of a uu needs an explicit tolerance so
  every placed decoration does not report.
- **Depends on solid-space classification**, which is why this is `[spec]` and not `[chore]`:
  deciding "is this point inside world solid" needs the native CSG core, and `level doctor` is
  otherwise pure per-actor/T3D compute. Worth settling whether the coarse core is accurate
  enough here, or whether this check has to wait on the `bspBrushCSG` port — and what the verb
  does when no core/package path is resolvable (exit 2 naming what is missing, per the
  `is_mover` precedent, rather than silently skipping the check).
(Andrzej, 2026-07-26.)
