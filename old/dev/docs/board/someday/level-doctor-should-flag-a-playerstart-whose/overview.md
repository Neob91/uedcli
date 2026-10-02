+++
priority = "p1"
kind = "unknown"
summary = "`level doctor` should flag a PlayerStart whose collision cylinder overlaps solid geometry"
+++

# `level doctor` should flag a PlayerStart whose collision cylinder overlaps solid geometry

p1. Dogfood: materialized the castle, booted it in-game via `uplayctl session start
--map Test_Castle`, and the game hit a fatal `Critical Error: Failed to spawn player actor`
(`MatchViewportsToActors <- (Test_Castle) <- ClientInit <- LoadMap`). Root cause: the PlayerStart
sat at (0,-64,48) but the central Keep additive brush spans Y[-56,56], so the player collision
cylinder (r≈20, half-height≈44) poked ~12u into the keep's front wall → engine can't spawn → map
load aborts. Fixed by moving the PlayerStart to (0,-250,48) (clear courtyard) + Yaw=16384 facing
the keep; re-materialized and it booted + spawned fine. **This class of defect is deterministic and
cheaply detectable model-side:** `level doctor` already parses every brush AABB — add a check that
each `Engine.PlayerStart` (and other spawn points) has its default-pawn collision cylinder clear of
every CSG_Add brush (and inside the subtracted play space). Emit a named error ("PlayerStart_X at
(…) overlaps brush Keep_Y — player cannot spawn"). Would have caught this before a 5-minute editor
boot + game boot round-trip. Andrzej, 2026-07-12.
