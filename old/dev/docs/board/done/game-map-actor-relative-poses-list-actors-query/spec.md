# `--game --map` actor-relative poses + `--sample` (non-PlayerStart coverage)

**Status:** BUILT + live-verified 2026-07-17 (40 non-PlayerStart shots delivered via the CLI). Extends the one-exec `--game` tier so SHOT poses can anchor to REAL in-map actors
(resolved by the running game), and adds a `--sample` convenience to auto-frame N of a class. Motive
(Andrzej): deliver screenshots of NON-PlayerStart locations THROUGH the CLI — today `--map` needs
literal `at:X,Y,Z` and there's no way to discover in-map coords, so bulk non-spawn shots aren't
possible without driving the link by hand.

## Decision (Andrzej 2026-07-17): generalize `@Actor` to `--map`
Currently `look:@Actor`/`orbit:@Actor` (and any actor ref) are REJECTED with `--map` because they
resolve against the trunk (`_resolve_all` → `actor_aim_point(level)`). New: with `--map`, actor refs
resolve against the **running game** (which knows every actor's position). And `at:` gains an
`@Actor` form (eye AT an actor). So on a retail map you can write `at:@PathNode37;rot:-8,90`,
`look:@JCDenton`, `orbit:@SomeMover;radius:120;azimuth:45`, and `at:@PlayerStart` (the old gap).

**Sampling is a QUERY, never in preview (Andrzej).** Preview never auto-samples-and-shoots; it takes
explicit poses only (incl. `@Actor`). A separate **query mode** `--list-actors CLASS [--sample N]`
lists (or evenly samples N of) a map's actors → prints `Name x y z`, exits WITHOUT shooting. You then
COMPOSE those `@Name` refs into preview shots. (DX auto-names nav markers `PathNode0`, `PathNode1`, …
so they're also referable by index directly.)

## Pieces
1. **uscript link verb `ListActors <Package.Class>`** — `AllActors(class)` → one `Actor <Name> <x>
   <y> <z>` line per actor, then `OK ListActors`. Cheap, read-only, works under the freeze
   (ReceivedLine runs on the unfrozen net poll — see the bplayersonly-freezes-timers finding).
2. **`preview_shots.py`: `at:` accepts `@Name`** (like `look:`). `Shot.at` becomes `tuple|str`. Pure
   parse; no engine dep. Bake `preview_shots.py` into the image so the batch can resolve+pose.
3. **`preview_batch.py` resolves actor refs against the game (for `--map`):** the req carries either
   fully-resolved `[x,y,z,pitchUU,yawUU]` shots (absolute, resolved host-side as today) OR an
   `unresolved` list of parsed Shot dicts. When present, the batch resolves each `@ref` via a
   **per-name `GetActorLocation` round-trip (cached)** — no class hint needed on the shot — then poses
   via the shared `preview_shots.resolve_pose` (actor-lookup hits the cache) + the ±89.9° pitch clamp.
   (`ListActors` is used only by the query mode, §4.) **An unresolved `@Actor` FAILS LOUD**: the batch
   emits `{ok:false, err:"actor not found …"}` and aborts (returns nonzero); the host surfaces that err
   and does NOT reboot-retry (a bad name won't fix on reboot). So over-specify with care — use
   `--list-actors` to get valid names first. (Chosen over graceful-skip: a typo should error, not
   silently drop shots and misalign the batch.)

4. **Query mode `level preview --game --map X --list-actors CLASS [--sample N]`** — prints one
   `Name x y z` per actor (or N evenly-indexed if `--sample N`), then exits. NO screenshots, no
   `--out-dir` required. This is a discovery verb whose output composes into preview `@Name` shots;
   it is where "sampling" lives (never in the shooting path).

## Where resolution happens
- **Trunk `--game`** (materialized level): `@Actor` resolves HOST-side as today (`actor_aim_point`),
  because the host holds the trunk. Unchanged.
- **`--map --game`** with any `@Actor` OR `--sample`: resolution moves to the BATCH (only the game
  knows retail-map actor positions), keeping the ONE `docker exec` contract. Absolute `--map` shots
  still resolve host-side.

## Non-goals
Trunk `--sample` (native tier); mesh/collision-aware framing (a node facing a wall still can); binary
`.dx` parsing (the game is the source of truth for positions).

## Tests / verify
Offline: `ListActors` parse + the batch's index/resolution + `--sample` shot generation (fake link
listing actors); `at:@Name` parse. Live: `--map 08_NYC_Bar.dx --sample Engine.PathNode --count N`
yields N distinct in-bounds frames; a hand-aimed `at:@PathNodeX;rot:...` lands where expected.
Deliverable: 40 non-PlayerStart shots across OG maps via `--sample`.
