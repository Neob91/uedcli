+++
priority = "p?"
kind = "owner-question"
summary = "PATHS commands.md correction needs the owner's yes (paths 1 and 2 below, resolved)"
+++

# UnrealEd `PATHS` doc correction needs a ruling; native path-build questions resolved

Findings of the 2026-09-05 path-build reverse engineering (`PATHING-BUILD.md`,
`dev/docs/spikes/2026-09-05-pathing-build-re/`). Originally three questions; two are now resolved
by the owner's 2026-09-05 chat ruling and the follow-on native-build work
(`dev/docs/board/to-build/native-path-build-reachspecs-in-level/`, `NATIVE-PATHING.md`). One
remains open.

1. ~~A UED22 `PATHS DEFINE`/`BUILD` does not reproduce a retail Deus Ex graph~~ — **resolved**: the
   owner ruled `level materialize` builds the path graph natively (never by driving UnrealEd), with
   a `pathing` preset per game (`deusex-1112fm` reproduces the retail rules; `ued22-469` the editor's;
   `"none"` — the default — builds no graph at all). See `NATIVE-PATHING.md` for what is and isn't
   implemented yet.
2. ~~UED22's `definePaths` spawns one `InventorySpot` per `Inventory` at a garbage Location~~ —
   **resolved/moot**: the native build spawns no marker actors at all (`PATHING-BUILD.md` §4), so
   this defect of the editor's own builder never reaches uedcli's output.
3. **`dev/docs/unrealed/commands.md` "PATHS" and the 2026-07-15 spike §4 are wrong** (`PATHS DEFINE`
   is the reachspec build, `createPaths` is the auto-placer, cutoff 1000 uu, `supports` direction,
   LOWOPT/HIGHOPT no-ops, on-disk residue fields) — **still open**. Proposed replacement text:
   `PATHING-BUILD.md` §2 and §8. Needs the owner's yes before `dev/docs/unrealed/commands.md` is
   edited.
