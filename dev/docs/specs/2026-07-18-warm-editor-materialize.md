# Warm editor container for `level materialize` (design spec)

**Status:** specced 2026-07-18; 2-reviewer design gate run + resolved 2026-07-18 (rulings:
`decisions.md` 2026-07-18 22:18 UTC; original decisions: 2026-07-18 21:52 UTC).
**Blocking spike:** SP-E — **RAN 2026-07-19, and it FALSIFIED the core premise for the current
drive+verify** (`spikes/2026-07-18-warm-editor-materialize/results.md`). A reused editor builds
*content* correctly, but reused builds **fail ~50% of the time** because the H3 post-verify, run
against the warm editor, breaks the next build's `MAP SAVE`. The design needs a fix (candidate:
run H3 verify against a separate throwaway editor, or add a real editor-quiesce barrier) and a
re-run before it ships — see §8 SP-E RESULTS. This is now an open design decision for Andrzej
(flagged in `board/inbox.md`); the build is NOT green-lit as specced.

---

## 1. Problem / motivation

Every editor-driving build pays a **full editor boot** today. `level materialize`
(`apply.run_materialize`) mints a fresh per-command container (`uned-<uuid7>`): `docker compose
run` + a fresh WINEPREFIX volume (seeded from the image bake) + Xvfb/wine/UnrealEd launch +
window-ready poll + per-package `OBJ LOAD`s — and tears it all down at the end (`stop_editor`,
container + volume). `level preview --game` pays the same cost indirectly: it calls
`run_materialize` whenever the trunk changed (its delivered-map cache is trunk-hash-keyed via
`preview_game.materialized_dx`), so the "cold preview of an edited level" path carries a full
editor boot inside it.

The `--game` preview tier already solved the identical problem for the *game* container
(spec `2026-07-17-game-preview-warm-container.md`, built + live-verified 2026-07-17: cold ~60s →
warm reuse ~2.2s). This spec applies the same warm-container design to the *editor* container so
repeated materializes reuse one booted editor instead of re-booting per invocation. Andrzej's
framing: reuse as much of the existing warm-preview setup (design AND machinery) as is reasonable.

