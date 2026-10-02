# Native AI path build — reachspecs in `level materialize`, `level paths define`

This is the single source of truth for the native path-build work: the goal, the two rule presets,
the reference we compare against, the parity bar, the method, the canonical scripts, and current
status. Read this before doing any native-pathing work so you don't re-derive it.

**Status: UNFINISHED, safe to merge as-is.** The PathNode placer (`createPaths`) is not
implemented, so **`level paths define` is deliberately NOT registered in the CLI** — the command
does not exist yet (`uedcli/cli/parsers/level.py` has a comment marking where to re-add it once the
placer is real; `uedcli/cli/commands/level.py`'s `_level_paths_define` and
`uedcli/native/pathplace.py` exist and are exercised directly by
`uedcli/tests/test_level_paths_define.py`, but nothing routes a real `argv` to them). The
`level materialize`/`level photo` reachspec-building integration IS reachable, but only when a
project's `~/.uedcli/config.toml` opts a game into `pathing = "deusex-1112fm"` or `"ued22-469"`; an
absent key or `pathing = "none"` (every project's config today) builds a map with **no** path graph,
byte-for-byte the same as before this feature existed — merging this branch changes nothing for any
existing project. See "Current status" below for exactly what is and isn't done.

## Goal

`level materialize` builds the git-tracked T3D trunk into a `.dx`/`.unr` map file; the built map's
`ULevel.ReachSpecs` and each NavigationPoint's `Paths`/`upstreamPaths`/`PrunedPaths`/
`VisNoReachPaths` are the AI path graph the game routes on. Historically this was empty
(`ReachSpecs.Count = 0`) — a map loads and plays without it, only NPC routing is absent. The
campaign goal is that **uedcli builds this graph itself, natively, with no UnrealEd involved at
all** (owner ruling, 2026-09-05) — reproducing the traversal test, edge sizing, bookkeeping and
prune exactly as one of the two decoded engines does it — plus a new **`level paths define`** verb
that auto-places PathNodes into the trunk the way the editor's own placer would.

The full reverse engineering of both engines' path builds — every constant, every algorithm — is
`PATHING-BUILD.md` (root); this doc does not restate it. The design (config, code layout,
verification plan) is `dev/docs/board/to-build/native-path-build-reachspecs-in-level/spec.md`; the
Rust↔Python interface is fixed in that item's `plan.md`.

## The two rule presets (`pathing` per game, `~/.uedcli/config.toml`)

Selected once per `[games.<name>]` table, never a CLI flag or env var (`direction/conventions.md`):

- **`deusex-1112fm`** — the retail Deus Ex 1112fm engine's own builder. Verifiable directly: rebuild
  a retail map's graph from its own built BSP and compare to what shipped.
- **`ued22-469`** — the OldUnreal 469 / UT-lineage editor's builder (what `level materialize`'s
  editor-driven path historically ran through). Verifiable against `PATHS DEFINE` goldens built with
  a live ephemeral editor.
