# Spec — native path build

Owner rulings (2026-09-05, chat): paths are built **natively, never by driving UnrealEd**; `level
materialize` builds the reachspec graph; a new **`level paths define`** creates PathNodes in the
trunk, reproducing the editor's auto-placement; the rule set is **configured per game in
`~/.uedcli/config.toml`**; the placer follows **UED22's `createPaths`** for every preset. The
algorithms are the ones decoded in `PATHING-BUILD.md` (root) and
`dev/docs/spikes/2026-09-05-pathing-build-re/findings/`; this spec says what is built, where, and how
it is verified, and cites rather than restates. Reviewed 2026-09-05 by two subagents (Opus, Fable
5.1); their findings are folded in.

## 1. Scope

In:

- A native path builder: reachability test, edge sizing, bookkeeping, prune, `VisNoReachPaths`,
  marker links (`PATHING-BUILD.md` §3), parameterised by a **rule preset**.
- `level materialize` runs it on every build (editor-driven and native world build alike) as a
  pass over the built package.
- `level paths define`: a native world build + UED22's `createPaths` auto-placement
  (`PATHING-BUILD.md` §4.1), writing the new PathNodes into the trunk.
- The `pathing` key of `[games.<name>]`, two presets, user docs, tests, the retail verification.
- A prerequisite spike: the collision layer (§8.1).

Out:

- The Deus Ex 1112fm wall explorer (`PATHING-BUILD.md` §4.2; handedness unverified, no editor to
  test it) — the placer is UED22's for every preset (owner ruling).
- Editor-driven `PATHS *` verbs; InventorySpot/WarpZoneMarker spawning (§4).
- Presets for engines nobody has decoded (Unreal 22x, UT 436): adding one is a data change once its
  `Engine.dll` has been read with the same harness. A UT/Unreal project can honestly pick only
  `"none"` today; the pass itself is format-agnostic (`.dx`/`.unr`).
- Building mover private models on the native world path (a known gap; §3.2 says what happens).

Naming note: the engine's `PATHS DEFINE` connects nodes and `PATHS BUILD` places them; uedcli's
`level paths define` places nodes (the owner's name). The user doc states the mapping once.

## 2. Configuration — `pathing` per game

```toml
[games.deusex]
paths = "/…/System:/…/Maps:…"
pathing = "deusex-1112fm"        # or "ued22-469", or "none"
```

- `pathing` is a `Substrate` field (`config.Substrate.pathing: str | None`), read through the
  project's game like `ignore_props`. It is never a CLI flag or an env var (`direction/conventions.md`:
  the same project always builds the same graph on every host).
- The loader accepts the key and rejects an unknown value (`ConfigError`, exit 2, naming table, key
  and the three allowed values). A **missing** key is validated **at the use site** — `level
  materialize`, `level photo` (it materializes first) and `level paths define` exit 2 naming
  `[games.<name>].pathing` and the allowed values — so verbs that never build paths (`texture
  search`, `actor find`, …) keep working with an old config (`direction/projects-and-config.md`
  blesses lazy resolution). No default, no inference from the game name.
- `"none"`: build no graph — `ReachSpecs.Count = 0`, no nav arrays, no residue, today's output.
  `level paths define` under `"none"` exits 2 naming the key (placement needs the reachability test).
- Every existing config gains a `pathing` line (no back-compat shim). The `[games.*]` schema is
  described in `direction/projects-and-config.md` and `docs/README.md`; the direction edit needs the
  owner's yes (`Confirmed: projects-and-config` trailer) — §10.

Presets are one frozen dataclass each (`uedcli/native/pathrules.py`); every field is a constant from
`PATHING-BUILD.md` §3 with its RVA in a comment. What differs:

| Field                                   | `deusex-1112fm`                       | `ued22-469` |
|-----------------------------------------|---------------------------------------|---
| scout `JumpZ` / `GroundSpeed` / `MaxStepHeight` / `BaseEyeHeight` | 120 / 120 / 25 / 0 | 320 / 320 / 25 / class default |
| radius search (start, height, step, cap, stop) | 12, 10, 103, 115, step < 1     | 18, 39, 52, 70, step < 2 |
| height search (start, radius, step, cap, floor, stop) | 10, **12**, 69, 79, 10, step < 1 (the stored (R, H) pair is never tested together) | 44 (40+4), best radius, 26, 70, 40, step < 1 |
| probe start                             | LOS `SingleLineCheck(TRACE_World)` A→B first (movers included); scout placed by `FarMoveActor(bTest=0)` (fit + encroachment) on the traced floor under `A` (79-uu probe, else `A.Z − A.CollisionHeight`) + its height; `pointReachable(B, bKnowVisible=1)` | `FarMoveActor(bTest=0)` at `A.Location`; `pointReachable(B, 0)` (BSP-only `FastLineCheck` from the eye) |
| stored size / `Distance`                | `int()` truncation                    | `appRound` (round-half-even) |
| jump: fall limit / `FindJumpUp` on a wall | 350 uu / no                         | none / yes (step-up 48) |
| prune: factor, compare, `BotOnlyPath`, `MonsterPath` | 1.2, strict `<`, `R < 12`, `R ≥ 22 && H ≥ 51 && !FLY` | 1.2f, `≤`, `R < 24`, `R ≥ 52 && H ≥ 40 && !FLY` |
| `addVisNoReach` scout                   | 22 × 51                               | 18 × 39 |
| marker actors spawned                   | none (as the engine)                  | none (deviation from the editor, §4) |

Everything else is shared and is taken from `PATHING-BUILD.md` §3.1–3.7 verbatim: the 1000-uu
cutoff, `bOneWayPath`, the special-edge table (lift both ways; teleporter/warp first match in roster
order; all tag/URL compares case-insensitive FName/`appStricmp`), swim `Distance` ×2, the movement
constants (§3.4), `insertReachSpec`, `Prune`'s structure, `addVisNoReach`, `NavigationPointList` =
reverse roster. Scout setup shared by both: `SetCollision(1,1,1)`, `bCollideWorld`, class default
52×50 until the first `SetCollisionSize`, `ReducedDamageType` = class default (`None`), pain tests on
`FootRegion`, water tests on `Region`.

## 3. The path pass (what `level materialize` runs)

A pure function over a **built package**: `native.paths.apply_path_pass(package_bytes, preset,
schema) -> package_bytes`. Both materialize paths call it on the map they are about to verify and
swap in — the editor path after `MAP SAVE` + `cp_out`, the native path on `assemble_unbuilt`'s output
— so there is one builder and one test surface, and its input is what the game loads.

