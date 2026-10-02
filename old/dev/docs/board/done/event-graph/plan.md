# Plan — `event graph` (build item 10, Analysis)

**Ephemeral.** Folds into `architecture.md` + `usage.md` + `decisions.md` once landed.

## Goal
A pure, offline, model-side query verb that scans the selected level's T3D actors and prints
the **Tag↔Event wiring** (who-triggers-whom) plus a wiring lint. No editor, no container.

In UE1/Deus Ex an actor's **`Event`** prop is the event it FIRES; another actor's **`Tag`**
prop is its receiver identity. An edge `A → B` exists when `A.Event == B.Tag` (non-empty,
case-insensitive FName match). A `Trigger` with `Event=OpenDoor` triggers every actor whose
`Tag=OpenDoor`.

## Surface
- New group `event` with one sub-verb `graph` (room to grow later).
- `event graph [--dot | --json]` (the two output flags mutually exclusive; default = text).
- Level-scoped, like `level doctor`/`level status`: resolves the SELECTED level, **no
  `--target`** (stash/prefab are geometry captures, no eventing use-case).

## Output (producer conventions)
- **default text → stdout**, one wiring per line:
  `Trigger1 (DeusEx.Trigger) --OpenDoor--> Door3 (Engine.Mover)`
- **`--dot` → stdout**: Graphviz DOT (`dot -Tpng`), every participating node + every edge.
- **`--json` → stdout**: `{nodes:[…], edges:[…], lint:[…]}`.
- **lint findings + summary counts → stderr** (text/dot modes) so the stdout pipe stays clean;
  `--json` folds lint into the object.
- **Exit 0** on any successful scan, lint findings included (a producer/query verb — lint is
  advisory; real errors — no project/level, bad flags — still exit 2 via the standard guards).
  Documented as a load-bearing choice in decisions.md.

## Model (new module `eventgraph.py`, pure)
- **Node** = an actor that participates in eventing: has a non-empty `Event` OR a non-empty
  `Tag`, OR is a Mover (`movers.is_mover`, so a tagless mover still shows). Fields: name, class,
  event, tag, is_mover.
- **Edge** `A → B` when `A.Event == B.Tag` (case-insensitive), both non-empty. Self-edges kept
  (self-triggering).
- **Unset/default Tag:** UE1 defaults an unset `Tag` to the class name at runtime. We treat
  ONLY an explicitly-set, non-empty `Tag` as a matchable receiver (a default/class-name Tag is
  NOT an edge target). Load-bearing → decisions.md + inbox note for Andrzej.

## Lint
- **`dangling_event`** — `Event=X` matches no actor's Tag (fires into the void).
- **`unreachable_tag`** — an explicit `Tag=Y` no `Event` targets (unreachable receiver);
  **excludes movers** (they get the mover-specific finding below).
- **`unreachable_mover`** — a Mover with an explicit Tag nothing targets AND not self-moving
  (its `InitialState`, if set, is not a self/bump/loop state). Conservative: a tagless mover is
  NOT flagged (its trigger mechanism — bump/loop — isn't reliably knowable offline). Documented.
- **`cycle`** — a directed cycle (Tarjan SCC: any SCC of size >1, or size 1 with a self-edge).
  Reports the member names.

## Tests (`test_eventgraph.py`, offline)
Pure-module: build graph, each lint category with a fixture level, empty/no-event level = clean.
Dispatch: text, `--dot`, `--json` output modes; exit 0 with lint; no-project/no-level exit 2.

## Docs
`usage.md` (new verb row), `architecture.md` (module in the map + a Commands entry),
`decisions.md` (unset-Tag treatment + exit-0-on-lint), inbox (assumptions + limitations:
Dispatcher `OutEvents`/Counter multi-event fire props are NOT modelled — single-`Event` edges
only; no `--strict` exit yet).
