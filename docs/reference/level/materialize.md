# level materialize

**`level materialize`** is the pure build step: it drives **UnrealEd** to compile the selected
level's T3D trunk into the `.dx`/`.unr` **build artifact** — map-file output only (the T3D tree is the
source, reached via git, not a build target).

```
level materialize [--out OUT] [--overwrite] [--no-verify] [--keep-build] [--no-bsp-check]
```

- **`--out OUT`** names the destination map file (`.dx` or `.unr`). It **refuses to overwrite an
  existing file** (exit 2) unless **`--overwrite`** is given.
- A **post-build verify** (H3) confirms the rebuilt map matches the intended trunk; **`--no-verify`**
  skips it (debugging / known-buggy verify), and **`--keep-build`** copies the built map to the
  project's `.uedcli/tmp/` on a verify FAILURE instead of discarding it.
- Before any editor work, materialize checks that every package the level **references** (via a
  qualified `Class=` or a face's `Texture=`) is present on the configured package path. If any is
  missing it **exits 2 naming the complete set** and writes nothing, rather than silently dropping
  those references. This gate runs even under `--no-verify`. A composed package path that resolves to
  **0 packages** prints one advisory line but does not block a level that references nothing.
- The verify compares the built map against the trunk in UnrealEd's own terms, so it needs each actor
  class's **defaults** out of the game's `.u` packages. They are resolved *before* the editor starts,
  so an actor whose `Class=` is not fully qualified (`Package.Class`) — or whose package is missing
  from the configured paths — **exits 2 in about a second**, naming the actor and class, instead of
  failing after a full build. `--no-verify` does not need them.
- After a successful build+save, materialize runs two **advisory BSP health checks** and prints any
  findings to **stderr** — the exit code stays **0** (these report on an already-good build; they
  never fail it). The **build-output** check parses UnrealEd's own rebuild warnings (dropped faces,
  unlinked T-junction sides, sliver nodes) into counts; the **built-model** check reads the saved map
  and locates a defect the static `level doctor` cannot: **invisible walls** (near-zero-area BSP
  nodes). A check that cannot run (editor wedged, unreadable map) prints one "skipped" line and
  the build still succeeds. **`--no-bsp-check`** turns both off.
- **The AI path graph can be built natively, after the save and before the verify — opt-in, and off
  by default.** With the game's **`pathing`** key set in `~/.uedcli/config.toml` (see
  [Projects](../../README.md#projects-uedclitoml)) to a value other than `"none"`, uedcli reads the
  saved map and writes the graph the game's AI routes on: the `ReachSpecs` edge list, each
  `NavigationPoint`'s `Paths`/`upstreamPaths`/`PrunedPaths`/`VisNoReachPaths` slots and
  `nextNavigationPoint` link, and the `LevelInfo`'s `NavigationPointList`. UnrealEd's own
  `PATHS DEFINE` is never run. Nothing else in the map changes.

  | `pathing`       | Builds |
  |-----------------|---
  | `deusex-1112fm` | the Deus Ex 1112fm builder: sizes truncated, radii up to 115, heights 10–79, the 350-uu fall limit, and the search residue the retail maps carry (`visitedWeight`, `bestPathWeight`, `previousPath`, …) |
  | `ued22-469`     | the UnrealEd 2.2 (OldUnreal 469) builder: sizes rounded and capped at 70/70, jump-up on walls, no residue |
  | `none` (default, incl. when the key is absent) | no path graph at all — the map is left exactly as built |

  **This is a new, still-maturing feature.** On some levels the computed edge sizes can differ
  slightly from a reference build; treat a built graph as best-effort until it has seen more use.
  An unknown `pathing` value exits 2 naming `[games.<game>].pathing` and the three allowed values. A
  level with no `NavigationPoint` actors builds unchanged. The pass exits 2, writing nothing, when
  an actor's class does not resolve, a Mover has no built brush model, or the level carries a
  `WarpZoneInfo` (warp-zone marker edges are not built).
- Committing is your own `git`. Lightmaps, rebuilt BSP and the path graph are **regenerable build
  output**, never part of the level's identity.

*(A native, in-process Rust build is under development, targeting byte-identity with UnrealEd's build
of the same trunk; the editor path above remains the current one.)*

See also: [`level doctor`](doctor.md), [`level photo`](photo.md).
