# Plan — native path build

Worktree `worktree-native-paths`, autonomous (owner ruling). Steps in build order; each step lands
with its tests. Rust is built and tested through the build container (`bin/_venv.sh
_rust_build_run`), Python tests with the stable-`TMPDIR` pytest invocation from `NATIVE-MATERIALIZE.md`.

1. **Collision spike** (`findings/60-collision.md`, running): extent `LineCheck`, `PointCheck`,
   `FindSpot`, `MultiLineCheck`/`MoveActor`/`FarMoveActor`, `FastLineCheck` vs the bake walker,
   `PointRegion`, `SetActorZone`. Pin constants in `test_pathing_facts.py`.
2. **`collision.rs`**: box sweep against a `Model`, point check, find-spot, mover-model tracing with
   the actor transform; `cargo test` goldens on hand-built BSPs (corridor, step, ledge, 0.7 slope,
   mover). Cross-check the box sweep against the retail Bar: every retail edge's straight line must
   pass the same sweep the engine passed.
3. **`paths.rs`**: scout movement (`walkMove` → `walkReachable`/fly/swim/jump helpers,
   `pointReachable`), `findBestReachable` + `defineFor` per preset, `addReachSpecs`,
   `insertReachSpec`, `Prune`, the `dx` route search for `addVisNoReach`; `build_path_graph` PyO3
   entry with a preset struct. Then `createPaths` (`Pass2From`, merge, gap fill) → `place_path_nodes`.
4. **Python**: `native/pathrules.py`; `native/paths.py` `apply_path_pass` (read → marshal → Rust →
   splice-rewrite with preserved header/GUID/generations and untouched bodies); `config.Substrate.pathing`
   + validation; `apply.py` hooks in both materialize paths; `level paths define` parser/command
   (strip by `auto-path-*` label, name reuse by position, moved/created names to stdout).
5. **Verification**: retail replay script (`harness/replay_retail.py`: strip → pass → diff, per-map
   report + miss classification) run over the 79 pathed maps; UED22 golden reproduction tests
   (`pathlab-define.dx`, `pathlab2-define.dx` with the InventorySpot exclusion, `pathlab-build.dx`
   placement); config/CLI tests; materialize regressions; wall-clock on Bar / Paris_Metro /
   UNATCOIsland.
6. **Docs**: `docs/reference/level/materialize.md`, new `docs/reference/level/paths.md`,
   `docs/reference/level/README.md`, `docs/README.md` games schema. Owner-gated texts
   (`direction/projects-and-config.md`, `architecture.md`, and a new dev/docs rationale note) written into
   `questions/` for the yes.
7. **Review + merge**: one code-review subagent with `rules/reviewer-brief.md`; fix; move the item
   to `done/`; squash-merge onto fresh master; push; remove the worktree.

## Interface contract (Rust ↔ Python) — AS LANDED (`uedcli-native/src/paths_py.rs`)

Superseded from the pre-build sketch below by the real PyO3 shapes, which the Python side
(`uedcli/native/pathrules.py`, `paths.py`) already targets:

```
PresetIn(*, scout_jump_z, scout_ground_speed, scout_max_step_height, scout_base_eye_height,
         radius_start, radius_phase_height, radius_phase_height_after_success, radius_cap,
         radius_stop, height_bump, height_phase_radius, height_cap, height_floor, height_stop,
         los_precheck, scout_on_traced_floor, know_visible, size_rounding: "round"|"trunc",
         jump_fall_limit, find_jump_up, prune_compare: "f32-le"|"f64-strict", bot_only_radius,
         monster_radius, monster_height, vis_scout_radius, vis_scout_height, residue: bool)
build_path_graph(model: Built|bytes, movers: list[MoverTuple], navs: list[NavTuple],
                 zones: list[ZoneTuple], level_zone: ZoneTuple, preset: PresetIn) -> PathGraphOut
place_path_nodes(model, movers, navs, zones, level_zone, starts: list[int]) -> PlacementOut
```

- `model`: a `Built` handle, or the serialized Model body bytes (`model_read.rs` parses them).
- `MoverTuple = (name, model_body_bytes, location xyz, rotation pyr, pre_pivot xyz, b_block_actors)`.
- `NavTuple = (index, class_kind, location xyz, rotation pyr, collision_radius, collision_height,
  b_one_way_path, lift_tag, url, tag)`; `class_kind` ∈ {navigationpoint, liftcenter, liftexit,
  teleporter, warpzonemarker, playerstart}; strings casefolded by Python; `index` = roster position
  (`None` holes already removed).