What warm reuse can and cannot save: it eliminates the **boot** portion (container create, prefix
seed, wine + editor launch, ready-poll) and may shrink the **package preload** (whether a resident
package's `OBJ LOAD FILE=` is a cheap no-op is SP-E.3); it does NOT shrink the per-build drive
itself (T3D full re-import, `MAP REBUILD`, `LIGHT APPLY`, `MAP SAVE`, H3 verify), which is
per-invocation work regardless. SP-E.5 measures the split so the win is quantified, not assumed.

## 2. Decisions (Andrzej — ledger entries 2026-07-18 21:52 + 22:18 UTC)

1. **Warm the current path; no new flag.** `level materialize` today IS the editor build; this
   spec warms that path as the default behavior, with no CLI surface change. The `--editor` flag
   *name* arrives later, with the native-default cutover — and this AMENDS the 2026-07-14 "editor
   ditched entirely (no fallback editor path)" stance recorded in the native-materialize spec §4:
   the editor build path now SURVIVES the cutover behind `--editor`, with this warm machinery
   carrying over unchanged. *(Rejected: introducing `--editor`/`--native` on materialize now —
   native isn't wired into the verb and isn't playable at DX scale yet; a flag split is that
   cutover's scope.)*
2. **Busy or pinned-mismatched → fall back to per-command ephemeral.** The warm container is a
   fast path, never a bottleneck: acquisition uses a NONBLOCKING per-user flock, and any
   contention (lock held) or a pinned container with a different fingerprint sends THIS invocation
   down today's ephemeral `ensure_editor`/`stop_editor` path. Parallel materializes still compose
   (the 2026-07-06 05:12 per-command parallelism property is preserved — one invocation gets the
   warm editor, the rest get ephemerals). *(Rejected: blocking on the flock — serializes ~1-2 min
   builds behind one editor; per-project warm containers — more idle memory + lifecycle
   bookkeeping, and same-project builds still contend.)*
3. **Preview-style fingerprint gates reuse; staleness reboots.** Reuse is gated in ONE
   `docker inspect` on a fingerprint LABEL (§4.2). The pinned engine fact motivating this:
   **`MAP NEW`/`MAP LOAD` never purge the prior level's object pool** (spike
   `2026-06-19-read-surface-texture-package`, load-bearing in `qualify.export_and_qualify`'s
   unconditional stop-then-ensure), and the running GUI editor rewrites its ini from boot-time
   in-memory config (quirks.md, 🔬 2026-07-01) — so a package/Paths change on disk cannot be
   trusted to reach a running editor; whether `OBJ LOAD FILE=` on a resident package reloads it
   is UNPINNED (SP-E.3) and the fingerprint is conservative either way. In-place reuse resets per
   build with the existing `MAP NEW` + FULL re-import; the H3 post-verify backstops the built
   *content* (it cannot detect a stale resident package — that is precisely the fingerprint's
   job; §9). *(Rejected: config-only fingerprint — a re-synced texture or regenerated stub would
   silently build with the stale resident version; always-reboot-the-editor-process — forfeits
   the boot saving, which is the whole point.)*
4. **Callers: `level materialize` + `preview --game`'s internal materialize.** Both go through
   `apply.run_materialize`, so the warm acquire lives at that seam and both benefit. The `stash
   intersect`/`deintersect` CSG generators and the no-GUI UCC build containers (stub build,
   texture batchexport) are OUT of scope (follow-ups; §10).
5. **A warm-mode build failure FAILS the invocation — no automatic ephemeral retry** (Andrzej,
   review-gate ruling 22:18). The warm container is torn down (§4.3) and the command exits 2
   with an error that NAMES warm mode and notes a retry will boot fresh. *(Rejected: one
   automatic ephemeral retry — masks whether warm reuse is flaky and doubles the cost of every
   genuinely-bad build; retry-on-drive-errors-only — same masking for the wedge class.)*

## 3. What is NOT changing

- The build drive: full re-import in D-I order (`ensure_load` → `MAP NEW` → re-add → `MAP
  REBUILD`), `LIGHT APPLY`, `MAP SAVE`, H3 post-verify, atomic host swap — the `apply.py` /
  `materialize.py` flow, with exactly two additions: a dialog dismissal beside the existing
  `MAP NEW` and a scoped verify dump (§4.4).
- The ephemeral path (`ensure_editor`/`stop_editor`) — it remains, verbatim, as the fallback and
  is still what `stash intersect`/`deintersect` use.
- Overwrite/preflight guards, `--no-verify`, `--keep-build`.
- The warm **game** container (`uedctl-game-preview-<uid>`) — unrelated lifecycle, untouched.

## 4. The warm editor container

### 4.1 Identity, lock, volume, ini

- **One per Unix user:** `uedctl-editor-<uid>` (mirrors `uedctl-game-preview-<uid>`). Same image
  as the ephemeral editors (the uned service image).
- **WINEPREFIX volume: unique per BOOT**, `uedctl-editor-wp-<uid>-<nonce>` — never the compose
  default `wine-prefix` volume, and never reused across boots (a wedge/GPF may corrupt the
  prefix; a fresh volume is seeded clean from the image bake, parallel-editors.md). Every
  explicit teardown removes container AND volume; idle self-death can only stop the container
  (a container cannot remove its own volume), so **acquire runs an orphan sweep**: remove any
  `uedctl-editor-wp-<uid>-*` volume with no existing container attached. No volume leaks.
- **Per-user lock:** `flock` on `editor.lock` under the resolved per-user home
  (`config`'s user-home resolution — honors `$UEDCTL_HOME`, beside the preview's
  `game-preview.lock`), taken NONBLOCKING for the whole acquire-and-drive. Lock held by another
  process → **ephemeral fallback** for this invocation (decision 2). The flock serializes the
  warm container's users; it does not serialize materializes.
- **Crafted engine ini: per-user home, torn down with the container.** The RW single-file
  bind-mount source (`editor.engine_ini_mount`'s output) for the WARM container lives under the
  per-user `~/.uedctl/tmp/` (NOT a project's `<state_dir>/tmp/` — the container is per-user and
  outlives any one project's invocation; a project tree can be cleaned/deleted under an idle
  warm container). That path is daemon-visible (the stub-cache mount already binds from the same
  home). It is unlinked ONLY at warm-container teardown/reboot (which also covers replacing
  project A's ini when project B's fingerprint mismatch reboots), never by per-invocation
  cleanup.

### 4.2 Fingerprint (the ONE-inspect reuse gate)

A `uedctl.editor.fingerprint` LABEL stamped at container create; reuse requires an exact match
read back in ONE `docker inspect` (the same shape as `preview_game._fingerprint`):

- image id;
- the realpath-normalized mount pairs (the `/resources/<n>` set from
  `container_assets.resource_mounts(composed_search_dirs)`, plus the `/stubs` mount) — mounts are
  fixed at container create, so ANY dir-set change forces a reboot anyway; the crafted-ini
  content is a pure function of the mounts, so it needs no separate component;
- `(path, size, mtime)` stat tuples of the MUTABLE package inputs, defined precisely as:
  (a) every package file in the **project overlay** dirs (the project-side subset of
  `composed_search_files`), and (b) for every stem in the composed load set that resolves to a
  **v69 stub**, that stub file in the stub cache — NOT the whole (cross-project, shared) stub
  cache dir, so another project regenerating ITS stubs doesn't spuriously reboot this editor.
  Base-game package dirs are treated as immutable (the preview fingerprint's stance), so ~240
  base files aren't stat'd into the label. A stub regeneration or overlay package edit changes a
  tuple → mismatch → reboot.

Gate outcomes (complete):
- **Match + running + healthy** (§4.3) → touch the idle marker (host-side, IMMEDIATELY after the
  inspect and BEFORE the health probe — a ~9.5-min-idle container must not be watchdog-killed
  mid-acquire; the ordering the preview spec pinned as R3 MED-5) → reuse.
- **Match + running + unhealthy** → reboot (§4.3).
- **Stopped** (pinned or not — the pin marker lives in the container fs and there is nothing
  running to preserve) → remove container + volume, boot fresh.
- **Running + mismatch, not pinned** → remove container + volume, boot fresh (stamp the new
  label).
- **Running + mismatch + pinned** → **ephemeral fallback** (never clobber a pinned container).
  NOTE this deliberately DIVERGES from the preview gate, which errors loudly on pinned+mismatch:
  materialize must never refuse to build when a perfectly good ephemeral path exists. The cost —
  a stale pinned editor silently sends every materialize down the full ephemeral boot — is
  accepted and surfaced by the stderr mode line (§5). Pinning is not exposed as a materialize
  flag in v1 (§10); the marker check exists so a future pin surface (or a hand-touched
  `/work/.pinned`) is honored.

### 4.3 Health check, wedge recovery, failure policy

The editor wedges silently ("process alive, window gone" — quirks.md Stability). Before reuse:
`wine_ctl.py status` must report `alive=True` AND a resolved `window=<digits>` (the
`parallel-editors.md` readiness rule). Unhealthy → remove container + volume + fresh boot,
bounded to **ONE reboot attempt per invocation** — deliberately tighter than the preview's
`REBOOT_BUDGET=3: a second same-image boot failure here predicts an ephemeral boot (same image,
same boot path) would fail too, so retrying more just delays the named error. Both-boots-failed →
capture the tail of `docker logs`, REMOVE the failed container + volume (fail-closed — a
never-READY container must not linger; §4.5's marker-at-start is the belt to this suspender),
and exit 2 naming the container and embedding the captured log tail.

**Any warm-mode build failure tears the warm container down (container + volume + ini temp)
before the flock is released, and the invocation FAILS** (decision 5): after a
`DriverError`/timeout/verify-machinery crash the editor's state is untrusted, and leaving a
half-wedged editor warm just moves the failure to the next invocation. An H3 verify FAILURE with
a healthy drive gets the same teardown (cheap; a verify failure is rare enough that keeping the
editor warm for it optimizes the wrong case). The exit-2 message names warm mode and notes that
retrying will boot fresh — no automatic ephemeral retry.

Additionally, the first command of every REUSED build is preceded by a defensive
`Driver.dismiss_blocking_dialog()`: a previous invocation killed mid-drive (SIGKILL'd uedctl)
can leave a modal dialog up that the health probe cannot see (`alive` + `window` both look
fine), and dismissing is harmless when nothing is up.

### 4.4 Per-build reset (in-place reuse)

There is NO extra reset step: the existing `materialize.materialize()` sequence — `ensure_load`
→ **`MAP NEW`** → re-add (full re-import) → `MAP REBUILD` — already resets the level per build
(its `MAP NEW` is the reset; review finding: an added leading `MAP NEW` would run the GC pass
twice). Two production changes ride this spec:

1. **Dialog dismissal at `MAP NEW`:** `MAP NEW`/`IMPORTADD`/`REBUILD` fire the GC pass whose
   "Cleaning up..." `xmessage` dialog blocks the console under headless SoftDrv (quirks.md).
   `driver.map_new()` gains a `dismiss_blocking_dialog()` (defensive on the ephemeral path,
   load-bearing on the warm path where resident packages make the GC pass likelier — SP-E.4
   pins that repeated MAP NEW + dismissal is stable across N builds).
2. **The H3 verify's live qualification dump is SCOPED to the current build's package set.**
   `verify_dx_matches(qualify_driver=ed)` re-derives bare `Texture=`/class qualifiers from the
   live editor's `OBJ DEPENDENCIES` dump — and the object pool is never purged across
   `MAP NEW` (§2.3's pinned fact), so in a REUSED editor that dump can carry build-N−1's
   packages; a bare name colliding across builds could mis-qualify (false FAIL, or worse, a
   consistent false PASS). The qualification therefore filters its dump to the packages of the
   CURRENT build (the level's referenced set + its transitive closure). SP-E.7 exercises the
   colliding-name case live.

Per-build hygiene: each build's `/work` temps (import T3Ds, save/export files) are removed at
build end (the `xfer.remove` pattern `apply.py` already applies to the save temp, extended to
all of that build's temps) — ephemeral death used to reclaim these; warm reuse must not let
them accumulate. `Editor.log` growth and editor RSS across N builds are SP-E.6's input to the
§4.6 cap.

### 4.5 Idle self-death

Same *pattern* as the preview container (decisions 2026-07-17) with editor-specific placement:

- The watchdog is an INLINE loop in `uned/entrypoint.sh` as tini's direct child, keyed on the
  `/work/.last_use` mtime, self-terminating the container after **10 min idle**. Because that
  entrypoint is SHARED (ephemeral editors, the standing `dx-lum-uned`, and as base of the game
  image), the watchdog is **env-gated — `UED_IDLE_S`, default 0 = disabled** — and ONLY the warm
  boot passes it. Ephemeral editors and the standing container are behaviorally untouched.
- **Marker refreshes:** the entrypoint touches `/work/.last_use` at container START (so a boot
  that GPFs before READY still self-dies — the entrypoint has no relaunch-exhausted exit path),
  and **`wine_ctl.py` touches it on EVERY invocation** — every host-side `Driver` exec routes
  through `wine_ctl`, so the whole drive (import, rebuild polls, light, save, verify) refreshes
  the marker continuously, exactly as the preview's in-container `preview_batch._mark()` does.
  A long build can never be idle-killed mid-drive; the only way the deadline lapses mid-build is
  a single exec blocked >10 min — a wedge, where self-death is the desired outcome (the host
  side has long since surfaced its own DriverError/timeout).
- A `/work/.pinned` marker disables self-death (honored, not exposed — §4.2).
- **Image rebuild required:** the watchdog + marker touches live in baked files
  (`entrypoint.sh`, `wine_ctl.py`), and quirks.md's stale-image trap applies — a warm boot on a
  stale image silently has NO watchdog (an immortal ~0.5 GB leak). The build sequences a
  `docker compose build`; the boot function asserts the label/env made it in (fail-closed).

### 4.6 Memory + build-count cap

A warm editor idles at ~0.5 GB RSS and spikes during `MAP REBUILD` (parallel-editors.md). One
per user is the accepted cost (same bar the warm game container passed). UnrealEd is not trusted
to survive unbounded rebuilds in one process: SP-E.6 measures RSS + `Editor.log`/overlay growth
across repeated warm builds, and IF anything drifts, a **builds-per-container cap** (reboot
after N acquired builds, N from the spike data) is the mitigation — decided by the spike, not
guessed here.

## 5. Code shape (build items)

- **Generalize, don't fork, the warm-container gate.** `preview_game.acquire_warm_container`'s
  flock + ONE-inspect fingerprint + reboot-retry pattern is factored into a shared helper (e.g.
  `warm.py`) parameterized by container name, lock path, fingerprint components, boot function,
  and health probe — used by BOTH the game-preview container and the new `acquire_warm_editor`.
  If the factoring fights the preview code's shape, the fallback is a sibling implementation in
  `editor.py` mirroring the pattern — the spec mandates the behavior, not the refactor.
- **Image-side:** `uned/entrypoint.sh` — env-gated idle watchdog + marker-at-start;
  `wine_ctl.py` — marker touch per invocation; `docker compose build` sequenced into the build.
- **Boot-side:** a warm-boot path beside `ensure_editor` that stamps the fingerprint LABEL,
  passes `UED_IDLE_S`, mints the per-boot volume name, writes the crafted ini under the per-user
  home, and runs the orphan-volume sweep.
- **Drive-side:** `driver.map_new()` gains the dismissal; the reused-build defensive dismissal;
  H3 qualification-dump scoping (`verify.py`/`qualify.py` seam); per-build `/work` cleanup.
- `apply.run_materialize` swaps its `ensure_editor`/`stop_editor` bracket for:
  `acquire_warm_editor(...)` → on success, drive + release (container persists; teardown only on
  failure per §4.3); on busy/pinned-mismatch → today's ephemeral bracket verbatim. The returned
  handle says which mode was taken so the `finally` knows whether to `stop_editor`.
- `preview_game.materialized_dx` inherits the behavior for free (it calls `run_materialize`).
- Human-facing note to stderr on each materialize: which path was taken (`warm reuse` / `warm
  boot` / `ephemeral fallback (busy)` / `ephemeral fallback (pinned)`) — one line, stderr only
  (pipe-clean stdout).

## 6. Errors (named exit-2, never a traceback)

- Warm boot fails twice → remove the failed container + volume, exit 2 naming the container +
  the captured `docker logs` tail (§4.3).
- Warm-mode build failure → teardown + exit 2, message names warm mode + "a retry boots fresh"
  (decision 5).
- Lock contention / pinned mismatch → NOT an error (silent fallback; the stderr mode line says
  so).
- Everything the ephemeral path already names (EditorBusyError, DriverError, ini-write OSError…)
  is unchanged.

## 7. Tests

Offline (mocked docker/driver, like the warm-preview suite):
- fingerprint: tuple change (overlay mtime / composed-set stub file / mount pair / image id) →
  reboot; exact match → reuse; an OUT-of-composed-set stub-cache change → NO reboot (the §4.2
  scoping); stopped (pinned or not) → reboot; running+mismatch+pinned → ephemeral fallback,
  container untouched.
- acquire ordering: inspect → marker touch → health probe (assert marker precedes probe).
- lock held → ephemeral fallback (and `stop_editor` called on that path; NOT called on the warm
  success path).
- health probe fail → one reboot attempt → second fail → container+volume removed + named exit 2.
- warm-mode drive error AND H3 failure → container + volume + ini temp removed before lock
  release; exit 2 message carries the warm-mode hint; no auto-retry occurred.
- volume lifecycle: per-boot unique name; orphan sweep removes unattached `uedctl-editor-wp-*`
  volumes only.
- watchdog gating: ephemeral boot and standing-container config pass NO `UED_IDLE_S` (assert
  absent); warm boot passes it.
- drive sequence on the mocked driver: `ensure_load` → ONE `map_new` (with dismissal) → re-add →
  rebuild; reused-build defensive dismissal precedes the first command.
- verify-dump scoping: a dump entry from a non-current package does not qualify a bare ref.
Integration (live, `-m integration`): one warm double-build (§8 SP-E.1 doubles as the seed), a
concurrent-invocation fallback exercise, and a live idle self-death check (backdated marker →
self-terminates; the preview spec live-verified its equivalent).

## 8. Spike SP-E (BLOCKING build) — reused-editor cleanliness + numbers

The whole design assumes a REUSED editor builds as cleanly as a fresh one. That is exactly the
kind of undocumented-editor fact the repo rules say must be live-verified and pinned, not
assumed. One spike, `spikes/2026-07-18-warm-editor-materialize/`, answers:

1. **Same-trunk double build:** materialize the castle trunk twice in one warm editor. Both H3
   verifies green; artifact 2 additionally compared against a FRESH-editor build of the same
   trunk through the existing verify oracle (GUID/timestamp-class fields aside). Any drift =
   resident-state contamination = design falsified (→ always-reboot fallback stance).
2. **Cross-level build:** level A then level B (disjoint package refs) warm; B's H3 + qualify
   green; B's import table carries no A-only residue.
3. **`OBJ LOAD FILE=` on an already-resident package:** no-op, error, or reload-from-disk? Pins
   whether `ensure_load` can run unchanged (expected: harmless no-op) or needs a resident-set
   skip — and lands the resident-reload fact in `unrealed/quirks.md` with a confidence marker.
4. **Repeated `MAP NEW` stability:** N (≥5) consecutive warm builds; GC-dialog dismissal holds
   every round; no console lockup.
5. **Timing split:** cold ephemeral end-to-end vs (boot portion / drive portion) vs warm
   end-to-end, on the castle trunk — the acceptance number for §1 — plus the worst-case single
   `MAP REBUILD`/`LIGHT APPLY` duration vs the 10-min idle deadline (sanity for §4.5).
6. **RSS + `Editor.log`/overlay growth across N warm builds** → decides the §4.6 cap.
7. **Colliding-bare-name qualification:** build with package P1 owning bare name X, then a build
   whose X must resolve to P2, in one warm editor — the scoped dump (§4.4.2) qualifies correctly
   in BOTH the verify direction and the import-time binding direction.

Findings fold back into THIS spec + `unrealed/quirks.md` (dated, with confidence markers); any
standing checkable fact gets a committed regression per the "pin the finding" rule.

### SP-E RESULTS (ran 2026-07-19 — `spikes/2026-07-18-warm-editor-materialize/results.md`)

**BLOCKER (falsifies the §8 premise): reused builds fail intermittently (~50%) at the H3 verify
boundary.** Driving one warm editor through many `run_materialize` builds (lifecycle seams
monkeypatched, real drive), the pattern is `1✓ 2✗ 3✗ 4✓ 5✗ 6✓` and the diagnostic reproduced 2/4.
Decisive isolation: **`no_verify` reuse is 0/4 (clean, correct byte-identical artifacts)**; **any
verify-against-the-warm-editor is 2/4 (broken)**; **isolating ONLY the UCC batchexport to a separate
container is still 2/4**. So the drive + `MAP SAVE` are reliable on reuse — the disruptor is the H3
verify's interaction with the warm editor (its live `OBJ DEPENDENCIES` qualify dump / the editor
being mid-verify) racing the *next* build's fire-and-forget drive, which then silently loses its
`MAP SAVE` (UCC: "Can't find file"). It is NOT the GC dialog (§4.3's dismissal is fine but irrelevant
to this) and NOT the second `wine` process. **This means §4.4's "H3 verify against the same live
editor" (D-Q3, inherited from the ephemeral path) is exactly what must change for warm reuse.**

**Fix candidates (Andrzej's design call — flagged in `board/inbox.md`), cheapest first:**
1. **A robust editor-quiesce / CPU-idle barrier** after each build's verify (the 1.5 s settle tried
   was too weak; use a real idle barrier like the §89 golden harness) so the next build never races
   a still-busy editor. Keeps verify in the warm editor → preserves the full ~16 s saving. **Try
   first.**
2. **Run the whole H3 verify (export AND qualify) against a SEPARATE throwaway editor** — the
   `qualify.export_and_qualify` pattern. Isolating only the UCC export was tried and is insufficient
   (the qualify dump must move too). **Caveat:** a separate *cold* verify editor per build costs a
   ~15 s boot ≈ the entire warm saving — it would itself need warm-pooling to net ahead.

Either way **re-run SP-E to confirm 0/N before shipping**; the build is not green-lit as specced.

**Answered:**
- **SP-E.5 timing (✅ live):** drive alone ~16 s; **H3 verify ~42 s (bigger than boot)**; warm boot
  ~15 s; teardown ~0.4 s; cold end-to-end ~79 s; **warm reuse saving ≈ boot+teardown ≈ 16 s/build
  (~20%)**. The ~58 s drive+verify dominates and is per-build regardless (matches §1). Note the
  verify cost re: fix candidate 2.
- **SP-E.6 RSS/log (✅ live):** RSS 85→181 MB on build 1 (the package `OBJ LOAD`s) then **flat
  ~181–184 MB across builds 2–6** — no unbounded growth; **no RSS-driven §4.6 reboot cap needed**
  within ≥6 builds. `Editor.log` grows ~360 KB/build (monotonic; minor housekeeping, not memory).
- **SP-E.3 resident `OBJ LOAD` (✅ live):** re-issuing `OBJ LOAD FILE=` on an already-resident
  package is neither a hard no-op nor an error — a re-read (~1.3 s each, writes to log, 0 errors in
  21 calls). `ensure_load` runs unchanged and safely on the warm path; a resident-set skip is a
  valid optimization (~4 s/build for 3 packages), not required. Lands in `quirks.md`.
- **SP-E.1 content (✅ live):** the genuinely-reused *successful* builds — builds 4 AND 6, run after
  prior builds populated the object pool — are `canonical_level_hash`-identical to a fresh cold build
  (`cold == warm1 == warm4 == warm6 == ad9ba84e…`). Reuse does NOT corrupt content when a build
  succeeds. (Raw bytes differ ~350 KB from object-table renumbering; canonical export is the oracle.)
- **SP-E.4 (✅ the negative):** `MAP NEW`/GC-dialog is stable and NOT the instability source.

**A possible POSITIVE, and a deferral (honest):**
- **SP-E.2 cross-level (🔬 inconclusive — possible real residue):** anchor(UNATCO)-after-castle failed
  with a **content** `post-verify mismatch` on actor `Bounce_…` (30.9 s; `MAP SAVE` succeeded, a
  *different* signature from the blocker) — and **`Bounce_…` is a CASTLE actor, not an anchor actor**,
  i.e. a castle actor leaked into the anchor build's verify: exactly the stale-pool residue SP-E.2
  targets. But it ran in a flaky editor (followed a *failed* build), so it could instead be the
  bare-vs-qualified qualify artifact or `MAP NEW` not fully clearing — **not nothing, but not
  trustworthy** until re-tested after the blocker fix. This is direct motivation to keep §4.4.2's
  scoped dump (and/or a stronger per-build reset).
- **SP-E.7 colliding-bare-name:** not reached — needs the blocker fixed (trustworthy successive
  builds) + a two-package colliding fixture that doesn't exist yet. Re-scope with SP-E.2 (same
  live-qualify-across-builds seam).

## 9. Risks / watch-list

- **`(path,size,mtime)` blind spot** (inherited from the preview fingerprint, worth restating
  here because the output is a durable artifact, not a throwaway frame): a same-size,
  mtime-preserving package/stub edit is missed → a silently stale build. Escape hatch:
  `docker rm -f uedctl-editor-<uid>`.
- **H3 verify is a CONTENT backstop only** — it compares the built map to the intended trunk
  actors; it cannot detect a stale resident package (same names, old bytes). Package freshness
  is solely the fingerprint's job.
- **A stale pinned editor** silently degrades every materialize to ephemeral-boot speed (the
  accepted §4.2 divergence); the stderr mode line is the tell.

## 10. Out of scope / follow-ups

- **`EXEC <file>` batch driving** (spike PROVEN 2026-07-18,
  `spikes/2026-07-18-exec-file-console-batch/`; adoption item in `board/inbox.md`): batching the
  write-only drive commands into one command-script submission composes with — and does not
  block — this spec; it cuts per-build drive overhead ~6× and rides through the GC dialog on
  both the warm and ephemeral paths. The completion poll still refreshes the §4.5 idle marker
  via `wine_ctl`.
- `--editor`/`--native` flag split on materialize (the native-default cutover owns it).
- `stash intersect`/`deintersect` adopting the warm editor (same seam, separate item).
- Warming the no-GUI UCC build containers (stub build, texture batchexport) — different
  image/lifecycle; separate item if ever wanted.
- A user-facing pin (`--keep-alive` analogue) for the editor container.
- In-place re-farm/reload of changed packages without a reboot (the fingerprint reboot is the
  v1 answer, as it is for preview).
