# AI pathing (`PATHS DEFINE`) — scoping draft

**Draft — a SCOPING document, not a build spec.** Pathing is a large feature and overlaps an
existing board item. This maps what exists, what is missing, the unknowns, and the scope/priority and
sequencing decisions the owner has to make. It does not commit a CLI surface.

## Goal

Let an LLM level-designer make a level navigable by NPCs/bots: author `NavigationPoint` actors
(PathNodes, patrol points, spawn markers, …) and run the path build that computes the reachspec graph
between them. Guiding board goal: expose everything the editor does without the GUI.

Background (engine facts, `dev/docs/unrealed/`): **NavigationPoints** are point actors the designer
places. The **reachspec graph** — which node can reach which, the `ULevel.ReachSpecs` array and each
node's `Paths`/`upstreamPaths`/`prunedPaths` — is COMPUTED, never authored, and cannot be carried in
T3D (`unrealed/t3d.md` "What T3D cannot carry"). Two editor verbs, disassembled and confirmed live
2026-06-23 / corrected 2026-07-15 (`unrealed/commands.md` `PATHS`):
- **`PATHS DEFINE`** (`FPathBuilder::definePaths`) only SPAWNS auto-marker NavigationPoints (an
  `InventorySpot` under each `Inventory`, a `WarpZoneMarker` under each `WarpZoneInfo`) and logs
  `DevPath: Defining paths.`. It builds NO reachspecs on its own.
- **`PATHS BUILD`** runs `definePaths` → `createPaths` (build all `FReachSpec`s) → `Prune`;
  `LOWOPT`/`HIGHOPT` set the optimization level (0/2, default 1). This is the real path build.
Paths are NOT wiped by `MAP REBUILD` (unlike lighting), but they go stale after geometry/actor
changes and must be rebuilt.

Note the item title names `PATHS DEFINE`, but per the 2026-07-15 disassembly the reachspec build is
`PATHS BUILD` — DEFINE alone yields no edges. The spec must build with `PATHS BUILD`.

## Current state — authoring exists, the build step is unwired

- **NavigationPoint placement: covered by the generic path.** PathNodes and other NavigationPoints
  are point actors, emitted by `actor build <Package.Class>` and landed with `actor add -`
  (`direction/generators.md`). No pathing-specific verb is needed to place a node.
- **The build step: NOT wired.** `level materialize`/`level apply` run `MAP REBUILD` + `LIGHT APPLY`
  (`uedcli/apply.py:289`, `uedcli/driver.py:485-487`) and NEVER `PATHS BUILD`. There is no `PATHS`
  driver method and no `level build` verb — `uedcli/cli/parsers/level.py` has no `build` subparser.
  So today a materialized map ships with NO reachspecs; NPCs can't path.
- **doctor: nothing pathing-aware.** No node-spacing check, no orphan-node check.
- **Overlapping board item.** `board/to-spec/level-build-paths-only-a-quality-escalation-knob` is
  the same build step from the other side: it proposes `level build` as a standalone paths-only verb
  plus a `--quality` (`BSP REBUILD LAME/GOOD/OPTIMAL`) knob for `level apply`, and states
  `PATHS DEFINE`/`PATHS BUILD LOWOPT/HIGHOPT` are confirmed and "no longer spike-gated". These two
  items MUST be reconciled — see Open questions (they likely merge, or split cleanly into
  authoring+doctor here vs the build verb there).

## The core tension — reachspecs need a build, and native path build does not exist

Placing nodes is a pure model-side edit uedcli already does. The reachspec graph is build output
(like lighting and BSP): it needs `PATHS BUILD` in the editor. There is NO native (editor-free) path
builder — the whole native-materialize effort is still fighting CSG/zone parity
(`board/inbox/native-*`), and paths are downstream of that. So for the foreseeable future, path
building is an EDITOR-ONLY step, which couples "make a navigable level" to the slow, crash-prone
editor container in a way pure authoring avoids.

