+++
priority = "p?"
kind = "unknown"
summary = "Water cluster — RESOLVED / triaged 2026-07-19 (live-verified)"
+++

# Water cluster — RESOLVED / triaged 2026-07-19 (live-verified)

WaterZone authoring needs NO
bespoke scaffold verb: `actor build Engine.ZoneInfo --prop bWaterZone=True | actor add -` (or the
placeable `DeusEx.WaterZone` class) round-trips the props into the trunk, schema-validated. The two
reported doctor false-positives: watertight-on-portal-sheet is ALREADY FIXED (2026-07-18;
`_brush_polyflags` OR's per-poly flags — verified zero findings on a real portal sheet); the
fallthrough-on-nonsolid warn has been REMOVED (the `doctor` `fallthrough` check was deleted) and
`brush build sheet --flag <name>` was added — both landed 2026-07-19. (Deferred follow-up: the same
`--flag` build-time passthrough on the OTHER `brush build` generators — cube/cylinder/… emit
multi-face solids where a per-face flag differs semantically from a single-face sheet, so it wants
its own decision.) The water-authoring recipe (water = a translucent NONSOLID zone-portal SHEET over a `bWaterZone`
  ZoneInfo; portals must be non-solid, not semisolid) folds into the level-design docs + AI-skills
  item below. (Content gap, not a tool gap: LUM_CoreTex ships no dedicated water texture — but the
  base `CoreTexWater` package is now reachable, see the base-texture RESOLVED note above.)
