+++
priority = "p?"
kind = "unknown"
summary = "GUI explicit-rebuild spec omits Paths as UnrealEd's third build axis"
depends-on = ["gui-explicit-rebuild-pinned-build-state-mode"]
+++

# GUI explicit-rebuild spec omits Paths as UnrealEd's third build axis

Filed from a UED22-vs-GUI-spec gap audit (2026-09-15) of
`dev/docs/board/done/gui-explicit-rebuild-pinned-build-state-mode/` (spec content recovered from
`git show 3f57ab50:dev/docs/board/to-build/gui-explicit-rebuild-pinned-build-state-mode/spec.md`,
since `done/` trims it).

## UED22 fact

UnrealEd's build model has (at least) THREE independent computed-artifact axes, not two:
- BSP geometry — `MAP REBUILD` (`dev/docs/unrealed/commands.md` "Build pipeline").
- Lighting — `LIGHT APPLY` (same section; "geometry needn't be rebuilt; `MAP REBUILD` wipes
  lighting" — the two are explicitly independent triggers).
- **Pathnode reachspecs — `PATHS BUILD`** (same section: "`PATHS BUILD` constructs the reachspec
  graph ... `definePaths` (place markers) → `createPaths` (build all `FReachSpec`s) → `Prune`").

`dev/docs/unrealed/t3d.md` "What T3D cannot carry" lists all three as coequal, T3D-inexpressible
computed artifacts: "Computed BSP ... rebuild with `MAP REBUILD`", "Lightmaps ... rebuild with `LIGHT
APPLY`", "Pathnode reachspecs (`ReachSpecs`, `Paths`/`upstreamPaths` etc.) ... rebuild with `PATHS
BUILD`." Reachspecs are not wiped by `MAP REBUILD` (unlike lighting), so the three axes don't even
share one invalidation relationship — they're genuinely separate build state.

## What the GUI spec says

The explicit-rebuild spec's own stated goal: "**Match UnrealEd's own build model**: BSP geometry +
lighting are a built artifact that persists exactly as it was until explicitly rebuilt — never
silently recomputed because the trunk changed underneath it." Its "Two independent axes" section
enumerates exactly two: "1. The trunk/actor view" (Load) and "2. The solved-geometry build — CSG +
lighting" (Rebuild). Its persisted-state design (section 1) keys everything off `(geom_hash,
light_hash)`. No section mentions paths/reachspecs at all.

## The gap

The spec explicitly frames itself as reproducing "UnrealEd's own build model," but only reproduces
two of its three real, independently-triggered build axes. This isn't a case of the GUI choosing not
to VISUALIZE paths (a reasonable, separate scope call, and consistent with there being no path
rendering anywhere in any GUI spec) — it's that the spec's own goal statement claims parity with a
model that has a third axis it never accounts for, discusses, or explicitly excludes. A reader of
this spec alone would not learn that UnrealEd's build model has a pathing dimension at all.

Separately, this project already has a dedicated native-paths effort
(`dev/docs/board/to-build/native-path-build-reachspecs-in-level/`) building reachspecs into
`level materialize` — so the underlying data (a level's AI path graph) is on a path to existing in
this codebase, making "the GUI's build model has no path-axis story" a real forward-looking gap, not
a moot one.

## Why this matters

If/when the GUI ever surfaces "is this level's build up to date" status (the pin/gating mechanism
this spec builds), a user could reasonably read "Rebuild" as covering everything UnrealEd's Build
menu covers. It doesn't, and nothing says so.

## Not filed as an implement task

This doesn't propose adding path-graph rendering or a third pinned-hash axis (a real scope decision,
not obvious which way it should go given native path-build is itself still in `to-build/` and the
GUI is read-only/visualization-only in P1) — it flags that the spec's "match UnrealEd's own build
model" framing is incomplete and should either explicitly scope paths out (a one-line non-goal) or
be revised once native path-build lands.