## Design — options

**Split the feature into the two halves it naturally has:**

**1. Authoring + doctor (this item, recommended scope).**
- Rely on generic `actor build`/`actor add` for NavigationPoint placement — no dedicated verb unless
  a real ergonomic gap shows up (a `pathnode`/`nav` sugar verb is deferrable).
- Add offline `level doctor` checks that ARE decidable without a build: two nodes closer than the
  ~50uu minimum spacing (overview: "nodes ≥50uu apart"), and possibly a NavigationPoint with no
  other node within a plausible reach radius (a likely-orphan heuristic — needs judgement on the
  threshold and false-positive rate). The reachspec graph itself is build output, so "is node A
  actually reachable from B" is NOT offline-decidable and stays out.

**2. The build step (reconcile with `level-build-paths-only-…`).**
- Wire `PATHS BUILD` into a build verb (`level build`, or a step in `level apply`/`materialize`),
  with the `LOWOPT`/`HIGHOPT` quality knob. This is the substantive engine-side work and is where
  the two items overlap. Recommend it lives in the `level-build` item, and this item owns authoring
  + doctor, cross-linked by slug.

**Recommendation:** scope THIS item to authoring + doctor checks; move the `PATHS BUILD` wiring into
(or explicitly depend on) `level-build-paths-only-a-quality-escalation-knob`. Confirm with the owner
before splitting, since the item titles overlap.

## Big unknowns (flag, do not design around)

1. **Where does `PATHS BUILD` run?** A standalone `level build` verb only, or also folded into
   `level apply`/`materialize` (like `LIGHT APPLY` was)? Paths going stale after any geometry/actor
   change argues for the build verb; always-run-on-materialize argues for apply-folding. Owner call.
2. **DX substrate placeability of NavigationPoint classes.** The stripped substrate crashes on some
   engine classes (`Keypoint`; `board/README.md` portability goal). Confirm `Engine.PathNode` /
   `DeusEx.*` nav classes import cleanly before relying on generic placement.
3. **`PATHS DEFINE`'s auto-spawned markers.** `definePaths` spawns `InventorySpot`/`WarpZoneMarker`
   actors into the level. In a full-re-import materialize these are transient build artifacts, not
   trunk content — confirm they never leak back into the authored trunk (the trunk is the source;
   `direction/trunk-and-editor.md`).
4. **Node-spacing / orphan thresholds** for the doctor checks — need a real engine number and a
   false-positive assessment; the ~50uu is from the overview, unverified against the engine.

## Edge cases (for whatever v1 lands)

- A level with zero NavigationPoints → path build is a clean no-op, not an error.
- Nodes added/moved after a build → reachspecs stale; if paths aren't folded into materialize, a
  navigable ship needs an explicit rebuild (surface this so it isn't a silent trap).
- `PATHS BUILD`'s spawned markers must not survive into a `MAP EXPORT`-read trunk (unknown 3).

## Tests (for whatever v1 lands)

- doctor: two nodes <50uu apart → a finding; a well-spaced pair → clean. Orphan heuristic if adopted.
- build step (in whichever item owns it): a level with two PathNodes, after the build, has a
  non-empty `ReachSpecs` array (offline-decodable from the built `.dx`, like the BSP node-count
  checks in `unrealed/quirks.md`); `LOWOPT`/`HIGHOPT` accepted.

## Docs to update on build

- `docs/leveldesign/` — a pathing recipe (NEW craft knowledge → owner approval per `CLAUDE.md`).
- `docs/usage.md` — any new doctor category / build verb.

## Open questions

- Scope split + reconciliation with `level-build-paths-only-a-quality-escalation-knob`, and where
  `PATHS BUILD` runs — see `questions/pathing-scope-and-build-verb.md`.
- Substrate placeability, marker leakage, and spacing thresholds are live-verify unknowns, not owner
  forks — resolve with a spike.
