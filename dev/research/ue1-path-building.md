# UE1 AI path building — `PathNode`s, `ReachSpec`s, the Scout

**Date:** 2026-10-03 · **Status:** research only — no decisions taken, nothing implemented.
**Question:** How does UnrealEd's "Build Paths" actually work, how far has uedcli's native
reimplementation got, and what is left?

## Summary

- **The algorithm is fully decoded, not guessed.** `old/PATHING-BUILD.md` (465 lines) reads both
  engines' builders to the instruction, with RVAs, and pins the facts against 88 shipped Deus Ex
  maps plus three live UnrealEd goldens. This is a stronger base than anything public: the
  community wikis document the *struct* and the *concept*, never the constants or the search.
- **Two engines, two different builders.** `deusex-1112fm` (the retail Deus Ex engine, which built
  the shipped graphs) and `ued22-469` (the OldUnreal 469 editor uedcli drives) disagree on size
  caps, jump flagging, rounding and the prune boundary. Rebuilding a Deus Ex map in UnrealEd 469
  produces a materially *worse* graph, not an equivalent one — 199/1017 Bar edges get `R_JUMP`,
  which `ScriptedPawn` (`bCanJump=False`) cannot use.
- **Reachspec generation is done and near-exact.** The Rust core reproduces the UnrealEd golden
  `pathlab-define.dx` (281 specs) bit-exact including all four per-node arrays, and builds all 889
  retail Bar edges in retail order with retail `Distance`/height/flags/`bPruned`.
- **Two open gaps, both named.** (1) 81 of 889 Bar specs record the wrong `CollisionRadius`, all at
  4 wall-hugging nodes; the next step is disassembling the `dx` `BoxPointCheck`/`ClipToPoint`
  bodies. (2) `createPaths` — the PathNode *auto-placer* — is not implemented at all, so
  `level paths define` is deliberately unregistered in the CLI.
- **Shipped behaviour is unchanged.** `pathing` defaults to `"none"`; every existing project builds
  a path-less map byte-for-byte as before.
- **A doc-consistency bug found while reading.** `old/NATIVE-PATHING.md` states the 81 Bar misses
  record a radius *smaller* than retail, twice; its own worked example and
  `old/uedcli-native/src/paths_golden.rs` both say *larger*. One of them is wrong (the code comment
  is the one pinned by a test).
- **A stale engine claim still live in the KB.** `old/dev/docs/unrealed/leveldesign/kb/actors-collision-pathing.md`
  §7 still says `PATHS DEFINE` "only spawns marker NavigationPoints — no reachspecs", which
  `old/PATHING-BUILD.md` §8 explicitly corrects. The correction is gated on an owner ruling (board
  item `ued22-path-build-differs-from-the-deus-ex`, question 3).
- **Nobody else has done this offline.** The only comparable work is XC_Engine's from-scratch UT99
  paths builder — and it *changes* the algorithm (sorts pairs by distance, drops pruning entirely),
  so it is a divergent implementation, not a parity reference. Its repo carries **no licence**
  (GitHub reports `license: null`), so it is not reusable regardless.
- **Modern navmesh tooling is a validator, not a replacement.** Recast/Detour (zlib) could
  independently answer "should an edge exist between these two points?" and flag suspicious
  disagreements; it cannot reproduce UE1's grid-quantised sizes or its bookkeeping, which is where
  parity actually lives.

## What we have today

| Piece | Path | LOC | State |
|---|---|---|---|
| Reverse engineering | `old/PATHING-BUILD.md` | 465 | complete, merged |
| Campaign status doc | `old/NATIVE-PATHING.md` | 239 | current as of 2026-09-05 |
| Collision layer | `old/uedcli-native/src/collision.rs` | — | box sweep, point check, `FindSpot`, `PointRegion` |
| Scout traversal | `old/uedcli-native/src/scout.rs` | 769 | complete for both presets |
| Graph build | `old/uedcli-native/src/paths.rs` | 1511 | `definePaths` end to end; `createPaths` absent |
| Goldens | `old/uedcli-native/src/paths_golden.rs` | 245 | 2 committed + 2 `#[ignore]` retail |
| PyO3 surface | `old/uedcli-native/src/paths_py.rs` | — | `build_path_graph` wired; `place_path_nodes` raises |
| Python side | `old/uedcli/native/{paths,pathrules,pathplace}.py` | — | complete, tested against an injectable fake |

