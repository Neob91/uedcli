# Blocker A: does uedcli compile the project's own `LUM_Core.u`, or consume a prebuilt one?

## Context

LUM mission maps can't materialize because the v69 editor can't load `LUM_Core.u`, the mod's own code
package. Unlike a shipped game `.u` (which uedcli stubs by decompiling), `LUM_Core` is compiled from
the LUM repo's own UnrealScript source. `architecture.md` currently lists it as explicitly out of
scope.

Two shapes:

- **uedcli compiles it** from source via a UCC build container (it already drives a UCC container for
  stub building) into a v69-loadable package, cached per-user like stubs. Most self-contained, but
  adds a "build a project's own code" capability and a source→package pipeline uedcli doesn't have
  today. Interacts with `direction/scope.md` (generic UE1 tool — a first-party-compile step must not
  bake in DeusEx/LUM specifics) and `containers.md` (never commit derived code).
- **uedcli consumes a prebuilt `LUM_Core.u`** that the LUM project builds by its own toolchain and
  places on the configured search path; uedcli just loads/stubs it like any other code package.
  Smallest change to uedcli; pushes the compile to the project's own build.

Recommendation: confirm which before planning — it changes the item from "add a compile pipeline" to
"place a package on the path". The spike (spec §Design) should report whether a built `LUM_Core.u`
already exists in the LUM repo output, which may make the consume option trivially available.

## Answer

<!-- Empty = open. -->