- **`"none"`** — build no graph at all (today's behavior, still the default until a project opts in).

`PATHING-BUILD.md` §7 documents why these two disagree (size caps, jump flags, rounding, prune
boundary) and why `deusex-1112fm` is the one that produces a game-faithful graph.

## The reference we compare against

- **`deusex-1112fm`**: the 83 single-player retail `.dx` maps that already carry a shipped graph
  (`dev/docs/spikes/2026-09-05-pathing-build-re/`, `evidence/retail-stats.txt`). Strip the path data,
  rebuild it natively from the map's own BSP and mover models, compare edge-for-edge.
- **`ued22-469`**: two synthetic UED22-built goldens committed to the spike's `evidence/` —
  `pathlab-define.dx` (a corridor/hall/water/lift/teleporter/pickup test level, `PATHS DEFINE`, 281
  specs) and `pathlab2-define.dx` (64 specs) — built by driving a real ephemeral editor
  (`harness/live_paths.py`), never re-derived by hand.

## The parity bar

Exact match, by `(Start, End)` pair, of every `FReachSpec` field (`Distance`, `CollisionRadius`,
`CollisionHeight`, `reachFlags`, `bPruned`) and every per-node array (`Paths`, `upstreamPaths`,
`PrunedPaths`, `VisNoReachPaths`, `nextNavigationPoint`, `NavigationPointList`). No content
carveouts by default; a divergence is either fixed or named as an open miss class with its evidence
(mirroring `NATIVE-MATERIALIZE.md`'s prime directive — close a divergence by reproducing the
engine's actual algorithm, not by masking it).

Two narrow, evidence-backed exclusions stand today, both pinned in `cargo test`:

- **`VisNoReachPaths` under `ued22-469` on water-room nodes** (`pathlab2-define.dx`, 3 nodes): the
  editor's own `findPathToward`/route search that fills this array is undecoded for UED22 (only the
  `deusex-1112fm` route search — `findings/21-dx-reachability-and-ai.md` Part 2 — has been read to the
  instruction). `ued22-469` runs the decoded `dx` search as a stand-in; it disagrees only here.
- **Movers do not collide during either engine's `PATHS DEFINE`.** Both `Editor.dll`/`Engine.dll`
  gate `CheckEncroachment` and the collision-hash actor query on `Hash != NULL`
  (`ued 0x101601bc`, `dx 0x1015f3f4`), which is unset for the path-build's own scout — so a closed,
  `bBlockActors` Mover does **not** block the traversal test in either engine. Confirmed both ways: a
  `pathlab2` closed door pair reachspecs as plain WALK in the live UED22 golden, and 15 retail Bar
  pairs cross closed doors in the LOS pre-check; tracing movers as collision volumes loses exactly
  those pairs from both goldens, ignoring them (as coded) reproduces all of them. `collision.rs`
  therefore does not trace mover models during the path build at all — a deliberate simplification
  matching the engine, not a gap.

**Open, unresolved miss class** (not yet an accepted exclusion): 81 of 889 retail Bar specs record a
larger `CollisionRadius` than the native rebuild — see "Current status" below.

## The method

Same lockstep discipline as `NATIVE-MATERIALIZE.md`, scoped to this feature: build the Rust core
(`collision.rs`, `scout.rs`, `paths.rs`) behind an injectable `ReachWorld`/`World` trait so the
geometric probes can be swapped for a fixture in tests; pin every constant from `PATHING-BUILD.md`
with its RVA in a comment; verify against the two UED22 goldens (must be bit-exact) and the retail
Bar (must explain every disagreement, not just count them). Only once the Rust core is solid does the
Python side (`uedcli/native/paths.py`, already built) splice its output into a real package.

## THE canonical scripts (do not reinvent)

- **`dev/docs/spikes/2026-09-05-pathing-build-re/harness/simulate_bookkeeping.py`** — the Python
  reference for `insertReachSpec` + `Prune` bookkeeping, proven bit-exact against 83 retail maps and
  every UED22 live build. `uedcli-native/src/paths.rs`'s `insert_reach_spec`/`prune` must match it.
- **`uedcli-native/src/paths_golden.rs`** (test-only, `cargo test`) — loads the committed fixtures
  under `uedcli-native/fixtures/paths/` and asserts the Rust core's output against them. Two ignored
  tests (`nyc_bar_retail_dx_graph`, `nyc_bar_probe_trace`) need `UEDCLI_PATHS_FIXTURE_DIR` pointing
  at a `fixtures/paths/extract_world.py`-produced retail Bar export (not committed — no retail `.dx`
  in the repo); run with `-- --ignored`.
- **`uedcli/tests/test_native_paths.py`**, **`test_level_paths_define.py`** — the Python-side pass
  (config validation, splice round-trip, CLI contract) with an injectable fake graph
  builder/placer, since the real `uedcli_native.build_path_graph`/`place_path_nodes` need the Rust
  extension built.
- **`uedcli/tests/test_pathing_facts.py`** — the binary-constant pins from the original reverse
  engineering (unchanged by this work).

## Testing (same project rule as `NATIVE-MATERIALIZE.md`)

- `cargo test` runs in the containerized build image (`bin/_venv.sh`'s `_rust_build_run`); no host
  Rust toolchain needed. 143 tests pass, 2 ignored (retail Bar fixtures, not committed).
- Python: run only the relevant files with `TMPDIR=<repo>/_scratch/<name>` and
  `-p no:cacheprovider -o cache_dir=<tmpdir>/pc --capture=sys` (this mount's pytest capture tmpfile
  vanishes intermittently under the default capture mode). Never the whole suite for iteration.
- `uedcli/tests/test_doc_links.py` checks that a `to-build/` item's prose citations into
  `direction/`/`rationale/`/`rules/` resolve — an item's `spec.md`/`plan.md` lose their "ephemeral,
  unchecked" exemption once moved to `to-build/`. A citation to an owner-gated doc that does not
  exist yet must not be a backticked path; say it in prose instead.

## Current status (as of this session, 2026-09-05)

**Done and tested:**

- Full reverse engineering (`PATHING-BUILD.md`) — complete, merged to master before this work started.
- Board spec + plan, reviewed by two independent subagents (Opus, Fable 5.1), all findings folded
  in; item is in `to-build/`.
- Rust core:
  - `collision.rs` — the extent box sweep (`BoxLineCheck`/`ClipTo`/`SetupHull`, edge bevels), point
    check, `FindSpot`/`AdjustSpot`, `PointRegion`, `SingleLineCheck`/`SinglePointCheck`,
    `MoveActor`/`FarMoveActor`/`SetActorZone`. The zero-extent walker's hit fill is now fully decoded
    (`Location`, `Normal`, the start-in-solid case).
  - `scout.rs` — `walkMove`/`walkReachable`, fly/swim, `jumpLanding`/`SuggestJumpVelocity`/
    `FindBestJump`/`FindJumpUp`, `TwoWallAdjust`, `pointReachable`, `Reachable` dispatch, wired to
    both presets.
  - `paths.rs` — `FReachSpec`, `insertReachSpec`, `Prune` (both presets' compare semantics),
    `specFor`, `addReachSpecs` (cutoff, `bOneWayPath`, lift/teleporter/warp edges),
    `findBestReachable` (both halving-search grids), the `dx` route search
    (`SortedPathList`/`findVisiblePaths`/`findEndPoint`/`expandAnchor`/`breadthPathFrom`/…) for
    `addVisNoReach`, `definePaths` end to end.
  - `paths_py.rs`/`lib.rs` — `PresetIn`, `build_path_graph` (fully wired), `PathGraphOut`; the two
    presets' constants live in `uedcli/native/pathrules.py` on the Python side, mirrored 1:1.
  - **Verified bit-exact**: `pathlab-define.dx` (UED22, 281 specs, all four arrays).
  - **Verified edge-for-edge with one open miss class**: the retail Bar (889 specs) — every pair
    matches in creation order with correct `Distance`/height/flags/`bPruned`; 81 specs record a
    radius smaller than retail's.
  - **Verified except a named gap**: `pathlab2-define.dx` (64 specs) exact except `VisNoReachPaths`
    on 3 water-room nodes (UED22's own route search is undecoded; see above).
- Python side (complete): `config.Substrate.pathing` + validation, `native/pathrules.py`,
  `native/paths.py` (`apply_path_pass` — read, marshal, splice, re-lay), the hook in both
  `run_materialize` paths, `level paths define`'s command function and dispatch route
  (strip/place/label/name-reuse), user docs (`docs/reference/level/{materialize,README}.md`,
  `docs/README.md`), and their tests — all currently exercised against an **injectable fake** graph
  builder/placer, since the real Rust entries only just landed in this session.
- **`level materialize`/`level photo` are safe to merge as-is**: `config.effective_pathing` /
  `resources.resolved_pathing` return `"none"` for an absent key or games config (never an error),
  so an existing project's config needs no change and its build output is byte-for-byte unchanged.
  Only `config.require_pathing`/`resources.pathing_for` (used by the still-hidden
  `_level_paths_define`) hard-require the key — dormant code, not reachable from the CLI today.
  `apply.run_materialize`'s own `pathing` parameter also defaults to `"none"`, so a caller outside
  the CLI (an old `dev/docs/spikes/` harness, say) that doesn't know about this feature keeps
  building path-less maps too, instead of hitting a `TypeError` for a missing required argument.
- **User docs match this merge-safe state**: `docs/reference/level/materialize.md` describes the
  `pathing` presets as opt-in and marks the feature "still-maturing" (the retail radius miss class
  below); it no longer claims a missing key is an error. `docs/reference/level/paths.md` and its
  `README.md` row are removed — no doc describes a command that doesn't exist in the CLI yet.
  `docs/README.md`'s games-schema note says plainly that omitting `pathing` builds a path-less map.

**Not done:**

1. **`place_path_nodes` / `createPaths`** (`PATHING-BUILD.md` §4.1, `findings/10-ued-pathbuilder.md`
   §4.12–4.20): `testPathsFrom`, `Pass2From` (the wall-following walk), `TestReach`, `TestWalk`,
   `FindBlockingNormal`, `findScoutStart`, `newPath`, the 128-uu merge pass, the 600-uu gap-fill pass.
   The PyO3 entry point exists with the right signature and currently raises `PathError("not
   implemented")`. **Because of this, `level paths define` is NOT registered in the CLI parser**
   (`uedcli/cli/parsers/level.py` — the `lsub.add_parser("paths", ...)` block was removed and left as
   a comment pointing back here) — the command does not exist for a user yet, only for
   `uedcli/tests/test_level_paths_define.py`, which builds the `argparse.Namespace` directly and
   bypasses the parser. Re-add that block once `createPaths` is real and pinned against
   `evidence/pathlab-build.dx`'s 8 auto-placed nodes.
2. **The 81-spec Bar radius miss class.** All differences are "records a smaller radius than
   retail", never a missing or extra edge, and all cluster at 4 nodes near one wall (y = 128).
   Ruled out this session: `FindSpot`'s structure, `AdjustSpot`'s push-out formula, `FarMoveActor`'s
   call into `FindSpot`, `SingleLineCheck`'s flag filtering, `CheckEncroachment` (confirmed inert, see
   above), the walker's hit fill, nearby blocking actors (none). **Not yet read**: the `dx`
   `BoxPointCheck`/`ClipToPoint` bodies themselves — `findings/60-collision.md` §8 only checked their
   constants, not their full instruction sequence, and that is the next disassembly to do. Diagnostic
   tools are in place and committed: `paths_golden::nyc_bar_retail_dx_graph` (`--ignored`, prints and
   pins the measured per-map state) and `nyc_bar_probe_trace` (`--ignored`,
   `UEDCLI_PATHS_PAIR=<a>,<b>` traces one pair's probes in detail — e.g. pair `36,38`: retail radius
   53, native 86).
3. **UED22's own route search** (for `VisNoReachPaths` under `ued22-469`) — undecoded; `dx`'s is used
   as a stand-in and disagrees only on the pathlab2 water-room nodes.
4. **Retail-corpus replay at scale** — spec §7.1's acceptance plan (≥ 99% edge agreement across all
   79 pathed maps, every miss classified) has only been run informally against one map (the Bar) this
   session; the harness for the full corpus is not yet written.
5. **Whether the interface should carry `ExtraCost`/`bPlayerOnly`** for the residue fields — not in
   the current contract; residue reads `cost = 0` and never skips a `bPlayerOnly` node. Flagged, not
   decided.
6. Docs/tests explicitly noted as pending in the spec: the owner-gated `dev/docs` edits
   (`direction/projects-and-config.md`, `architecture.md`, a new `dev/docs/rationale/` note) are
   written nowhere yet — they need the owner's yes before landing, per `CLAUDE.md`.

## Next steps, in order

1. Disassemble `dx-engine` `BoxPointCheck`/`ClipToPoint` (the bodies, not just constants) and diff
   against `collision.rs`'s implementation, using `nyc_bar_probe_trace` on pair `36,38` as the
   reproduction case. This is almost certainly the fix for the 81-spec miss class.
2. Implement `createPaths` in `paths.rs` over the existing `CollisionWorld`/`ScoutPawn` (the pieces
   it needs — `TestReach`, `TestWalk`, floor probing — are already built for the reachspec pass and
   should be reused, not re-derived) and pin it against `pathlab-build.dx`'s 8 auto-placed nodes.
3. Wire `place_path_nodes` for real and re-run `test_level_paths_define.py` against the real
   extension (drop the fake placer where it was only standing in for the missing native code).
4. **Re-register `level paths define` in `uedcli/cli/parsers/level.py`** (restore the
   `lsub.add_parser("paths", ...)` block, currently a comment) and restore
   `docs/reference/level/paths.md` (delete the removal, or write it fresh) plus its row in
   `docs/reference/level/README.md` and the "See also" link in `materialize.md` — only after step 3.
5. Write the full-corpus retail replay harness and run it; record the acceptance numbers as
   committed evidence, same as `evidence/replay-results.txt` did for the bookkeeping-only replay.
   Once this clears the parity bar for `deusex-1112fm`, drop the "still-maturing" caveat from
   `docs/reference/level/materialize.md`.
6. Decode UED22's own route search if `ued22-469` parity on `VisNoReachPaths` is ever required project-
   side; otherwise leave the `dx`-search stand-in and its 3-node gap documented as-is.
7. Once (1)–(5) are solid, take the owner-gated doc edits back to the owner for a yes.

## Where the detail lives

- Reverse engineering: `PATHING-BUILD.md` (root), `dev/docs/spikes/2026-09-05-pathing-build-re/`
  (`findings/*.md`, `harness/*.py`, `evidence/`).
- Design + rulings: `dev/docs/board/to-build/native-path-build-reachspecs-in-level/`
  (`spec.md`, `plan.md`).
- Rust core: `uedcli-native/src/{collision,scout,paths,paths_py,model_read}.rs`,
  fixtures under `uedcli-native/fixtures/paths/`.
- Python side: `uedcli/native/{pathrules,paths,pathplace}.py`, `uedcli/apply.py`,
  `uedcli/cli/{parsers,commands}/level.py`.