`cargo test` reports 143 passing, 2 ignored (the retail Bar fixtures are not committed — no retail
`.dx` in the repo).

**Reachable today:** `level materialize` / `level photo` build the graph when a project's
`~/.uedcli/config.toml` sets `pathing = "deusex-1112fm"` or `"ued22-469"` for that game. No project
does; `"none"` (the default) builds no graph.

**Not reachable:** `level paths define` — the parser entry was removed and left as a comment
because the placer behind it is a stub.

## Findings

### 1. What "Build Paths" actually is

Two distinct verbs, routinely conflated in community docs (verified in-repo,
`old/PATHING-BUILD.md` §2):

| Verb | What it does |
|---|---|
| `PATHS DEFINE` | **the reachspec build** — `undefinePaths` then `definePaths` over the already-placed nodes |
| `PATHS BUILD` | auto-*places* PathNodes (`createPaths`), with a `DEFINE` before and after it on `ued`; on `dx` it deletes every PathNode first and does **not** connect |
| `PATHS UNDEFINE` | empty `ReachSpecs`, drop the node list, destroy marker actors, reset the arrays |
| `PATHS REMOVE` | destroy every `PathNode` actor |
| `LOWOPT` / `HIGHOPT` | parsed and then **never read** on `ued`; one log line on `dx` |

