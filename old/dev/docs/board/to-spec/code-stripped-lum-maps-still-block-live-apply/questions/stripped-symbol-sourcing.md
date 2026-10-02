# Blocker B: can we source un-stripped `Engine.CameraPoint` / `DeusEx.DeusExDecoration.BeginPlay`?

## Context

`20_Lenz` and 5 retail cinematics reference `Engine.CameraPoint` and
`DeusEx.DeusExDecoration.BeginPlay` — symbols the committed code-stripped DeusEx substrate does not
carry in decompilable form, so the stubber fails loudly and the maps can't materialize.

The fix needs an un-stripped definition of exactly these symbols so a stub can be built (or a minimal
hand-authored stub of the right class shape that satisfies the editor load — materialize needs the
class to load and import, not to run, which may make a body-less stub enough; the spike confirms).

The decision is whether we are willing and able to source those definitions, and under what handling:
- Same copyright shape as the game code the stubber already decompiles per-user — so any sourced
  definition or generated stub stays **derived, per-user, never committed** (`direction/containers.md`).
- Is the un-stripped symbol source obtainable at all (a fuller `.u`, public engine headers, or a
  minimal reconstructed class), or is a hand-authored minimal stub the only route?

Recommendation: scope this to the *named* symbols only (the spike verifies the set is just these),
prefer a minimal load-satisfying stub over sourcing full bodies, and keep the fail-loud contract for
anything still unsourceable. Confirm willingness before planning.

## Answer

<!-- Empty = open. -->
