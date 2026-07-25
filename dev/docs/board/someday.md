# Someday (parked nice-to-have)

The **parking lane** for ambitious / low-urgency work. Items here are deliberately
**deferred** until the higher-priority pipeline is polished — they are **NOT surfaced in
normal triage** (they are not a stage, and carry no `to-` prefix). This is where something
lands when it's a genuine "nice to have / someday" rather than "route it to its next action
now". See [`README.md`](README.md).

An item leaves this lane only when it's actively **picked up**: pull it back into
[`inbox.md`](inbox.md) (or straight to the queue for its next action) and triage it forward
from there. Until then it stays parked here so the working queues stay scannable.

Tags (`[spec]`/`[implement]`/`[chore]`/`[debug]`) and `pN` priority ride each line as
elsewhere; priority here is relative *within* the parked set, not a claim on the pipeline.

---

## Backlog — deferred (someday)

### Deferred from the stash/prefab v1

- [ ] `p3` `[implement]` **`apply --anchor NAME`** — place by a chosen actor's pivot; v1 is bbox-min only.
- [ ] `p3` `[implement]` **`apply --csg first|last`** — control CSG insert position; v1 appends at end.
- [ ] `p3` `[implement]` **Strict autoload mode (`--require-packages`)** — fail apply on a missing texture/class package instead of warn-and-continue.
- [ ] `p3` `[implement]` **Unify `stash apply` + `prefab apply`** into one resolver; v1 keeps them separate (shared `_place_actors`).
- [ ] `p3` `[implement]` **uedctl config file** — persist settings (e.g. the prefab dir) without env/flag; v1 is env + flag only.
- [ ] `p3` `[implement]` **Stash/prefab lineage via a real git merge edge** — record a promoted prefab's source commit/branch as a second parent. *(Reframed 2026-07-18: "source session" → source commit; sessions removed by the git-native migration.)*
- [ ] `p3` `[implement]` **True 3D depth sort for composite preview** — correct inter-brush occlusion; v1 reuses the facing-based 2D painter order.
- [ ] `p3` `[implement]` **`preview` of non-brush point actors** — render lights/movers (radii/icons); would make `actor preview` the honest name.
- [ ] `p3` `[chore]` **Bare `stash <names…>` capture** — drop the explicit `capture` sub-verb; v1 requires `stash capture …`.

### Other deferred

- [ ] `[implement]` **Level validation: BSP-error/leak surfacing on genuinely broken geometry.**
  `LSTAT LEVEL` ✅, `MAP REBUILD` warnings ✅ confirmed log-readable (2026-06-23). REMAINING: probe
  a *genuinely broken* level (BSP leak, sealed-room failure), confirm `MAP REBUILD` warnings
  identify it, then classify warnings into actionable feedback for the autonomous loop.

