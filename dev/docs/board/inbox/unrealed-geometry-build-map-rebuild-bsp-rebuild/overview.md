+++
priority = "p2"
kind = "docs"
summary = "UnrealEd geometry/lighting/paths build — reverse-engineered specification"
+++

# UnrealEd geometry, lighting, and paths build — reverse-engineered specification

Owner asked for a precise specification of how UCC.exe/UnrealEd's geometry build (`MAP REBUILD` /
`BSP REBUILD`) actually works, precise enough to reimplement from scratch with high confidence.
`spec.md` in this item is the deliverable.

**Round 2** extended the same spec to cover the other two operations the GUI's `Build` dialog exposes
— lighting (`LIGHT APPLY`) and AI paths (`PATHS DEFINE`/`PATHS BUILD`) — and pinned down exactly how
the `UnrealEd.exe` GUI (F8 dialog / Ctrl-B "Build All") dispatches all three: direct extraction from
`unrealed.exe`'s wide-string table shows it constructs the identical `MAP REBUILD VISIBLEONLY=%d`,
`BSP REBUILD <quality> [OPTGEOM] [ZONES] BALANCE=%d PORTALBIAS=%d`,
`LIGHT APPLY SELECTED=%d VISIBLEONLY=%d`, `PATHS DEFINE`, `PATHS BUILD` exec strings the console
verbs use — not a separate code path — cross-confirmed by `Editor.dll`'s own exec-parser recognizing
the same argument keys. New: spec.md §1.5 (GUI dispatch), §10 (lighting bake, ~190 lines), §11 (paths
build, ~160 lines). The lighting and paths material mined two more already-existing primary decode
docs in this repo's spike tree (`sections/20-lighting-bake.md`, 1268 lines; `sections/
30-ulevel-paths-assembly.md`, 628 lines, plus supporting docs) that hadn't previously been
synthesized into a coherent spec. Same evidentiary rule as round 1: no citation of
`uedcli-native`/`uedcli`/the board.

Built entirely from primary reverse-engineering evidence — static disassembly of the real
`Editor.dll`/`Engine.dll`/`core.dll` (RVA-cited), live-driven real-editor observation (console
commands, `Editor.log`, `gdb` breakpoints on the live process), and byte-level diffs against real
editor-written `.dx` packages. Per explicit owner instruction, **this project's own Rust/Python
reimplementation (`uedcli-native/`, `uedcli/`) and its board-tracked bugs were deliberately excluded**
as evidence — that code is an unproven hypothesis about the algorithms documented here, not ground
truth. Almost all of the primary decode material already existed in this repo's spike tree
(`dev/docs/spikes/2026-06-24-*-from-binary.md`,
`dev/docs/spikes/2026-07-15-native-materialize/{re-raw-zones,sections}/*.md`) from prior
investigation; this item's contribution is synthesizing ~18,000 lines of that material (read via 15
parallel research agents across three rounds, plus a direct wide-string extraction pass against
`unrealed.exe`/`Editor.dll` for the GUI-dispatch question) into one coherent, cross-checked,
confidence-tagged spec, explicitly flagging every place the source material itself is incomplete,
contradictory, or only inferred rather than disassembled (see spec.md §17-18).

Two genuinely open items surfaced by round 1's synthesis, not resolved by the existing evidence:
1. Whether `MAP REBUILD`'s console-parsed `BALANCE=`/`PORTALBIAS=` values (default 50/70) have any
   effect on the world-tree repartition, given that the actual repartition call
   (`bspRepartition@0x49fc0`) pushes hardcoded `Balance=12/PortalBias=0/GOOD` literals in its own
   machine code (confirmed by two independent decode passes) — and whether a bare `MAP REBUILD` runs
   `bspOptGeom` at all (live evidence says it does not re-run zone/leaf enumeration; `bspOptGeom` is
   ambiguous).
2. A direct citation conflict between two source decode documents on the `F_COSPATIAL_FACING_IN`/
   `F_COSPATIAL_FACING_OUT` numeric value assignment (spec.md §3.3).

Both need either a fresh live A/B test against the real editor or a fresh targeted disassembly to
close — flagged in spec.md §18 rather than guessed at.

**Round 3** answers the owner's follow-up — "is this enough to actually implement" — directly, in a
new spec.md §20. Short version: for orchestrating the real `UCC.exe`/`UnrealEd.exe` (§1-§11 as
written), yes — and that's not hypothetical, it's what this project's own architecture settled on for
`level materialize` after a from-scratch native attempt was tried and removed (commit `fbccd70`).
For a from-scratch native engine with no editor at runtime, not yet: three specific, well-characterized
gaps remain, none of them "the algorithm is unknown" — all three are "a real implementation attempt
built from the correct algorithm still didn't converge, for a reason not fully pinned":
1. **BSP repartition over-splits at real (700+ brush) scale** (§20.2) — `FindBestSplit`/`SplitPolyList`
   (spec §5) is the most rigorously byte-verified mechanism in the whole document and matches the real
   editor node-for-node at small (95-brush) scale, but at UNATCO scale a correctly-built implementation
   produced 57 surplus axis-aligned nodes the real editor doesn't. Root cause narrowed (a CSG-soup
   content difference upstream, not a partition-algorithm defect) but not pinned, despite ~2000 lines
   of prior live-`gdb` bisection.
2. **Export/import table ordering is not shown to be a deterministic function of the trunk** (spec
   §12.1, a new subsection this round) — every geometric `Surfs` field is 100% byte-exact against a
   real `.dx`, but the two object-table-index fields (`iActor`, `texture_ref`) are 0% positional
   match; no trunk-derivable ordering rule reaches better than ~40%. The one experiment that would
   settle it (does a *clean* re-import produce trunk-order tables?) was never run.
3. **Lighting and paths were decoded but never build-tested** — a native lighting implementation
   (824 lines) and paths/collision code existed in this codebase and were deleted at "stub" status in
   the same commit that ended the geometry effort; spec §10/§11's algorithmic content is as
   well-evidenced as geometry's, but unlike geometry it was never checked against an actual build
   attempt.

Also closed one real content gap while investigating this: `bspAddPoint`/`bspAddVector`'s point/vector
pool dedup rule (`FindNearestVertex`, nearest-not-first, address-cited thresholds) was already fully
decoded in the existing spike material but had never been added to the spec — now spec.md §3.10.

§20's evidentiary basis is explicitly different from the rest of the document (stated at its own
head): it's the git/architecture-doc history of the since-removed native implementation attempt,
cited as implementation-*outcome* evidence, not as a source for any claim about UnrealEd's own
internals — every other section's algorithmic claims still rest solely on primary editor evidence.