The public record gets the shape right and the detail absent. The UnrealWiki states only that
"ReachSpecs must be built before the navigation network can be used" and that two nodes link "if
one of them is in the line of view of a bot located at the position of the other one and the bot
could go there at least in one direction" — community-documented, and consistent with what the
repo read from the binary, but with no constants
([UnrealWiki ReachSpec](https://beyondunrealwiki.github.io/pages/reachspec.html)).

`definePaths` in full (verified in-repo, `old/PATHING-BUILD.md` §2):

1. Get or spawn the Scout; `SetCollision(1,1,1)`, `bCollideWorld`, class-default size 52×50.
2. Marker pass: `WarpZoneInfo` → drop to a floor → spawn `WarpZoneMarker`. On `ued` only, one
   `InventorySpot` per `Inventory` — at a **garbage location** (X ≈ 1.8e25 on the Bar), a real
   editor defect. `dx` spawns none, which is why retail maps carry 0 `InventorySpot`s.
3. For each `NavigationPoint` in roster order: prepend to `NavigationPointList`, then
   `addReachSpecs`.
4. `Prune` every node, in list order.
5. `addVisNoReach` every node.
6. Destroy the Scout.

Because the traversal tests trace the BSP, a path build belongs **after** `MAP REBUILD` (which does
not clear reachspecs).

### 2. The native pipeline, as built

`old/uedcli-native/src/paths.rs` mirrors the above one function at a time, every constant carrying
its RVA in a doc comment. The geometric probes sit behind a `ReachWorld` trait (7 methods:
`line_visible`, `probe`, `vis_scout`, `fast_line_check`, `point_reachable`, `far_move_test`,
`line_hits_mover`) so the algorithmic layer is testable against scripted answers, and the real
implementation is `scout::CollisionWorld` over `collision::World`.

**Candidate pairs** (`add_reach_specs`): every other `NavigationPoint` that is not a `LiftCenter`,
within a straight-line **1000 uu** cutoff; with `bOneWayPath`, only nodes in front
(`rotator_x_axis` · delta > 0). Retail confirms the cutoff exactly: longest unpruned WALK edge
= 999.

**Special edges** skip the traversal test entirely: `LiftCenter` ↔ `LiftExit` with the same
`LiftTag` (500 / 60 / 60 / `R_SPECIAL`, both ways), `Teleporter` → `Teleporter` by `URL`/`Tag`
(100 / 150 / 150, one way, first match), `WarpZoneMarker` similarly. Retail Deus Ex carries **no**
`R_SPECIAL` edge at all — its Teleporters are map-exit markers with plain WALK edges.

**Sizing** (`define_for` → `find_best_reachable`): two sequential halving searches — radius first,
then height — over a probe that places the scout at `A` and asks `pointReachable(B)`. The recorded
sizes therefore land on a coarse grid, and retail sits exactly on it: the complete set of 33 `dx`
radii is `int(12 + 103k/32)` and of 33 heights `int(10 + 69k/32)`, over 128 178 specs. On `ued` the
grid is 9 radii (18…70) and 9 heights (44…70), so a 469-built graph **never records a size above
70/70** while retail carries 115/79 and heights down to 10.

**The collision primitive the scout uses** is an axis-aligned **extent box sweep** against the
level BSP — `BoxLineCheck`/`ClipTo`/`SetupHull` with edge bevels, plus a zero-extent walker — not a
cylinder. `old/dev/docs/unrealed/leveldesign/kb/actors-collision-pathing.md` lines 42–48 is
explicit that this box is correct *for the Scout's own purpose* and says nothing about how real
actors collide. **Movers are never traced during a path build**, in either engine: the
actor-collision query is gated on the level's collision hash, which the build's scout is never
added to, so `IsBlockedBy` is unreachable and `CheckEncroachment` is inert. Verified both by
reading the gate and by data — tracing movers loses exactly 15 retail Bar pairs and a `pathlab2`
closed-door pair from the goldens.

**Traversal** (`scout::walk_reachable` and friends): step toward the target at `MoveSize` 16,
100 ticks, with a steep-up rejection, `walkMove`'s four return codes (1 moved / 0 blocked / −1
ledge / 5 goal), step-up-finish-step-down on a hit, a floor probe at `MaxStepHeight + 2`, and on
failure a dispatch to fly, swim, `FindBestJump` (ballistic simulation at `dt = 0.1`) or — `ued`
only — `FindJumpUp`. `R_JUMP` is OR'd in **before** the jump attempt, which is why the 469 builder
marks so many edges unusable by non-jumping pawns.

**Bookkeeping** (`insert_reach_spec`, `link`): each node keeps its 16 shortest outgoing edges in
**descending** `Distance` order; a full list evicts slot 0 (the longest) unless the newcomer is
itself the longest, in which case it is dropped. A refused `upstreamPaths` insert leaves a
one-sided spec. This produces retail's 2 978 array-less specs and 5 770 one-sided slots — artefacts
a naive reimplementation would never generate.

**Pruning** (`prune`): for every detour `A→node→B`, prune the direct `A→B` when the detour is within
1.2× its distance and no less capable. The two engines differ at the boundary: `ued` compares
against `float32 1.2f` non-strictly, `dx` against the `double` just *below* 1.2 with the x87 at
64-bit precision, which for integer distances is exactly `5σ < 6γ` — pinned exhaustively in a test.
`simulate_bookkeeping.py` replays this over all 83 single-player retail maps and reproduces
120 976/120 976 `bPruned` bits and every array.

**`addVisNoReach`** runs the *runtime* route search from each node — `find_path_toward`,
`breadth_path_from` (a backwards Dijkstra along `upstreamPaths`), `expand_anchor`, `can_move_to` —
and that search's scratch is what leaves `visitedWeight`/`bestPathWeight`/`previousPath` residue in
the saved map. Nothing reads `VisNoReachPaths` at runtime; it still has to match for byte parity.

### 3. `ReachSpec` fields × native coverage

On-disk layout (verified in-repo, `old/PATHING-BUILD.md` §1.1):
`INT32 Distance · ci Start · ci End · INT32 CollisionRadius · INT32 CollisionHeight · INT32 reachFlags · u8 bPruned`.

| Field | Meaning | Produced by native today | Verified against the editor | Unknown / notes |
|---|---|---|---|---|
| `Distance` | Euclidean `|B−A|`, **doubled** for a swim edge; `appRound` on `ued`, truncated on `dx` | yes | yes — exact on all 889 Bar pairs and both UnrealEd goldens | — |
| `Start` | object ref to the source `NavigationPoint` | yes (roster index, mapped on the Python side) | yes | — |
| `End` | object ref to the destination node | yes | yes | — |
| `CollisionRadius` | largest scout radius that still traverses, snapped to the halving grid | yes | **no — 81/889 Bar specs disagree**; both UnrealEd goldens exact | the `dx` `BoxPointCheck`/`ClipToPoint` bodies are unread; suspected cause |
| `CollisionHeight` | largest scout height at the chosen radius | yes | yes — exact on all 889 Bar pairs | the stored (R,H) pair is never tested *together* on `dx` |
| `reachFlags` | mask from the last successful probe, or `R_SPECIAL` for lift/teleporter/warp edges | yes (1/2/4/8/32) | yes — exact on all 889 Bar pairs | no builder writes 16 or 64; `R_DOOR`/`R_PLAYERONLY` are consumer-side only |
| `bPruned` | set by `Prune`; the runtime reads every field *except* this one | yes | yes — 120 976/120 976 on the retail replay | — |
| `MaxLandingVelocity` | **UE2 only.** Absent from the UE1 on-disk struct | n/a | n/a | community-documented for UT2003/4 ([UnrealWiki](https://beyondunrealwiki.github.io/pages/reachspec.html)); not in this substrate |
| `bForced` | **UE2 only** (`ForcedPaths`) | n/a | n/a | the KB already records `ForcedPaths`/`ProscribedPaths`/`bNoAutoConnect` as verified absent from this build |
| `ExtraCost` / `bPlayerOnly` | per-*node*, not per-spec, in UE1; read by the runtime search only | **no** — the interface contract omits them; residue reads `cost = 0` and never skips a `bPlayerOnly` node | — | flagged, undecided (`old/NATIVE-PATHING.md` "Not done" item 5) |

Per-node arrays, all 16 slots with `-1` empty, all four produced natively:
`Paths`, `upstreamPaths`, `PrunedPaths`, `VisNoReachPaths`, plus `nextNavigationPoint` /
`LevelInfo.NavigationPointList`. Invariants hold across 178 532 retail array entries with zero
mismatches.

### 4. `reachFlags` bits

| Bit | Name | Meaning | Confidence |
|---|---|---|---|
| 1 | `R_WALK` | walking required | **verified in-repo** — `calcMoveFlags` `ued 0x10116cb0` / `dx 0x26d10`; `bCanWalk` |
| 2 | `R_FLY` | flying required | **verified in-repo** (same function); never written by either builder, never in retail |
| 4 | `R_SWIM` | swimming required; also doubles `Distance` | **verified in-repo**; 784 retail SWIM + 5 WALK\|SWIM + 2 WALK\|SWIM\|JUMP |
| 8 | `R_JUMP` | a jump was needed | **verified in-repo**; 1 508 retail WALK\|JUMP |
| 16 | `R_DOOR` | pawn must be able to open doors (`bCanOpenDoors`) | **verified in-repo** as a value; **no builder writes it** and retail carries none |
| 32 | `R_SPECIAL` | lift / teleporter / warp-zone edge (`bCanDoSpecial`) | **verified in-repo** (`ued 0x10176f76`, `dx 0xb2308`); absent from every retail map |
| 64 | `R_PLAYERONLY` | player-only edge (`bIsPlayer`) | **verified in-repo** as a value in *this* UE1 lineage; no writer found |
| 64 | `R_LADDER` | UE2 | **community-documented** for UT2003/4 — **conflicts** with UE1's 64 = `R_PLAYERONLY` |
| 128 | `R_PROSCRIBED` | UE2 | community-documented |
| 256 | `R_FORCED` | UE2 | community-documented |
| 512 | `R_PLAYERONLY` | UE2 | community-documented — UE2 **renumbered** this bit |

The UE1/UE2 divergence at bit 64 matters: the single most-cited public source
([UnrealWiki ReachSpec](https://beyondunrealwiki.github.io/pages/reachspec.html)) documents the UE2
numbering, which is wrong for Deus Ex. The repo's own binary reading is authoritative here. The
wiki also notes these enum names "are not accessible from within UnrealScript", which is why no
community tooling pins them.

The consumer's one gate is `supports(r, h, flags)` =
`CollisionRadius >= r && CollisionHeight >= h && (reachFlags & flags) == reachFlags` — the **pawn's**
flags must be a superset of the **spec's**.

### 5. The golden-data validation approach

`old/uedcli-native/src/paths_golden.rs` is the oracle harness. The design:

- **Inputs** come from a fixture triple produced by `extract_world.py`: a `.world.txt` text roster
  (navs with kind/location/rotation/collision/`bOneWayPath`/`LiftTag`/`URL`/`Tag`, zones, movers),
  a `.model.bin` level BSP, and `.mover<k>.bin` mover models.
- **Expected output** comes from `extract_fixture.py`: one `spec` line per reachspec with all seven
  fields, and one `nav` line per node with its `P`/`U`/`PR`/`VNR` 16-slot arrays.
- **`graph_diff`** compares by `(Start, End)` key, reports missing / differing / extra, *and*
  separately checks creation order and count, then every per-node array.

The oracle itself is **the engines' own output**, which is the right choice:

| Golden | Preset | Oracle | Result |
|---|---|---|---|
| `pathlab-define.dx` (40 navs, 281 specs) | `ued22-469` | a live ephemeral UnrealEd 469 driven by `live_paths.py` | **bit-exact**, all four arrays |
| `pathlab2-define.dx` (50 navs, 64 specs; water, closed door, lift, teleporters, pickups) | `ued22-469` | same | exact **except** `VisNoReachPaths` on 3 water-room nodes (15, 19, 48) |
| `02_NYC_Bar.dx` (889 specs) | `deusex-1112fm` | the shipped retail graph | all 889 pairs built in retail order with retail `Distance`/height/flags/`bPruned`; **81 radius misses** |

How close: **one map bit-exact, one map exact modulo a named undecoded subroutine, and the retail
spot-check exact on 6 of 7 fields.** The two retail tests are `#[ignore]` because no retail `.dx`
ships in the repo; they need `UEDCLI_PATHS_FIXTURE_DIR`. `nyc_bar_probe_trace` is a per-pair
diagnostic driven by `UEDCLI_PATHS_PAIR` (the worked case is pair `36,38`: retail radius 53,
native 86).

The `pathlab2` gap is honestly scoped: UnrealEd 469's own `findPathToward` is undecoded, so the
build runs the decoded `dx` route search under *both* presets, and it disagrees only there. The
test asserts `diffs.len() == 3` so the gap cannot silently widen.

**What is not yet done is the scale check.** The spec's acceptance bar (§7.1) is ≥ 99 % edge
agreement across all 79 pathed maps with every miss classified; only the Bar has been run, and
informally. The harness for the full corpus is unwritten.

### 6. Actor classes that participate

The builder's only class question is a small `IsA` ladder. `paths::NavKind` has exactly six values,
and `old/uedcli/native/paths.py` resolves them by `descends_from` against five `Engine.*` bases
with `navigationpoint` as the fallback:

| Class | Role in the build | Native today |
|---|---|---|
| `NavigationPoint` | the base; everything in the roster | yes (fallback kind) |
| `PathNode` | the generic node designers place | yes, as a plain `NavigationPoint` — the builder never names it |
| `PlayerStart` | an ordinary node for `DEFINE`; a **walk start** for `ued`'s auto-placer | kind exists; placer absent |
| `LiftCenter` / `LiftExit` | `R_SPECIAL` edges by `LiftTag`; a `LiftCenter` gets no ordinary edges | yes |
| `Teleporter` | `R_SPECIAL` edge to the `Tag` matching its `URL` | yes |
| `WarpZoneMarker` | spawned by the build for each `WarpZoneInfo`; `R_SPECIAL` edge by zone URL | yes |
| `InventorySpot` | spawned per `Inventory` by `ued` **only**, at a garbage location | deliberately **not** spawned (board ruling: the native build spawns no markers) |
| `PatrolPoint`, `HidePoint`, `AmbushPoint` | ordinary `NavigationPoint`s to the builder; consumed by `ScriptedPawn` orders at runtime | yes, as plain nodes; `PatrolPoint` is known to `old/uedcli/native/unbuilt.py`'s self-ref rewrite |
| `AIMarker`, `ScriptMarker`, `DeusExCarcass` | **do not exist in this substrate** — zero hits anywhere in the repo, and `DeusExCarcass` is not a `NavigationPoint` at all | n/a |

Deus Ex specifics worth recording: `PatrolPoint` is `Engine.PatrolPoint`, not `DeusEx.PatrolPoint`;
`AmbushPoint` exists in stock `Engine.u` but is effectively unused because DX drives NPCs through
`ScriptedPawn` orders rather than the Unreal AI ambush system; `AlarmPoint` does not exist in this
build; there is no `Ladder` NavigationPoint and no `JumpSpot`/`JumpDest` (climbable ladders are
texture-driven). All from
`old/dev/docs/unrealed/leveldesign/kb/actors-collision-pathing.md` §7 (marked 🔬 there).

Community mapping guidance agrees with the KB's numbers: pathnodes "shouldn't be spread more than
700 units apart (350 on stairs)", and without them "your pawns cannot navigate to a destination"
([Steam, *A.I. Navigation*](https://steamcommunity.com/sharedfiles/filedetails/?id=322411573) via
search summary; [DXEditing mirror](https://mirror.deusexnetwork.com/dxediting.com/tutorials.php?tutorial=27)).
The failure mode is silent: unbuilt paths mean AI pawns simply do not move. The KB adds that paths
also will not form over bad BSP, making a missing path graph a BSP-hole symptom.

### 7. Has anyone reimplemented this outside the editor?

**No parity reimplementation exists publicly.** What exists:

- **XC_Engine** (UT99 / UE1, Higor) ships a paths builder "rewritten from scratch". It
  deliberately *changes* the algorithm: pairs are sorted by distance before reachspec creation,
  which lets it "completely ditch the path pruning process". It also exposes a reference-pawn
  choice, an air-routes toggle, colour-coded reachspec rendering, and a "theoretical maximum
  distance of 2000" (vs stock UE1's 1000)
  ([UT99.org XC_Engine v23](https://ut99.org/viewtopic.php?t=13175)). `XC_PathsWorker` builds on it
  for relocating/defragmenting/re-indexing paths. **Licence: none.** `github.com/CacoFFF/XC-UT99`
  reports `license: null` via the GitHub API and is archived read-only since 2023-07-15 — so it is
  unusable as source *and* useless as a parity oracle, since it does not reproduce the stock
  builder.
- **The Scout is documented but not reimplemented.** The UnrealWiki confirms it is "used only by the
  editor during bot path building to find connections and check viability" and that it destroys
  itself in `PreBeginPlay()` ([UnrealWiki Scout](https://beyondunrealwiki.github.io/pages/scout.html));
  no constants.
- **No `ucc` commandlet for path building** turned up. Everything public routes through a live
  editor.

Conclusion: **uedcli's native build appears to be the only offline, parity-targeting
reimplementation of UE1 path building.** There is no external oracle to borrow; the retail corpus
and live-editor goldens already in the repo are the oracle.

### 8. Modern equivalents (short)

The "scout traversal test" is a **sampled agent-capsule traversability query** — in Recast/Detour
terms, roughly what the voxelization + walkable-slope/step/height filtering stages decide, except
UE1 answers it per candidate edge by *simulating the agent* rather than precomputing a surface.
Recast's pipeline is voxelize → filter non-walkable → partition into regions → re-triangulate; it
is zlib-licensed ([recastnavigation](https://github.com/recastnavigation/recastnavigation)).

UE1's builder is a **waypoint-graph** builder, not a navmesh builder, and its two interesting
heuristics have modern analogues: the 16-slot descending-distance cap is edge-degree limiting, and
`Prune`'s 1.2× detour rule is transitive-reduction with a slack factor and a capability guard.

**Where a modern technique could help — as a validator only:** build a Recast navmesh from the same
BSP, then for each native reachspec ask Detour whether a corridor exists between the two node
positions for an agent of the spec's recorded radius/height. Disagreements in *either* direction
(native built an edge Detour calls impossible, or dropped one Detour calls trivial) are candidate
bugs worth a human look. This would have been an independent signal on the 81-spec radius class.
It cannot *replace* anything: it reproduces neither the halving grid, nor `Distance` doubling for
swim, nor the eviction/prune bookkeeping — which is where byte parity lives.

### 9. The three board items

| Item | One line |
|---|---|
| `to-build/native-path-build-reachspecs-in-level/` | p1 implement — build the graph natively in `level materialize` plus a `level paths define` placer, rule preset per game; the live work, spec + plan reviewed, reachspecs done and the placer not |
| `to-spec/ai-pathing-paths-define/` | p? implement — the older, pre-spike framing ("NPC levels need NavigationPoints + `PATHS DEFINE`… implement as part of `level build`"); superseded in substance by the to-build item, carries one open question file (`pathing-scope-and-build-verb.md`) |
| `to-spec/level-build-paths-only-a-quality-escalation-knob/` | p2 implement — a `--quality` knob (`LAME`/`GOOD`/`OPTIMAL`) on `level materialize` plus a standalone paths-only `level build`; its draft spec predates the native ruling and still assumes paths come from driving the editor |

Two adjacent items also bear on this: `to-spec/reimplement-unrealed-s-paths-define-in-uedcli`
(p2, the original ask, now satisfied in substance) and
`ued22-path-build-differs-from-the-deus-ex` (owner-question — two of three resolved; the third,
correcting `dev/docs/unrealed/commands.md`'s `PATHS` entry, still needs a yes).

## Options

| Option | Pros | Cons |
|---|---|---|
| A. Close the 81-spec radius class first (`BoxPointCheck`/`ClipToPoint` disassembly) | the only blocker to a clean `deusex-1112fm` story; reproduction case already committed; smallest remaining unknown in the decoded path | disassembly work, hard to timebox; may not be the cause |
| B. Write the full-corpus replay harness first | turns one informal spot-check into the spec's actual acceptance number; may reveal that the 81-spec class is one of several, or the only one | if the radius bug is systematic, every map reports it and the numbers need redoing after the fix |
| C. Implement `createPaths` next and unblock `level paths define` | unblocks a whole user-visible verb; reuses `TestReach`/`TestWalk`/floor probing already built | the auto-placer is the *coarsest* part of the editor (`ued` moves hand-placed nodes; `dx` deletes them all); parity value is lower than the connector's |
| D. Add a Recast-based cross-check as a diagnostic | independent signal, zlib licence, catches whole classes of miss | new dependency and build surface for a tool that validates rather than ships; cannot adjudicate sizes |
| E. Ship `deusex-1112fm` as opt-in with the caveat documented, defer the rest | already the state of the branch; zero risk to existing projects | the parity bar is "exact match"; shipping at 99.99 % on one map is not that |

## Proposal (owner's call — not decided)

B then A, with the order from `old/NATIVE-PATHING.md` otherwise kept. The corpus harness is
mechanical, has no unknowns, and converts the single informal Bar result into the number the spec
actually asks for — which also tells you whether the 81-spec radius class is *the* miss class or
one of several before anyone spends a session in a disassembler. D is worth half a day as a
throwaway diagnostic only if A stalls. C is real work with a lower parity payoff and no one is
blocked on it today, since the verb is unregistered and documented as absent.

Separately, and cheaply: reconcile the smaller/larger contradiction in `old/NATIVE-PATHING.md`
against `paths_golden.rs`, and take the `commands.md` / KB §7 corrections back to the owner as one
decision rather than two.

## Open questions / what to verify next

1. **Does `old/NATIVE-PATHING.md` or `paths_golden.rs` have the radius direction right?** The test
   comment says native records *larger*; the status doc says *smaller*, twice, while its own
   example (pair `36,38`: retail 53, native 86) says larger. The test is the pinned artefact.
2. **Is the `dx` `BoxPointCheck`/`ClipToPoint` body the cause of the 81 misses?** Every other step
   of the placement path has been ruled out. Unread.
3. **Why does the `dx` builder flag so few drops `R_JUMP`** where `ued` flags 199/1017? Candidates
   named (traced-floor start, `JumpZ` 120, the 350-uu fall limit), none confirmed.
4. **Should the interface carry `ExtraCost` / `bPlayerOnly`?** They do not affect which edges are
   built, but they do affect the residue the route search leaves behind. Flagged, undecided.
5. **Is `ued22-469` parity on `VisNoReachPaths` ever required?** If not, the 3-node gap stays
   documented and UnrealEd's route search stays undecoded.
6. **`dx` explorer handedness** in `createPaths` — needs a live `PATHS BUILD` in a Deus Ex editor,
   or the sign of `UModel::LineCheck`'s normal.
7. **Did the retail designers ever run `PATHS BUILD`?** No data trace either way, so the residue
   attribution in §1.3 of `old/PATHING-BUILD.md` stays inferred.
8. **Unverified externally:** whether any UE2-era community tool rebuilds paths headlessly. The
   search budget ran out before `ucc`/UT2004 tooling could be swept properly; treat §7's "no" as
   well-supported for UE1 and only provisional for UE2.

## Sources

Internal (verified in-repo):

- `old/PATHING-BUILD.md` — the decoded algorithm, both engines, with RVAs and corpus statistics.
- `old/NATIVE-PATHING.md` — campaign goal, presets, parity bar, current status, next steps.
- `old/uedcli-native/src/paths.rs`, `scout.rs`, `paths_golden.rs`, `paths_py.rs`.
- `old/uedcli/native/paths.py` (`_KINDS`, `_nav_in`), `pathrules.py`, `pathplace.py`, `unbuilt.py`.
- `old/dev/docs/unrealed/leveldesign/kb/actors-collision-pathing.md` §§5, 7, 7.1, 8 — DX nav
  subclasses, spacing, human-scale anchors; §7's `PATHS DEFINE` claim is **stale**.
- `old/dev/docs/board/to-build/native-path-build-reachspecs-in-level/{overview,spec}.md` §7.1 —
  the acceptance bar.
- `old/dev/docs/board/to-spec/{ai-pathing-paths-define,level-build-paths-only-a-quality-escalation-knob,reimplement-unrealed-s-paths-define-in-uedcli}/`,
  `ued22-path-build-differs-from-the-deus-ex/overview.md`.

External (community-documented unless noted):

- <https://beyondunrealwiki.github.io/pages/reachspec.html> — the `ReachSpec` field list and the
  **UE2** `reachFlags` numbering (1/2/4/8/16/32/64/128/256/512); notes the enum names are not
  reachable from UnrealScript. UE2-scoped: its bit 64 contradicts UE1's.
- <https://wiki.beyondunreal.com/Legacy:ReachSpec> — same content on the live wiki; **403 to
  automated fetch**, read only via the mirror above.
- <https://beyondunrealwiki.github.io/pages/navigationpoint.html> — `bOneWayPath`, `ExtraCost`,
  `ForcedPaths[4]`, `ProscribedPaths[4]`, and the hidden `nextNavigationPoint`/`nextOrdered`/
  `prevOrdered`/`previousPath`/`cost`/`visitedWeight`/`bEndPoint`/`bestPathWeight`/`PathList`.
  UE2-era; `Paths`/`upstreamPaths`/`PrunedPaths`/`VisNoReachPaths` are **not documented there** —
  the repo's binary reading is the only source for them.
- <https://beyondunrealwiki.github.io/pages/scout.html> — the Scout is editor-only, self-destructs
  in `PreBeginPlay()`; no constants.
- <https://beyondunrealwiki.github.io/pages/bot-pathing.html> — concepts only; **explicitly** does
  not document reachspec generation, max path distance, spacing, pruning, Scout sizes or reachflags.
- <https://beyondunrealwiki.github.io/pages/pathnode.html> — stub, self-described as incomplete.
- <https://ut99.org/viewtopic.php?t=13175> — XC_Engine's from-scratch UT99 paths builder:
  distance-sorted pairs, pruning dropped, reference-pawn choice, air-route toggle, max distance
  2000.
- <https://github.com/CacoFFF/XC-UT99> — XC_Engine source; GitHub API reports **`license: null`**,
  archived 2023-07-15. Not reusable.
- <https://github.com/recastnavigation/recastnavigation> — Recast/Detour pipeline and the **zlib**
  licence.
- <https://steamcommunity.com/sharedfiles/filedetails/?id=322411573> — DX *A.I. Navigation* mapping
  guide: ≤ 700 uu spacing, 350 on stairs, pawns cannot navigate without pathnodes. **Read via
  search summary only** — direct fetch returned 429.
- <https://mirror.deusexnetwork.com/dxediting.com/tutorials.php?tutorial=27> — DXEditing tutorial
  mirror, same guidance. **Not fetched directly.**
- <https://docs.unrealengine.com/udk/Two/GameAndAIHandout.html> — Epic's 2001 Game & AI seminar
  handout, the most likely first-party description of the path builder. **403 to automated fetch —
  unverified, worth a manual read.**