- [ ] `[implement]` **Camera rotation READ (`camera get-rotation`-style verb).** SET is done
  (`level preview --rotate`). This is the remaining piece: report the live camera's current rotation
  without the caller already knowing it. Known avenue: parse the camera `Rotation` out of a `MAP
  SAVE`'d binary `.dx` (verified parser: `dev/docs/spikes/camera-rotation/parse_dx_camera.py`). NOTE: `JUMPTO
  X,Y,Z` centers viewports on a coordinate — a direct camera-position verb is cheap to retest.

- [ ] `p3` `[implement]` **`install-deusex-assets.sh --symlink` flag.** Spike Q20 (2026-06-23):
  Docker follows host-side symlinks for bind mounts; `pathlib.Path` follows symlinks. Add a
  `--symlink` flag that creates `DeusExAssets` as a symlink to the game install root instead of
  copying ~1.5 GB. **Verified 2026-07-19:** the script is still copy-only (the flag is UNBUILT); a
  hand-made `uned/DeusExAssets → DX` symlink already exists for the editor/game container bind-mount;
  and the host-native CLI reads assets straight from the real install via config `paths` (no copy at
  all) — so this is **moot for the CLI**, relevant only to the Docker editor/game container mount.
  (Merged the duplicate `[spec]` inbox entry into this one.)

- [ ] `p3` `[implement]` **`actor rotate --to` (absolute base rotation).** `actor rotate` is
  `--by`-only; `mover key rotate --to` introduced absolute keyframe rotation. A symmetric
  `actor rotate --to` would let `mover key rotate 0`'s redirect point at an absolute base verb (it
  currently points at `actor rotate --by` / a manual delta). Deferred from mover support
  (decisions.md 2026-06-25, Decision 10).

- [ ] `p3` `[implement]` **`mover key set` (combined absolute reposition+reorient).** Covered today
  by `mover key move --to` + `mover key rotate --to`. Deferred (decisions.md 2026-06-25, Decision 5).

- [ ] `p3` `[implement]` **Confirm `OldRot` is editor-computed and strip it.** `normalize.COMPUTED_PROPS`
  strips `BasePos`/`BaseRot`/`OldLocation` but NOT `OldRot` (not spike-confirmed). The mover
  integration test (`test_mover_integration.py`) checks whether a re-exported mover carries `OldRot`;
  if it does, add it to `COMPUTED_PROPS` (decisions.md 2026-06-25, Task 3 note).

## Deferred `level doctor` coverage

Ambitious `level doctor` checks parked until the core authoring/build loop is polished (deferred
from `inbox.md`, 2026-07-19).

- `[spec]` **`level doctor` should flag a PlayerStart whose collision cylinder overlaps solid
  geometry.** p1. Dogfood: materialized the castle, booted it in-game via `uplayctl session start
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

- `[implement]` **`level doctor` should WARN when a level has no `LevelInfo` (materialize will fail),
  and materialize's error should name that cause.** p2. `level create` now bakes an `Engine.LevelInfo`
  (fixes the common/new-level case), but a PRE-EXISTING trunk without one still fails materialize
  opaquely (`MAP NEW`'s default LevelInfo survives → re-export carries an actor the trunk lacks →
  mismatch). A doctor warn + a named materialize error close the gap for older levels.

- `[spec]` **Ghost playtester: offline reachability / walkability check (`level doctor --reach`).**
  Simulate a walking pawn over the built BSP (collision radius + step height + gravity, flood-fill from
  PlayerStart) and report: rooms unreachable on foot, doorways too narrow for the collision cylinder,
  steps too tall, drops the player can't climb back out of, kill-pits. The tracked PlayerStart-overlap
  check catches "can't spawn"; nothing catches "spawns fine but can't get into the keep" — today that
  costs a full materialize + game boot + manual walk. Builds on `linecheck.rs`/the collision-topology
  work (spike §60). (AI brainstorm 2026-07-16.)

- **[implement] p3 No offline ZONE / PORTAL / PATH verification — builds are "author-complete but
  verify-blind".** `doctor` has zero zone awareness: it can't confirm a portal actually seals two
  regions into separate zones, that the portal covers the opening, that a leak didn't fuse the rooms
  into zone 0, or that PathNodes are reachable. All resolve at build time only. An offline
  zone/portal/reachability pass would close the biggest confidence gap for multi-room work. (Agent B.)

## Brainstorm features (deferred, 2026-07-16 creative session)

Feature ideas from the "uedctl:creative" capture, triaged 2026-07-19: **all parked here**
(parametric prefabs **dropped entirely**; semantic texturing **sequenced after** the
texture-catalog redesign). Pulled back to `inbox.md` when actively picked up.

### Capabilities unlocked by the native Rust core

- `[spec]` **Offline spatial queries: `query los A B` / raycast.** The native `linecheck.rs` BSP ray
  test (built for the light bake) can answer line-of-sight and hit-point questions with no editor and
  no game: "can the guard at X see the door at Y", "what surface does this ray hit first". A stateless
  query verb (actor-to-actor, point-to-point, `--from-actor --direction`) that prints hit/clear + the
  hit surface — composes with `actor find`. Gameplay sight-line design (patrols, snipers, camera cones)
  becomes checkable text. (AI brainstorm 2026-07-16.)