- `ZoneTuple = (zone_number, b_water, b_pain, damage_type_casefold, gravity xyz, fluid_friction,
  velocity xyz)`; `level_zone` supplies zone 0 / unzoned values.
- `PathGraphOut` is COLUMN-oriented, one entry per nav in roster order (not per-node objects):
  `specs: list[(distance, start_idx, end_idx, r, h, flags, pruned)]` in creation order;
  `paths`/`upstream`/`pruned_paths`/`vis_no_reach: list[[i32; 16]]`; `next_nav: list[i32]`;
  `residue: list[(visited_weight, best_path_weight, cost, b_end_point, previous_path, next_ordered,
  prev_ordered)] | None` (`None` for `ued22-469`); `nav_list_head: i32`; `num_pruned: u32`.
- `PlacementOut`: `created: list[xyz]`, `moved: list[(nav_idx, xyz)]`, `removed: list[nav_idx]`,
  `log: list[str]` (the editor's log lines, for tests).

Python owns: package read/write, class resolution, the presets table, labels/trunk writes, the CLI.
Rust owns: every geometric and algorithmic step. No fallbacks either side: a shape Rust cannot use
(non-finite location, unknown class kind) raises `PathError` naming the offending value.

## Spec drift found during the build (fold in before `to-plan` review)

1. **Package read API**: the pass reads via `upackage.parse_package_bytes` (+ `read_property_tags`,
   `object_path`), not `pkg_write.parse_package` as spec §3.1 says — `pkg_write` owns the re-lay
   (`relayout_package`), `upackage` owns the read. Update §3.1/§6.
2. **`bDeleteMe` navs**: left byte-untouched by the pass (not reset, not re-tagged). Spec doesn't
   rule on whether `undefinePaths`-equivalent reset should apply to a `ued22-469` re-run; note as an
   open point, not a bug, until the owner rules.
3. **Name table growth**: a native-built (pre-pass) package has no `Paths`/`upstreamPaths`/…
   property names in its name table yet; `relayout_package` appends them. So "names preserved
   verbatim" (spec §3.5) holds only when they already exist (an editor-built or previously-pathed
   package); a first pass on a fresh native build legitimately grows the name table. Update §3.5 to
   say "preserved, extended only by appending any new property/class names the pass introduces".
4. **`level photo --game` also materializes** (`preview_game.MaterializeResources.pathing`), so it
   needs a resolved `pathing` too — already wired by the Python build; spec §2/§6 named only
   `materialize`/`paths define` and should list `photo` alongside them.
5. **`require_pathing` is not the resolver `level materialize`/`level photo` use.** Spec §2 says "a
   missing key is validated at the use site" for both build-paths verbs via one `require_pathing`
   (hard exit 2). Landing that literally would have made `level materialize` — an everyday
   command — a breaking change for every existing project, since `pathing` did not exist in any
   config before this feature. Split instead: `config.effective_pathing`/`resources.resolved_pathing`
   (an absent key or games config → `"none"`, never an error) for `materialize`/`photo`;
   `config.require_pathing`/`resources.pathing_for` (hard exit 2) reserved for `level paths define`
   only, which is itself not registered in the CLI yet (item 6). `apply.run_materialize`'s `pathing`
   kwarg also defaults to `"none"` for the same reason, for any non-CLI caller. Update spec §2 to
   describe both resolvers and which verb uses which.
6. **`level paths define` is not registered in the CLI** (`uedcli/cli/parsers/level.py`'s
   `lsub.add_parser("paths", ...)` is a comment, not code) because its placer (`createPaths`) isn't
   implemented — a registered command that always raises `PathError("not implemented")` would be
   worse than no command. The command function, dispatch route and `docs/reference/level/paths.md`'s
   content (removed, not deleted-and-forgotten — restore verbatim once `createPaths` lands) all
   still exist. Update spec §5/§6 to note the verb ships disabled until §6 item 2 below is done; see
   `NATIVE-PATHING.md` "Next steps" for the exact re-enable sequence.

Reviewed and left as designed (not drift): `PathGraphOut`'s column layout is more efficient across
the PyO3 boundary than one struct per nav and needs no spec change beyond noting the shape above.
