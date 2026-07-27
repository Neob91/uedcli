# `level preview --game` — implementation plan

**Spec:** [`../specs/2026-07-13-ingame-preview-design.md`](spec-ingame-preview-design.md)
(spec gate RUN 2026-07-16, two cold reviewers, all findings folded as *(gate fold)* notes).
**Decisions:** `decisions.md` 2026-07-13 (the tier) + 2026-07-16 15:49 UTC (config-driven
asset/ini wiring — Andrzej). **Status:** draft. Ephemeral — delete once built; durable knowledge
folds into `architecture.md`.

**Priority context (Andrzej, 2026-07-16):** the native tier is ON HOLD (CSG core under active
parity work — its output can't anchor tests right now); `--game` builds FIRST. The standing goal's
UNATCO deliverable rides this tier via `--game --map` (no CSG anywhere in that path).

**BUILD STATUS (2026-07-16): DONE — `--game` boots reliably and delivered 10 UNATCO shots.**
G1-G3 code + 25 offline tests green; live boot (G4) resolved. The boot wedge was NOT memory
pressure — it was the ini `Paths=` globbing RAW `/resources` bind mounts, which tips the wine-8.0
esync startup lost-wakeup race to ~90% (the engine enumerates every Paths glob at first-package
bind; raw overlay/bind-mount dirs stretch the race window). **Fix:** `game-entrypoint.sh`
symlink-farms the composed content into LOCAL game-root dirs + STOCK RELATIVE Paths (uplayctl's
proven layout; the composed config still selects what's farmed, project-first). Boot→link ~60s at
93% CPU, reliable. **Bugs fixed en route:** CRLF-ini (wine wedges on LF), farmed-map docker-cp
collision (rm before cp), smart relaunch loop. **Delivered:** 10 faithful in-game UNATCO HQ shots
(`--game --map 03_NYC_UNATCOHQ.dx`), HUD/weapon hidden. Diagnosis: memory
`game-boot-pipe-read-flake-memory-pressure`; root cause found via two cold subagents +
`/proc/<pid>/wchan`. **REMAINING (G4 formal + G5):** SP-1..6 spike write-up, `dispatch`-path
regression test for the `--map` deliverable end-to-end, `architecture.md`/board reconcile (the
architecture bullet already describes the tier; add the symlink-farm boot note).

---

## 0. Concurrency contract (the native-materialize agent is still active)

**NOT touched:** `uedcli/native/*`, `uedcli-native/*`, `apply.py`/`materialize.py`/`packages.py`
internals (G3 only CALLS `run_materialize` through its existing API), `preview_native.py`,
`editor.py` (read for patterns; the game container gets its own module), `preview_shots.py`
grammar semantics (shared; additive helpers only if needed).

**Touched:** NEW `uedcli/preview_game.py`, NEW `uedcli/game/` (image build: Dockerfile,
entrypoint, uscript sources, build script, host substrate table), `dispatch.py` — ONLY the
`_level_preview` `--game` branch + error-catch list, `cli.py` — only help-text updates for the
now-functional `--map`/`--rebuild`/`--keep-alive`. Same standing rules: rebase-free, commit+push
per slice, re-run `bin/test` before each push, plain-merge on drift.

---

## 1. Slices (each: build → offline tests green → commit+push)

### G1 — UnrealScript package + game image + entrypoint (boots to the boot map, link answers)
- `uedcli/game/uscript/UedPreview/Classes/`: `UedPreviewConsole.uc` (Console subclass, Tick-poll
  ~1 s, spawns the link when possessed+absent — NotifyLevelChange misses the initial level),
  `UedPreviewLink.uc` (TcpLink 127.0.0.1:7777, `#<id> …` framing, verbs: `Ping`,
  `GetCurrentLevelName`, `GetPlayerPosition`, `TravelToLevel` [reply OK BEFORE `open` — the
  travel destroys the link], `Screenshot <x> <y> <z> <pitch> <yaw>` [re-ensure frozen/noclip/
  clean → pose → OK]), `UedPreviewBaseDriver.uc` + `UedPreviewDeusExDriver.uc`
  (`CleanFrameForPreview`: `ShowHud(False)`, null `Weapon`/`inHand`, flash zero, conversation
  guard; DX driver class baked in link defaultproperties). Engine.* only in the generic classes.
- Freeze: START with `bPlayersOnly` compiled in; SP-1 (G4) decides whether it stays or the build
  flips to `TimeDilation≈0` — one recompile, no runtime fallback (spec §5).
- `uedcli/game/` image build, uplayctl's shape, uedcli-owned: `Dockerfile` (`FROM dx-lum-uned`,
  warm-wineprefix `RUN xvfb-run -a wineboot -u`, baked `.u` + boot map + entrypoint),
  `build-image.sh` (flock; two-step: compile `.u` in a MOUNTED builder container against the
  game's own code dir from the composed config paths, source-hash stamp; then thin
  `docker build`), gitignored `uedcli/game/inputs/edit/` for the user-supplied v469 UCC
  toolchain (9 files, same provenance as uplayctl's — document `docker cp`/local copy; named
  exit-2 when absent). Boot map staged from the substrate's own Maps dir (DX: `00_Training.dx`).
- `game-entrypoint.sh`: assemble the game root from `/resources/<n>` mounts **in composed order
  (project shadows base)** — `System/` copy from the base code dir, `Maps/`/`Textures/` symlink
  farms across all composed dirs, Sounds/Music links; ini patch via the crafted-ini bind-mount
  pattern (KEY SET + exact names per spec §5 gate fold: `LocalMap`, `Console=`,
  `GameRenderDevice`/`RenderDevice=SoftDrv…`, `WindowedColorBits=32`, `StartupFullscreen=False`,
  `WindowedViewportX/Y`, `FirstRun=400`, generated `[Core.System] Paths`); launch with
  `WINEESYNC/WINEFSYNC` + `wineserver -k` + the relaunch-on-deadlock loop (~6×, ~100 s
  per-attempt link-bind gate); readiness signal = port 7777.
- **Verify (live, this slice):** container boots to the boot map, `Ping`/`GetCurrentLevelName`
  answer. ⚠️ background-job + long-fallback rules for every live wait.

### G2 — `preview_game.py` host side + dispatch/CLI wiring + offline tests
- `preview_game.py`: `GamePreviewError`; the host substrate table (ini name, `LocalMap` key,
  boot map, window-title pattern, exe) with the DeusEx row; hash-named freshness cache
  (`<level>.<hash12>.dx`, prune siblings, internal `run_materialize` call — never the CLI
  path); container lifecycle (mint uuid7, `docker run` with `-p 0:6080` + resource mounts +
  crafted ini, teardown in `finally`, `--keep-alive` guards the teardown + prints the noVNC
  URL); the 3-phase readiness/travel handshake; `docker cp` the target `.dx` into the Maps farm
  pre-boot; per shot: host-side pitch clamp ±89.9° → `Screenshot` → X-grab (largest
  title-matched window, splash excluded) → cp out → `shot_filename` naming.
- `dispatch._level_preview`: replace the reserved `--game` exit-2 with routing; `@actor`-with-
  `--map` rejection; `--fov`-with-`--game` rejection stays; `--map`/`--rebuild`/`--keep-alive`
  become functional (help text updated).
- **Offline tests (mock the docker/link/materialize seams):** cache decision matrix (fresh/
  stale/missing/`--rebuild`/`--map`), every §7 error path incl. the new taxonomy entries
  (image-build failure, no games config, docker unavailable, PlayerStart pre-check for trunks,
  `@actor`+`--map`, possession-timeout message), pitch clamp, protocol framing parse, host
  substrate table lookup.

### G3 — trunk-path plumbing
- Trunk previews: model-side PlayerStart pre-check (named exit-2 BEFORE any boot), materialize-
  into-cache via the internal API, overlay packages reaching the game (already free — the
  composed mounts carry the project dirs). Zero new editor-path code.

### G4 — live verify SP-1..SP-6 + acceptance (one spike dir)
- `dev/docs/spikes/2026-07-16-ingame-preview-verify/`: SP-1 freeze renders AND link answers
  under it (else flip the compiled freeze to `TimeDilation≈0` and re-run); SP-2 pose reaches
  pixels incl. pitch; SP-2b clean frame (no HUD/weapon/flash); SP-3 eye height exact (+
  `WalkBob` zero); SP-4 N shots one boot; SP-5 `--size` → grab is exactly WxH; SP-6 the D8
  spawn-failure signature (pin the `--map` no-PlayerStart error). Record verdicts + evidence
  images; fold any surprises back into the spec/architecture.
- Acceptance: a trunk preview (anchor trunk has a PlayerStart) + a `--map` retail preview.

### G5 — docs + board + deliverable
- `architecture.md` `level preview` bullet + "Preview internals" grow the `--game` half;
  `usage.md` banner line; board strike/done + new TODOs for anything deferred; `direction.md`
  needs nothing (already two-tier).
- **The standing goal's deliverable:** 10 posed shots of `03_NYC_UNATCOHQ.dx` via
  `level preview --game --map …` — real lighting, no CSG involvement.

---

## 2. Risks / watch-list
- **SP-1 link-under-freeze** is the design-level risk (spec §5 gate fold): if `bPlayersOnly`
  kills TcpLink ticking, flip to `TimeDilation≈0` (one compile-time switch, G1 isolates it).
- **Wine boot wedge**: mitigated by the ported relaunch loop; per-attempt gate keeps the hang
  guard honest.
- **Toolchain provisioning** is user-supplied/gitignored — named error, docs, never committed.
- **Concurrent materialize churn**: only G3 touches materialize (API call only); cache tests
  mock it.

## 3. Done when
Offline suite green with every named error path tested; SP-1..SP-6 verdicts recorded; a trunk
preview and a `--map` retail preview both produce posed, HUD-free, correctly-sized PNGs; docs +
board reconciled; the 10-shot UNATCO batch delivered.