- `[spec]` **Lighting doctor: per-surface exposure report from the native bake.** Run the N-4 bake
  offline and report numbers instead of vibes: surfaces with ZERO light contribution (pitch black),
  surfaces where many lights stack (the `LE_NonIncidence` washout lesson, 2026-07-13), lights that
  contribute to nothing (dead weight), per-room brightness histogram; optionally a top-down heatmap
  image. Would have caught both castle lighting mistakes without booting the game. Gated on the N-4
  lit-render fix only for *verifying* in-game — the bake itself already runs. (AI brainstorm 2026-07-16.)

- `[implement]` **Engine-budget lint: counts vs UE1 limits.** After a native build (or parsing any
  `.dx`), report node/surf/vert/light/zone counts against the engine's hard + practical ceilings
  (64 zones, name-table/index widths, typical node budgets for the software renderer) and warn on
  approach. Cheap once the native build exists; catches "castle grew past what the renderer likes"
  before it manifests as mystery slowness. (AI brainstorm 2026-07-16.)

### Gameplay-wiring intelligence (mission authoring)

- `[implement]` **Cross-tool lint: map actors ↔ dxconcli conversations.** A mission's `.con` binds
  conversations to actor `BindName`s; nothing verifies the two artifacts agree. A check (either tool's
  CLI) that every conversation BindName has a matching actor in the level trunk, and every
  conversation-bearing NPC in the map has its `.con` entry — catching silent no-conversation NPCs at
  build time instead of in-game. (AI brainstorm 2026-07-16.)

### Higher-level authoring

- `[spec]` **Floorplan compiler: `level scaffold --from plan`.** Compile a 2D floorplan (ASCII grid or
  small JSON: rooms with heights, door/corridor edges) into the grid-aligned subtract set + door cuts +
  a PlayerStart. One level of abstraction above the tracked wall-run/ring generators: those place one
  shape; this roughs out a whole connected level in one call — the natural LLM interface ("draw the
  map as text, extrude it"). Output is ordinary trunk actors, editable by every existing verb.
  (AI brainstorm 2026-07-16.) NB the `level scaffold` name is unrelated to the rejected `project
  scaffold` (project init) ruling.

- `[spec]` **Semantic texturing: `poly theme`.** Classify every face by role (floor/ceiling/wall/trim
  from its normal + position) and assign textures by catalog tag query ("floor←stone, walls←castle
  brick") in one command, instead of dozens of `poly set --texture` calls. Composes the texture
  catalog's tags with a face-role classifier; deterministic and reviewable (prints the plan first).
  **SEQUENCED AFTER the texture-catalog redesign** (`to-plan.md`) — its tag-query half rests on that
  work; fold it into that work's follow-on rather than speccing independently. (AI brainstorm 2026-07-16.)

### Leveraging the git trunk

- `[spec]` **Semantic `level diff` (worktree or `--git A..B`).** Instead of raw per-file T3D diffs:
  "3 actors added, Keep_a3 moved +128Y, 12 faces retextured, light L_4 brightness 40→120, brush
  Wall_x2 geometry changed". Reads two trunk states (git refs or dirs) and classifies per-actor
  changes — the review surface for level PRs, and the digest an LLM wants before merging. Optional:
  emit a before/after preview shot pair. (AI brainstorm 2026-07-16.)

- `[implement]` **`level blame` — per-actor change history.** Thin sugar over `git log --follow` on an
  actor's trunk dir: when each actor last changed, in which commit, alongside what. Answers "who moved
  my wall" once multiple sessions/branches edit one level. (AI brainstorm 2026-07-16.)

*(Parametric prefabs — dropped entirely 2026-07-19, Andrzej. Not parked.)*
