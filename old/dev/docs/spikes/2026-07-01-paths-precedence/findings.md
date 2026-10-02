# Spike: `[Core.System] Paths` precedence (global-CLI overlay shadowing)

**Date:** 2026-07-01 · **Status:** complete · live-verified against an ephemeral UED22 editor.

**Question.** The global-CLI `paths` design (spec in board item `uedcli-as-a-global-cli-over-multiple-projects`
§3.4/§8) relies on *project-shadows-base*: a project package overrides a same-named base one, the way
the engine's own search path shadows. Verify the two hypotheses it rests on:
- **H1 — first-match-wins:** if two dirs on `[Core.System] Paths` each hold a same-named package, the
  one listed FIRST resolves (order, not filesystem luck).
- **H2 — override shadows substrate:** a dir prepended to `Paths` ahead of the baked substrate, holding
  a package that also exists in the substrate, shadows the substrate copy.

## Verdict: both HOLD.

- **H1 CONFIRMED, both orderings.** Two same-named `Foo.utx` made distinguishable by content
  (dirA = BobPage → `BP_FX_01/02/03`; dirB = InfoPortraits → 42 textures incl. `AlexJacobson`,
  `AnnaNavarre`). dirA-first → `Foo` resolved to A; dirB-first → flipped to B. Order decides.
- **H2 CONFIRMED, with control.** An override `CoreTexMetal.utx` (3 `BP_FX` textures) in a dir
  prepended ahead of the substrate shadowed the real substrate `CoreTexMetal` (175 metal textures → 3
  BP_FX); removing the override reverted to 175. The shadow was the override winning by order.

This is exactly the project-overlay-shadows-game-base behavior the design depends on.

## The method surprises (these shape the design — read them)

Getting a *reliable* by-name probe was most of the work. Three durable findings (folded into
`unrealed/quirks.md`):

1. **The running GUI editor rewrites `unrealtournament.ini` from its boot-time in-memory config, and
   actively ERASES any `Paths=` line `sed`'d in after launch** — worse than "doesn't re-read
   mid-session": it clobbers the edit, and a slow step between edit and read lets it win the race
   (caused spurious `Can't find file 'Foo'` until diagnosed). **Fix: do the ini edit + the consuming op
   in ONE atomic `docker exec`.**
2. **`UCC.exe` reads the ini fresh per invocation and performs the real by-name `Paths` glob search** —
   so `UCC batchexport <pkg> Texture pcx` is the correct precedence probe (the exported texture set
   reveals which file resolved).
3. **No live-editor console verb does a by-name `Paths` search:** `OBJ LOAD PACKAGE=Foo` is a silent
   no-op; `OBJ LOAD FILE=<bare-name>` fails; only `OBJ LOAD FILE=<resolved path> PACKAGE=` works
   (explicit file, sidesteps `Paths`). Only **directory-glob** `Paths=` entries (`<dir>/*.utx`) are
   searched — a full-file-path entry is not. No demand-load interference beyond the already-documented
   "qualified `Texture=` doesn't auto-demand-load."

## Design implication (folded into spec §8)

The editor's `[Core.System] Paths` precedence governs only the **indirect / by-name** linker path
(what UCC exercises). uedcli's shipped `apply` load path uses **explicit `OBJ LOAD FILE=<resolved
path>`**, so at apply **precedence is decided HOST-SIDE** by whichever resolver picks the file (today
`substrate_search_dirs`; under the global CLI, the composed `paths`, first-wins §3.4). The editor does
not shadow at load time for that path. So:
- the host-side composed-`paths` resolver MUST impose project-shadows-base when selecting files to
  `OBJ LOAD FILE=` (it already does — §3.4); the resolved code file is the stub, not the v68 original;
- the ini `Paths=` (for the by-name / UCC / demand-load path) must be written **project-first, stubs
  ahead of substrate**, and edited **atomically** with its consuming op.

## Artifacts

- Harness (this dir): `run_precedence.sh` (H1, both orderings), `run_shadow.sh` (H2,
  baseline/override/control). Both tear down container + volume on exit; the standing `dx-lum-uned` is
  never touched.
- Scratch (gitignored): `_scratch/paths-precedence/{dirA,dirB,override}/`.
