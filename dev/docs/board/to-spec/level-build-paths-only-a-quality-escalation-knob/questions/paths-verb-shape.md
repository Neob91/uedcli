# How does pathfinding reach the map — a `level build` verb, a `--paths` flag, or a post-process?

## Context

`PATHS BUILD` writes the reachspec graph into the map file. It must run AFTER materialize's FULL
RE-IMPORT (a `MAP NEW` wipes everything) AND after the post-verify (paths auto-spawn marker actors —
`InventorySpot`/`WarpZoneMarker` — not in the trunk, which would fail the actor compare). Paths are
build output, never authored, never in the trunk (same class as lighting/BSP).

Options:
- (i) `level build` = materialize + a paths stage, one verb with materialize's `--out` surface.
- (ii) **`--paths` flag on `level materialize`** (recommend) — paths as one more optional build
  stage; no duplicated verb surface.
- (iii) `level build` as a standalone post-process over an existing `--map` (`MAP LOAD` → `PATHS
  BUILD` → `MAP SAVE`) — decoupled and cheap to re-run, but a second editor round-trip and load path.

Recommend (ii). Pick (iii) if pathing should be re-runnable on an already-built map without a full
rebuild. The overview's wording ("standalone paths-only verb") leans toward (i)/(iii); flagging the
divergence.

## Answer

<!-- Empty = open. -->