1. **Read** (`upackage.parse_package_bytes` + `read_property_tags`/`object_path`,
   `umodel.parse_model_body` on the `ULevel.Model` export). The roster is the `Actors` array in order;
   `None` holes are skipped (retail carries them; `dx definePaths` `if !a: continue`); `bDeleteMe` is
   a `ued`-only filter and is applied under `ued22-469` only; `ued definePaths`' trailing-`None` trim
   is **not** reproduced (the pass never shrinks the roster; native output has no trailing holes, an
   editor save's holes are parity-accepted as they are). Collected: every `NavigationPoint`-family
   actor (`Location`, `Rotation`, `CollisionRadius/Height`, `bOneWayPath`, `LiftTag`, `URL`, `Tag`);
   the `ZoneInfo`s (`bWaterZone`, `bPainZone`, `DamageType`, `ZoneGravity`, `ZoneFluidFriction`,
   `ZoneVelocity`) resolved to zone numbers with `materialize._model_point_region`, unzoned/zone-0
   points taking `LevelInfo`'s zone values; every Mover with its **built private model**, `Location`,
   `Rotation`, `PrePivot`, `bBlockActors`. Class membership through the game's schema
   (`classindex.ClassIndex`), never a name suffix.
2. **Collision world** (Rust, new `collision.rs`): the level `Model` for BSP queries plus each
   Mover's own built `Brush` UModel traced in mover space with the actor transform — exactly what
   `MultiLineCheck` does through the collision hash, blocking iff the scout has `bCollideWorld` and the
   Mover `bBlockActors` (`ued 0x10113fd0`). No convexity assumption. An editor-built or retail package
   carries every mover model; the native world path builds them with
   `unbuilt.build_mover_shape_model` (byte-verified on UNATCO's 28 movers) — a Mover whose model
   cannot be built exits 2 naming it. Pawns and Decorations are ignored (`IgnorePawns=1`); other
   `bCollideActors && bBlockActors` actors are **not** modelled in this change; the retail replay (§7)
   measures what that costs. Queries (decoded by the prerequisite spike, §8.1): `UModel::LineCheck`
   with extent (`ued 0x1ae4c0`, the box sweep behind `MoveActor 0x1608e0`/`MultiLineCheck 0x161500`),
   `UModel::PointCheck` (`0x1aeba0`), `ULevel::FindSpot` (`0x1602e0`), `CheckEncroachment`
   (`0x15f370`, reduced to the mover models), `UModel::FastLineCheck` (`0x1ada40` — **not** the
   existing `linecheck.rs` walker, which is the LIGHT APPLY bake walker with lighting flag semantics;
   the spike pins whether they coincide), `UModel::PointRegion` (`0x1aee60`).
3. **Scout movement** (Rust, `paths.rs`): `walkMove`, `walkReachable`, `flyReachable`/`swimReachable`
   with `flyMove`/`swimMove`/`findWaterLine`, `jumpLanding`, `SuggestJumpVelocity`, `FindBestJump`
   (preset fall limit), `FindJumpUp` (`ued22-469` only), `TwoWallAdjust`, `pointReachable` (editor
   semantics: no range cap), `Reachable` dispatch — pseudocode `findings/11` §4, `findings/21` Part 1.
   LOS probes: `pointReachable(…, 0)` is BSP-only `FastLineCheck` from the eye; `dx
   findBestReachable`'s pre-check and `addVisNoReach` (both presets) are `SingleLineCheck(TRACE_World)`
   against BSP **and** movers.
4. **Edges** (Rust): `addReachSpecs`, `defineFor`/`findBestReachable`, `insertReachSpec`, `Prune` in
   `NavigationPointList` order, `addVisNoReach` including its `findPathToward` runs (`findings/21`
   Part 2 for the `dx` search; UED22's search is undecoded, so under `ued22-469` the residue fields
   are not reproduced and §7.2 excludes them). Output: `ReachSpecs`; per node `Paths`, `upstreamPaths`,
   `PrunedPaths`, `VisNoReachPaths`, `nextNavigationPoint`, and — `deusex-1112fm` only —
   `visitedWeight`, `bestPathWeight`, `cost`, `bEndPoint`, `previousPath`, `nextOrdered`/`prevOrdered`;
   `LevelInfo.NavigationPointList`.
5. **Write** (Python): **splice**, never re-synthesize. The parsed `ULevel` body keeps every field
   (`TimeSeconds`, `FirstDeleted`, the 16 trailing refs, `TravelInfo`); only the `ReachSpecs` run is
   replaced. Touched actor bodies get their tagged-property lists rewritten in
   `uprops.class_serialization_order` (most-derived first; the 16-int arrays as one tag per
   non-default element, `findings/30` §3.2), StateFrame and untouched tags preserved byte-for-byte.
   The package is re-laid with the resized bodies (`pkg_write.relayout_package`, all bodies
   offset-free per `findings/../30-ulevel-paths-assembly.md` §5.2) with header, GUID, generations,
   and the name/import tables preserved **verbatim except for appending any new property/class name
   the pass introduces** (a pre-pass native build has no `Paths`/`upstreamPaths`/… names yet). Under
   `"none"` the pass is skipped.

Exit conditions (`direction/conventions.md`, no partial results): an unresolvable actor class, a
Mover without a buildable model, a `WarpZoneInfo` (§4), a Model with no nodes while nav actors
exist, or a package the writer cannot re-lay → exit 2 naming the offending actor/value, nothing
written. Zero nav actors is a clean no-op.

The post-build verify is unaffected: every field the pass writes is non-editable and already
dropped by the schema edit-rule (`normalize.is_authored_prop`); §7.5 tests it on a pathed level.

## 4. Marker actors — the InventorySpot question

The owner asked whether InventorySpots are needed natively. No:

- The Deus Ex builder never spawns them (`dx-engine 0xb1363` handles `WarpZoneInfo` only); no retail
  map contains one. `deusex-1112fm` spawns nothing.
- UED22 spawns one per `Inventory` at a garbage location; they carry no edges and contribute no
  `createPaths` start (`No valid start found`), so skipping them changes no edge and no placement.
  `ued22-469` spawns nothing either — a documented deviation whose parity cost is the exclusion set
  in §7.2.
- `WarpZoneMarker`s are spawned by both engines per `WarpZoneInfo`; no Deus Ex map has one. Not
  built; a `WarpZoneInfo` under either preset exits 2 naming it (never a silently missing warp edge).

## 5. `level paths define` — auto-placing PathNodes into the trunk

```
level paths define [--tree level/<name>]
```

1. Load the trunk; `build_world_model` for the BSP and `build_mover_shape_model` per Mover; the
   collision world of §3.2. `"none"` → exit 2 naming `pathing`.
2. Strip the previous auto-placed nodes — every `NavigationPoint` carrying an `auto-path-*` label
   (§5a), from any earlier run — mirroring `ued buildPaths`' strip of `bAutoBuilt` PathNodes. Removed
   names go to stderr.
3. `createPaths` (`PATHING-BUILD.md` §4.1, `findings/10` §4.12–4.20): the wall-following walk from
   every `PlayerStart` with the 70→28 radius sweep at height 40; the 128-uu merge pass; the 600-uu
   gap-fill pass. It reads no reachspecs (every probe is `TestReach`/`TestWalk`/`pointReachable`/
   `FastLineCheck`), so no graph is built first. Its movement rules are **UED22's wholesale**
   (`ued22-469` movement + `FindJumpUp`, no fall limit, `JumpZ −1`/`GroundSpeed 320`/`MaxStepHeight
   24` from `buildPaths`) for every preset, per the owner's ruling; the game preset contributes
   nothing here.
4. Nodes the algorithm **moves** (merge survivor to the midpoint; the "closest path" branch) are
   moved, hand-placed ones included — faithful to the ruled-on algorithm (owner ruling 2026-09-05);
   every moved name is printed (§5.6) so the change is visible in git.
5. Write: `Engine.PathNode` (the substrate schema decides the package), `Location` from `newPath`
   (48 uu above the floor), the run's `auto-path-<token>` label, rank appended. Names: a new node whose position matches a
   just-stripped auto node within 1 uu **reuses that node's name and rank** (stable re-runs);
   otherwise `t3dtree.alloc_name("PathNode", existing)`. Reachspecs are not stored in the trunk
   (build output, `direction/materialize.md`).
6. Output: created and moved actor names, one per line, on stdout (producer convention); counts
   (starts walked, created, merged, moved, removed) on stderr.

5a. **Marking auto-placed nodes** (owner ruling 2026-09-05): one batch label per run,
`auto-path-<token>`, minted like `actor duplicate`'s `dup-<token>` (`t3dtree._rand_suffix`, unique
among the level's labels), stored in the labels sidecar. The strip in §5.2 matches the prefix
`auto-path-*` over every run; the token tells runs apart in `actor find --label`.

## 6. Code layout

| Where                              | What |
|------------------------------------|---
| `uedcli-native/src/collision.rs`   | extent line check, point check, find-spot, mover-model tracing (§3.2) |
| `uedcli-native/src/paths.rs`       | scout movement, `findBestReachable`, `addReachSpecs`, `insertReachSpec`, `Prune`, `addVisNoReach` + the `dx` route search, `createPaths` |
| `uedcli-native/src/lib.rs`         | `build_path_graph(model, movers, nav_actors, zones, preset) -> PathGraph`, `place_path_nodes(...) -> (created, moved)`; `PathError` |
| `uedcli/native/pathrules.py`       | the two presets (§2) |
| `uedcli/native/paths.py`           | `apply_path_pass`: read, marshal, call Rust, splice-rewrite (§3.1, §3.5) |
| `uedcli/apply.py`                  | call the pass in both materialize paths before verify |
| `uedcli/config.py`                 | `Substrate.pathing`, value validation; use-site required check |
| `uedcli/cli/parsers/level.py`, `cli/commands/level.py` | `level paths define` |
| `docs/reference/level/materialize.md`, new `docs/reference/level/paths.md`, `docs/reference/level/README.md`, `docs/README.md` (games schema) | user docs, same change |
| `dev/docs/architecture.md`, `direction/projects-and-config.md`, a new dev/docs/rationale note | owner-gated (§10) |

## 7. Verification and acceptance

1. **Retail replay (primary).** For each of the 79 pathed single-player maps: strip the path data,
   run `deusex-1112fm` on the package (its own BSP and mover models; movers at their saved pose,
   checked against `KeyPos[0]`/`BasePos` before a mover mismatch is scored as a miss), compare with
   the original: edge set by `(Start, End)`; on shared edges `Distance`, `R`, `H`, `reachFlags`,
   `bPruned`; the four arrays; the residue fields as a separate, non-gating per-map match count.
   Acceptance: edge set agreement ≥ 99 % corpus-wide **and** every disagreement classified (stale
   post-build edit, unmodelled blocking actor, mover pose, a movement rule read wrong); bookkeeping
   exact wherever edge set and per-edge fields agree. Per-map numbers and the classification are
   committed as evidence. A percentage hiding a systematic miss class is not acceptance.
2. **UED22 goldens.** `ued22-469` on `evidence/pathlab-define.dx` (no pickups) reproduces
   `ReachSpecs`, the four arrays and the `nextNavigationPoint`/`NavigationPointList` chain
   **exactly**; on `evidence/pathlab2-define.dx` the same with the exclusion set {the `InventorySpot`
   export, its list links, `Inventory.myMarker`}. Residue fields are excluded for this preset
   (UED22's search is undecoded). `place_path_nodes` on `pathlab-define.dx` yields the 8 auto nodes
   of `pathlab-build.dx` at the same coordinates (all pass-3 midpoints — pass 1 is exercised only by
   the anchors it logs, a known gap), and the pass on the result matches its 329 specs.
3. **Unit pins** (`cargo test`): the box sweep against hand-built BSPs (corridor, step, ledge, a
   slope at `Normal.Z` 0.7, a mover model), `walkMove`'s four return codes, both size-search grids,
   `insertReachSpec` and `Prune` on the replay cases; the collision constants pinned from the spike.
4. **Config/CLI**: unknown `pathing` → load-time exit 2; missing → exit 2 at materialize / paths
   define naming key and values; `"none"` builds a path-less map; `level paths define` under `"none"`
   exits 2; the stdout/stderr contract; name reuse across two runs.
5. **Materialize**: `test_materialize_verb.py`, `test_native_roundtrip.py`, `test_pathing_facts.py`
   green; a level with no nav actors is byte-identical to today; a pathed level materializes and
   passes the post-build verify.
6. **Performance**: measured wall-clock on `02_NYC_Bar`, `10_Paris_Metro` (699 nodes / 10 127
   specs) and `01_NYC_UNATCOIsland` (1 198 / 12 514), recorded in the pass's rationale note (§10); the pass runs
   in every materialize and has no skip flag other than `pathing = "none"`.

## 8. Prerequisite spike and risks

8.1 **Collision layer spike** (running, `findings/60-collision.md`): `UModel::LineCheck` with
extent, `PointCheck`, `FindSpot`, `MultiLineCheck`'s hit filtering, `MoveActor` end to end,
`FarMoveActor` (incl. the `bTest=1` question: does a test move leave the actor in place? — it decides
where the `dx` scout stands and how `pointReachable` nudges `Dest`), `FastLineCheck` vs the bake
walker, `PointRegion`, `SetActorZone`. Pinned by `cargo test` constants + `test_pathing_facts.py`.
The build does not start on §3.2 until it lands.

Risks:

- The box sweep decides every edge; a wrong threshold shows up as a systematic miss class in §7.1.
  If the bar is not met after the spike, the classes go on the board and the honest figure is
  recorded — no relaxed acceptance.
- Movers: pose (`KeyPos[0]` vs saved `Location`), `PrePivot`/`Rotation` transform of the model.
- Zones on the native world path: `zones.rs`'s flood is approximate vs the editor
  (`architecture.md`), and water/pain/gravity tests key on it; the replay (retail zones) does not
  measure this.
- `Pass2From` is 🔬 inferred structure; the pathlab golden barely exercises it.
- Residue fidelity (`deusex-1112fm`): running the same searches in the same order; measured, not
  gated.
- Performance: an estimate says tens of millions of box sweeps for the Bar; measured in §7.6.

## 9. Parity ladder — untouched (owner ruling 2026-09-05)

The lockstep ladder must not be affected: its harnesses, goldens and gate are not touched. That holds
by construction: `actor_parity.py` builds native maps through `build_world_model` + `assemble_unbuilt`
directly (`parity_compare.build_native_lit_dx`), never through `run_materialize`, and the path pass
hooks only into `run_materialize`/`_materialize_native` — so the ladder keeps producing path-less
maps against path-less goldens with no config or harness change. The graph is verified by the retail
replay (§7.1) and the UED22 goldens (§7.2). One optional byte-check of the splice-rewrite and the
`ued22-469` preset against the editor — a golden built with the existing builder's `--rebuild-cmd
"MAP REBUILD;PATHS DEFINE"` vs native on a scratch project whose game has `pathing = "ued22-469"` —
runs as a test of this item, outside the ladder.

## 10. Docs and owner-gated edits

User docs in the same change (§6). Owner-gated, proposed text parked in `questions/` at plan time until the yes:
`direction/projects-and-config.md` (the `pathing` key in the `[games.*]` schema, `Confirmed:`
trailer), `architecture.md` (native core section, module map), a new rationale note under dev/docs/rationale/ (one pass over
the package; presets as data; no marker spawning; the verb-name mapping). `unrealed/commands.md`
PATHS correction is already pending (`ued22-path-build-differs-from-the-deus-ex`).
