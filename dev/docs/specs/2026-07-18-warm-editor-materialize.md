# Warm editor container for `level materialize` (design spec)

**Status:** specced 2026-07-18; design-gated 2026-07-18. **Blocking spike SP-E ran 2026-07-19 and
falsified the original drive+verify design** (`spikes/2026-07-18-warm-editor-materialize/results.md`).
**REVISED 2026-07-26** to resolve that blocker: the H3 post-verify moves OFF the build editor
entirely, into a one-shot headless commandlet container.

> ## ⛔ PARKED — this revision DID NOT PASS its spec review (2026-07-26)
>
> Three cold reviewers returned ~50 findings with heavy independent convergence. **The premise
> survived**: a one-shot commandlet structurally satisfies the "fresh editor, exactly one level
> loaded" precondition `commands.md` states for `OBJ DEPENDENCIES`, which warm reuse cannot meet.
> **The mechanisms did not.** Do not build from this document. The findings are logged in full on
> `board/inbox.md` ("SPEC REVIEW ROUND 1"); the headlines:
>
> - The verify container is specified two mutually exclusive ways (`docker exec` into a container
>   that has exited), boots the full GUI stack (the image `ENTRYPOINT` ignores its args and
>   `LAUNCH_UED` defaults to 1 outside compose), and loses the `/stubs` mount that its own crafted
>   ini puts first on `Paths` — the last of which is a deterministic exit 2 on correct builds.
> - Both dumps share one undelimited stdout stream, re-creating the exact contamination
>   `qualify._blocks_only` exists to prevent.
> - The single engine fact decision 6 rests on is **not reproducible from any committed harness**.
> - The idle watchdog's deadline equals `map_save`'s own 600 s bound and the marker is not refreshed
>   by its poll loop, so it can kill a healthy build — on the ephemeral **default** path.
> - Two further `direction/` conflicts are taken silently (the §4.3 one was parked correctly).
> - SP-F's acceptance criterion is both unreachable (two known pre-existing verify false positives)
>   and insufficient (it cannot see a runt/unlit map, which the compare structurally ignores).
>
> **Next step is a spike, not a spec revision.** Roughly half the findings are questions that should
> be answered empirically — what the commandlet actually does with `OBJ LOAD`/`MAP LOAD`/
> `OBJ DEPENDENCIES`/`OBJ LIST`, in what stdout format, under which entrypoint and mounts, at what
> cost — rather than inferred and then reviewed. Re-spec on measured facts; per CLAUDE.md
> "Review gates" the artifact then re-enters at round 1.

**What changed on 2026-07-26, in one paragraph.** SP-E proved the *design*'s premise false: reused
builds fail ~50% of the time, and the decisive isolation showed the disruptor is the H3 post-verify
running against the warm editor. The two fixes on the table both had a bad price — an idle barrier
that only works if the cause is a race (never discriminated), or a separate *GUI* verify editor whose
~15 s boot eats the entire ~16 s warm saving. A spike run on 2026-07-26
(`spikes/headless-materialize/findings.md`) removed that trade: `UCC.exe Editor.ExecCommandlet` runs
the full editor engine with **no GUI, no window and no X server**, executes a file of ordinary console
verbs, prints its whole log to **stdout**, and **exits by itself** in ~1.4–3.7 s. That makes "verify in
a separate, genuinely fresh editor" cost ~3 s instead of ~15 s — so the robust fix is now also the
cheap one. It additionally deletes the qualify path's two log-scraping poll loops, and it satisfies a
precondition `commands.md` already documents for `OBJ DEPENDENCIES` that a reused editor structurally
cannot meet.

---

## 1. Problem / motivation

Three costs, not one. The 2026-07-18 spec named only the first.

**(a) Every build pays a full editor boot.** `level materialize` (`apply.run_materialize`) mints a
fresh per-command container (`uned-<uuid7>`): `docker compose run` + a fresh WINEPREFIX volume
(seeded from the image bake) + Xvfb/wine/UnrealEd launch + window-ready poll + per-package
`OBJ LOAD`s — then tears it all down (`stop_editor`, container + volume). `level preview --game`
pays the same cost indirectly: it calls `run_materialize` whenever the trunk changed (its delivered-map
cache is trunk-hash-keyed via `preview_game.materialized_dx`).

**(b) The post-verify costs more than the boot.** SP-E.5 measured the split on the 161-actor castle
trunk: cold end-to-end **79 s** = boot 15 + drive ~16 + **verify ~42** + teardown 0.4 + ~5 s
`docker compose run` overhead. The verify is the single largest term and the 2026-07-18 spec left it
untouched, so that spec's ceiling was a **20 %** improvement.

**(c) Ephemeral editors LEAK, and the leak is structural.** Teardown lives only in
`run_materialize`'s `finally`. Python's default SIGTERM disposition terminates the process without
unwinding, so `finally` never runs — and `timeout <n> bin/uedcli level materialize …` (SIGTERM) is a
routine invocation shape in this repo, as are harness and agent-session job kills. There is no
`--rm` (the editor is detached), no in-container watchdog, and no startup sweep, so a killed or
wedged run **always** strands a running `unrealed.exe` plus a ~0.5 GB wineprefix volume. Observed on
this host 2026-07-26: **8 stranded `uned-*` containers** (6 running, 2 never-started) accumulated over
~4 hours, and **9 orphan `uned-wp-*` volumes ≈ 5.5 GB**. Independently reproduced by
`spikes/headless-materialize/findings.md` §1 (a second `--no-verify` run wedged past 600 s and
stranded its container) and logged in `spikes/levelbuild-friction/README.md` §2.

This spec addresses all three: (a) with the warm container, (b) by moving the verify to a one-shot
commandlet container, (c) with an idle watchdog on **every** editor container plus an orphan-volume
sweep.

**Projected effect** (from SP-E.5's terms; the ~42 s verify is SP-E's *derived* figure — §9 SP-F.4
times it directly):

| Path | today | with commandlet verify | + warm reuse |
|-------------------|-------|------------------------|---
| warm reuse        | —     | —                      | **~20 s**
| ephemeral (fallback / contention) | 79 s | **~40 s** | —

The verify move is the larger lever **and it lands on the ephemeral path too**, which is why it is
not deferred behind the warm container.

## 2. Decisions

Owner decisions 1–5 are from 2026-07-18 (21:52 + 22:18 UTC) and stand unchanged. 6–8 are from
2026-07-26 and are **parked for confirmation** on `board/inbox.md` as `[OWNER — confirm]` items
carrying their proposed `direction/` wording; this spec builds on them, `direction/materialize.md` is
not edited until they are confirmed.

1. **Warm the current path; no new flag.** `level materialize` today IS the editor build; this spec
   warms that path as default behavior, with no CLI surface change. The `--editor` flag *name*
   arrives later, with the native-default cutover — this AMENDS the 2026-07-14 "editor ditched
   entirely" stance: the editor build path SURVIVES that cutover behind `--editor`, with this warm
   machinery carrying over. *(Rejected: introducing `--editor`/`--native` on materialize now — that
   flag split is the cutover's scope.)*
2. **Busy or pinned-mismatched → fall back to per-command ephemeral.** The warm container is a fast
   path, never a bottleneck: acquisition takes a NONBLOCKING per-user flock, and any contention
   (lock held) or a pinned container with a different fingerprint sends THIS invocation down the
   ephemeral `ensure_editor`/`stop_editor` path. Parallel materializes still compose. *(Rejected:
   blocking on the flock — serialises multi-minute builds machine-wide; per-project warm containers —
   more idle memory and bookkeeping, and same-project builds still contend.)*
3. **Preview-style fingerprint gates reuse; staleness reboots.** Reuse is gated in ONE
   `docker inspect` on a fingerprint LABEL (§4.2). The pinned engine fact behind it: **`MAP NEW`/`MAP
   LOAD` never purge the prior level's object pool** (spike `2026-06-19-read-surface-texture-package`)
   and the running GUI editor rewrites its ini from boot-time in-memory config (`quirks.md`, 🔬
   2026-07-01) — so a package/Paths change on disk cannot be trusted to reach a running editor.
   *(Rejected: a config-only fingerprint — a re-synced texture or regenerated stub would silently
   build stale; always-reboot — forfeits the boot saving.)*
4. **Callers: `level materialize` + `preview --game`'s internal materialize.** Both go through
   `apply.run_materialize`, so the warm acquire lives at that seam. The `stash intersect`/`deintersect`
   CSG generators and the no-GUI UCC build containers are OUT of scope (§11).
5. **A warm-mode build failure FAILS the invocation — no automatic ephemeral retry.** The warm
   container is torn down (§4.3) and the command exits 2 with an error NAMING warm mode and noting
   that a retry boots fresh. *(Rejected: one automatic ephemeral retry — masks whether warm reuse is
   flaky and doubles the cost of a genuinely bad build.)*
6. **The H3 post-verify NEVER runs against the build editor. It runs in a one-shot headless
   commandlet container** (`UCC.exe Editor.ExecCommandlet`, `docker run --rm`, self-exiting), for
   **both** the warm and the ephemeral path. This is the SP-E blocker's fix and it is not conditional
   on warm mode. *(Rejected: an editor-quiesce/CPU-idle barrier — it only works if the cause is a
   transient race, which SP-E explicitly did not discriminate, and the 1.5 s settle it did try leaned
   against; a separate cold GUI verify editor — robust but its ~15 s boot ≈ the entire warm saving;
   `--no-verify` as the warm-mode default — trading build correctness for speed on the one path whose
   job is detecting wrongness.)*
7. **Warm editor now; the native and commandlet BUILD backends are separate, later work.**
   `spikes/headless-materialize/findings.md` ranks `level materialize --native` first overall; that
   is not this spec. The commandlet is adopted here **only as a verify/oracle host**, where its three
   gaps (no lighting, no movers, brush names reassigned) do not apply. *(Rejected for now: re-scoping
   this work to `materialize --native` — a bigger, different change with an open byte-parity front;
   promoting the commandlet to a build backend — it cannot produce a lit map, see §5.4.)*
8. **The idle watchdog covers EVERY editor container, not only the warm one.** The 2026-07-18 spec
   gated it warm-only ("ephemeral editors untouched"); §1(c) is why that is wrong — the ephemeral
   editor is exactly what leaks today, and no host-side `finally` can fix a SIGTERM'd process.
   *(Rejected: host-side signal handlers alone — they cannot cover SIGKILL, and a container whose
   parent died must be able to reap itself; an age-based startup sweep as the primary mechanism —
   unsafe, because a legitimate build can outlive any age threshold, and 2 live builds were in flight
   among the 6 stranded containers observed.)*

## 3. What is NOT changing

- The build drive: full re-import in D-I order (`ensure_load` → `MAP NEW` → re-add → `MAP REBUILD`),
  `LIGHT APPLY`, `MAP SAVE`, atomic host swap.
- **What the verify COMPARES.** `compare_view` over typed effective values, `_first_diff`, the
  `defaults` requirement with no zero fallback — untouched. Only *where the inputs are produced*
  moves. `qualify.py`'s parsers (`parse_obj_dependencies`, `parse_loaded_classes`,
  `qualify_level_textures`, `qualify_level_classes`, `requalify_classes_to_loaded`) are reused
  **verbatim** — they already take text.
- The ephemeral path (`ensure_editor`/`stop_editor`) — it remains as the fallback and is still what
  `stash intersect`/`deintersect` use.
- Overwrite/preflight guards, `--no-verify`, `--keep-build`.
- The warm **game** container (`uedcli-game-preview-<uid>`) — unrelated lifecycle, untouched.
- `dev/docs/direction/` — not edited by this work; decisions 6–8 are parked for confirmation (§2).

## 4. The warm editor container

### 4.1 Identity, lock, volume, ini

- **One per Unix user:** `uedcli-editor-<uid>` (mirrors `uedcli-game-preview-<uid>`), same image as
  the ephemeral editors.
- **WINEPREFIX volume: unique per BOOT**, `uedcli-editor-wp-<uid>-<nonce>` — never the compose
  default `wine-prefix`, and never reused across boots (a wedge/GPF may corrupt the prefix; a fresh
  volume seeds clean from the image bake — `parallel-editors.md`). Every explicit teardown removes
  container AND volume; idle self-death can only stop the container, so **acquire runs an orphan
  sweep** (§4.5).
- **Per-user lock:** `flock` on `editor.lock` under the resolved per-user home (honors `$UEDCLI_HOME`,
  beside the preview's `game-preview.lock`), taken NONBLOCKING for the whole acquire-and-drive. Lock
  held → ephemeral fallback for this invocation (decision 2).
- **Crafted engine ini: per-user home, torn down with the container.** The RW single-file bind-mount
  source (`editor.engine_ini_mount`'s output) for the WARM container lives under the per-user
  `~/.uedcli/tmp/`, NOT a project's `<state_dir>/tmp/` — the container is per-user and outlives any
  one project's invocation, and a project tree can be deleted under an idle warm container. That path
  is daemon-visible (the stub-cache mount already binds from the same home; `parallel-editors.md`'s
  bind-source trap). Unlinked ONLY at teardown/reboot.

### 4.2 Fingerprint (the ONE-inspect reuse gate)

A `uedcli.editor.fingerprint` LABEL stamped at container create; reuse requires an exact match read
back in ONE `docker inspect` (same shape as `preview_game._fingerprint`):

- image id;
- the realpath-normalized mount pairs (the `/resources/<n>` set from
  `container_assets.resource_mounts(composed_search_dirs)` plus the `/stubs` mount) — mounts are
  fixed at container create, so any dir-set change forces a reboot anyway; the crafted ini is a pure
  function of the mounts, so it needs no separate component;
- `(path, size, mtime)` stat tuples of the MUTABLE package inputs: (a) every package file in the
  **project overlay** dirs, and (b) for every stem in the composed load set resolving to a **v69
  stub**, that stub file — NOT the whole shared stub cache, so another project regenerating ITS stubs
  does not spuriously reboot this editor. Base-game dirs are treated as immutable (the preview
  fingerprint's stance).

Gate outcomes (complete):
- **Match + running + healthy** (§4.3) → touch the idle marker (host-side, IMMEDIATELY after the
  inspect and BEFORE the health probe — a ~9.5-min-idle container must not be watchdog-killed
  mid-acquire) → reuse.
- **Match + running + unhealthy** → reboot (§4.3).
- **Stopped** (pinned or not) → remove container + volume, boot fresh.
- **Running + mismatch, not pinned** → remove container + volume, boot fresh.
- **Running + mismatch + pinned** → **ephemeral fallback**, container untouched. This deliberately
  DIVERGES from the preview gate, which errors loudly: materialize must never refuse to build when a
  working ephemeral path exists. The cost — a stale pinned editor silently sends every materialize
  down the full ephemeral boot — is accepted and surfaced by the stderr mode line (§6).

### 4.3 Health check, wedge recovery, failure policy

The editor wedges silently ("process alive, window gone" — `quirks.md` Stability). Before reuse:
`wine_ctl.py status` must report `alive=True` AND a resolved `window=<digits>` (`parallel-editors.md`
readiness rule — a bare `window=` substring is the documented false-ready trap). Unhealthy → remove
container + volume + fresh boot, bounded to **ONE reboot attempt per invocation** (tighter than the
preview's 3: a second same-image boot failure predicts the ephemeral boot would fail too).
Both-boots-failed → capture the `docker logs` tail, REMOVE the failed container + volume, exit 2
naming the container and embedding the tail.

**A warm-mode DRIVE failure tears the warm container down** (container + volume + ini temp) before
the flock is released, and the invocation FAILS (decision 5): after a `DriverError`/timeout the
editor's state is untrusted.

**A verify FAILURE does NOT tear the editor down — PROPOSED, and it CONTRADICTS a direction doc, so
it is parked, not decided.** `direction/containers.md` currently states: *"a warm-mode drive **or
verify** failure tears it down before releasing the lock."* That rule was written when the verify ran
against the warm editor, where a verify failure genuinely did implicate editor state. Decision 6
removes that coupling: the verify now runs in its own container, so a verify failure says nothing
about editor health — it says the *build* was wrong — and tearing the editor down would discard a
healthy warm editor on exactly the occasion the operator is about to re-materialize.

**Until the owner rules, the BUILD follows `direction/containers.md` and tears down on a verify
failure too.** The proposed change is parked as an `[OWNER — confirm]` item on `board/inbox.md`. Under
either answer the invocation still exits 2 with the mismatch diagnostic, `--keep-build` still
preserves the rejected map, and decision 5 (no automatic ephemeral retry) is unchanged.

The first command of every REUSED build is preceded by a defensive
`Driver.dismiss_blocking_dialog()`: a previous invocation killed mid-drive can leave a modal dialog
up that the health probe cannot see, and dismissing is harmless when nothing is up. SP-E.4 showed
this is *not* what makes reuse reliable — it is retained as cheap insurance, not as a fix.

### 4.4 Per-build reset (in-place reuse)

There is NO extra reset step: the existing `materialize.materialize()` sequence — `ensure_load` →
**`MAP NEW`** → re-add → `MAP REBUILD` — already resets the level per build. One production change
rides this spec: **dialog dismissal at `MAP NEW`** (`driver.map_new()` gains
`dismiss_blocking_dialog()`), because `MAP NEW`/`IMPORTADD`/`REBUILD` fire the GC pass whose
"Cleaning up…" `xmessage` never auto-closes headless and blocks the Command-box input path
(`quirks.md`).

**DELETED from the 2026-07-18 spec: the scoped qualify dump (old §4.4.2).** That section existed to
stop a reused editor's un-purged object pool from contaminating the verify's live `OBJ DEPENDENCIES`
dump. Decision 6 removes the cause: the dump now runs in a container whose editor has existed for
~1.3 s and has loaded exactly one level. This also structurally addresses SP-E.2's possible cross-level
residue (a castle actor appearing in an anchor build's verify) and makes SP-E.7 (colliding bare names
across successive builds in one editor) moot for the verify direction. **It does not make them moot for
the IMPORT-TIME binding direction** — that still happens in the warm editor — which is why SP-F.3
re-tests the cross-level case rather than declaring it closed.

Per-build hygiene: each build's `/work` temps are removed at build end (the `xfer.remove` pattern
`apply.py` already applies to the save temp, extended to all of that build's temps) — ephemeral death
used to reclaim these.

### 4.5 Idle self-death, and the leak fix

Same *pattern* as the preview container, with two placements the 2026-07-18 spec got wrong.

- The watchdog is an INLINE loop in `uned/entrypoint.sh` as **tini's direct child** — a backgrounded
  `&` watchdog is not tini's child, so its exit stops nothing and `kill 1` is a no-op (the game
  entrypoint records this trap). Keyed on `/work/.last_use` mtime, self-terminating after **10 min
  idle**.
- **It is env-gated (`UED_IDLE_S`, default 0 = disabled) and passed by BOTH the warm boot AND the
  ephemeral `ensure_editor` boot** (decision 8). The standing `dx-lum-uned` container and any
  hand-run `docker compose run` still get no watchdog (default 0), so interactive debugging is
  untouched. This is the mechanism that fixes §1(c): a container whose parent process was SIGKILLed
  reaps itself 10 minutes later, with no host-side cooperation required.
- **Marker refreshes:** the entrypoint touches `/work/.last_use` at container START (so a boot that
  GPFs before READY still self-dies), and **`wine_ctl.py` touches it on EVERY invocation** — every
  host-side `Driver` exec routes through `wine_ctl`, so the whole drive refreshes it continuously. A
  long build can never be idle-killed mid-drive; the only way the deadline lapses mid-build is a
  single exec blocked >10 min, which is a wedge, where self-death is the desired outcome. SP-E.5
  confirmed the worst single editor op is far under 10 min.
- A `/work/.pinned` marker disables self-death (honored, not exposed — §4.2).
- **Orphan-volume sweep, covering BOTH naming schemes.** A self-died container cannot remove its own
  volume, so `acquire` sweeps volumes with no attached container: `uedcli-editor-wp-<uid>-*` (warm)
  **and `uned-wp-*` (ephemeral)**. The ephemeral half is what reclaims the ~5.5 GB already stranded on
  this host. The sweep keys on *no attached container*, never on age — §1(c) observed two legitimate
  multi-minute builds in flight among the stranded set, and an age threshold would have killed them.
- **Image rebuild required:** the watchdog and marker touches live in baked files (`entrypoint.sh`,
  `wine_ctl.py`), and `quirks.md`'s stale-image trap applies — a boot on a stale image silently has
  NO watchdog, i.e. the leak persists invisibly. The build sequences a `docker compose build`, and
  the boot path **asserts the env made it in (fail-closed)** rather than trusting it.

### 4.6 Memory + build-count cap

A warm editor idles at ~0.5 GB RSS and spikes during `MAP REBUILD` (`parallel-editors.md`). SP-E.6
measured RSS 85 → 181 MB on build 1 (the package `OBJ LOAD`s) then **flat ~181–184 MB across builds
2–6** — no unbounded growth, so **no reboot cap ships in v1**. SP-E.6's own caveat stands: three of
those six builds were ~17 s failures, so the soak is really ~3 full builds. SP-F.5 re-runs it as a
clean ≥6-build successful soak; a builds-per-container cap ships only if that shows drift.
`Editor.log` grows ~360 KB per full build (monotonic; housekeeping, not memory).

## 5. The verify container (the SP-E blocker's fix)

### 5.1 What moves, and what it replaces

Today `verify_dx_matches` does four things, three of which need an editor:

1. `export_dx_level(container, dx_path)` — `UCC.exe batchexport` via `docker exec` **into the build
   container**;
2. `qualify_live_level(got, driver)` — `OBJ DEPENDENCIES PACKAGE=MyLevel` scraped from the **live**
   editor's `Editor.log`, polled up to **20 attempts / 20 s**;
3. `requalify_classes_to_loaded(expected, _read_loaded_classes(driver))` — `OBJ LIST CLASS=Class`,
   polled up to **45 attempts / 90 s** and requiring two consecutive identical non-empty reads;
4. the offline `compare_view` equality — no editor.

Steps 1–3 move into **one `docker run --rm`** of the baked editor image, whose command runs two UCC
invocations in sequence and then exits:

```
wine /opt/UED22/UCC.exe batchexport <built.dx> Level T3D 'Z:\work\out'
wine /opt/UED22/UCC.exe Editor.ExecCommandlet 'Z:\work\verify.txt'
```

where `verify.txt` is `OBJ LOAD FILE=` for the build's referenced package set, `MAP LOAD FILE=` the
built map, then `OBJ DEPENDENCIES PACKAGE=MyLevel` and `OBJ LIST CLASS=Class`. Both dumps land on
**stdout, in order**, and the host reads them from the process's captured output.

Why this is not merely "the same thing, elsewhere":

- **Both poll loops disappear.** They exist solely because `Editor.log` is a 4 KB stdio-buffered
  stream that an external reader cannot see past (`quirks.md`), which is why `dump_obj_dependencies`
  re-drives a guaranteed-noisy flush filler each round and `_read_loaded_classes` waits for two
  identical reads. A commandlet writes to stdout and exits; there is no buffer to defeat and no
  completion to infer. `spikes/levelbuild-friction/README.md` §3 counts **19** production occurrences
  of `OBJ DEPENDENCIES … did not complete within 20 attempts (20s)`; that failure mode is deleted,
  not tuned.
- **It satisfies a documented precondition the warm editor cannot.** `commands.md` on
  `OBJ DEPENDENCIES`: *"Run in a fresh editor with exactly one level loaded — `MAP NEW`/`MAP LOAD`
  don't purge the prior level's objects, so a reused editor accumulates stale textures."* Warm reuse
  structurally violates this. A one-shot commandlet satisfies it by construction, every time.
- **No dialog.** The GC "Cleaning up…" `xmessage` blocks the Command-BOX input path, not the engine's
  exec loop (`quirks.md`, ✅ 2026-07-18) — and a commandlet has no Command box at all.

### 5.2 Lifecycle — nothing to leak

`docker run --rm` around a process that **exits by itself** in ~1.4–3.7 s. No detach, no readiness
poll, no `ensure_editor` retry loop, no `stop_editor` a killed parent might skip. A SIGKILL of the
uedcli process leaves at worst one container that is already exiting on its own.

**No wineprefix volume is mounted.** The verify container uses the image's baked `/wineprefix` on its
own copy-on-write layer, which is per-container by construction and dies with `--rm`. This is why it
is a plain `docker run --rm <image>`, not `docker compose run`: the compose service definition would
attach the shared `wine-prefix` named volume, and concurrent `wineserver`s on one prefix corrupt the
registry/locks (`parallel-editors.md` §1). It also avoids the ~5 s `docker compose run` + prefix-seed
overhead SP-E.5 measured, which matters when the whole verify budget is ~5 s. **SP-F.1 confirms wine
runs off the baked prefix with no volume mount** — the Dockerfile does `wineboot --init` at build, so
this is expected, but it is the one assumption the design rests on that has not been observed.

Mounts: the `/resources/<n>` set and the crafted engine ini exactly as `ensure_editor` composes them
(the verify must resolve the level's packages against the same `[Core.System] Paths`), plus a
host staging dir at `/work`.

### 5.3 The verify reads the HOST bytes

Ordering changes, and it closes a real gap. Today: `MAP SAVE` → verify the container-side
`/work/<uuid>.dx` → `cp_out` to host staging → `os.replace`. So a corrupt `docker cp` lands
unverified. New order: `MAP SAVE` → **`cp_out` to host staging first** → bind-mount that staging dir
into the verify container → verify → `os.replace` on pass. The verify now reads the exact bytes that
will be installed, which is what `verify.py`'s own docstring ("save/apply MUST re-read the bytes on
disk") always intended.

`MAP SAVE`'s existing completion discipline is unchanged and still load-bearing: `driver.map_save`
waits for a stable non-zero size AND a complete 36-byte package header, because the save writes
`Save.tmp` and patches the summary LAST (`commands.md`).

### 5.4 Scope limits — why the commandlet is a verify host and not a build backend

`spikes/headless-materialize/findings.md` establishes three hard limits, none of which touch the
verify path, and all of which would block a build backend:

- **`LIGHT APPLY` poisons the level** — it opens a temporary viewport that spawns a `Camera` actor
  and leaves it zombied with a dangling `Player` reference, so the following `MAP SAVE` GPFs in
  `FArchiveSaveTagExports`. Nine workarounds failed; reproduced under a real Xvfb and under an
  independent host-Wine run, so it is not a null-display artifact. **The verify neither lights nor
  saves**, so it never reaches this.
- **The clipboard is dead**, so `EDIT PASTE` — the only add path that yields a CSG-participating
  brush — does nothing. The verify imports nothing.
- **`BRUSH ADD`/`SUBTRACT` reassign brush actor names** (`Brush1…BrushN`), which would break a
  name-keyed compare. The verify only *reads* an already-built map.

`CAMERA OPEN` also fails (`CreateWindowEx failed`), which is recorded here so nobody re-proposes
moving `preview`'s retired editor-screenshot path to the commandlet.

### 5.5 The two things SP-F must confirm before this ships

1. **Export dialect.** v1 keeps `UCC.exe batchexport` — the *same* command `store_export` runs today,
   merely in a different container — so the compare's inputs are provably unchanged and only *where*
   the verify runs varies. (Its `<outdir>/MyLevel.T3D` naming and the package-prefix normalization
   `store_export` already handles are unchanged.) Doing the export as `MAP EXPORT` inside the same
   commandlet script would save one engine init (~1.3 s) but changes the T3D dialect; that is a
   named follow-up (§11) gated on a byte-compare, not a v1 variable.
2. **Loaded-class equivalence.** `requalify_classes_to_loaded` maps both compare sides onto the
   *live* loaded-class pick, so the verify container's loaded set must not be narrower than the build
   editor's, or a bare class could resolve differently. The script therefore `OBJ LOAD FILE=`s the
   same `_level_referenced_packages` set the build loaded, before `MAP LOAD`. SP-F.2 confirms the
   resulting class map equals the live editor's on a real level, and measures the cost (SP-E.3
   measured ~1.3 s per package).

## 6. Code shape (build items)

- **Generalize, don't fork, the warm-container gate.** `preview_game.acquire_warm_container`'s flock
  + ONE-inspect fingerprint + reboot-retry pattern is factored into a shared helper (e.g. `warm.py`)
  parameterized by container name, lock path, fingerprint components, boot function and health probe
  — used by BOTH the game-preview container and `acquire_warm_editor`. If the factoring fights the
  preview code's shape, the fallback is a sibling implementation in `editor.py` mirroring the pattern:
  the spec mandates the behavior, not the refactor.
- **Image-side:** `uned/entrypoint.sh` — env-gated idle watchdog as tini's direct child + marker at
  start; `wine_ctl.py` — marker touch per invocation; `docker compose build` sequenced into the
  build; a fail-closed assertion that the boot's `UED_IDLE_S` took effect.
- **Boot-side:** a warm-boot path beside `ensure_editor` that stamps the fingerprint LABEL, passes
  `UED_IDLE_S`, mints the per-boot volume name, writes the crafted ini under the per-user home, and
  runs the orphan-volume sweep. `ensure_editor` itself gains `UED_IDLE_S` (decision 8) and nothing
  else.
- **Verify-side (new module, e.g. `verify_container.py`):** compose the script, run the one-shot
  `docker run --rm`, capture stdout, feed the existing `qualify` parsers. `verify_dx_matches` loses
  its `qualify_driver` parameter and takes the built map's **host** path; `store_export.export_dx_t3d`
  keeps its `container` argument and is simply handed the one-shot container. Per **Code & CLI
  conventions** (no back-compat cruft), the `qualify_driver` seam and the two poll wrappers
  (`dump_obj_dependencies`, `_read_loaded_classes`) are **deleted**, not kept behind a flag — their
  parsers stay.
- **Drive-side:** `driver.map_new()` gains the dismissal; the reused-build defensive dismissal;
  per-build `/work` cleanup.
- `apply.run_materialize` swaps its `ensure_editor`/`stop_editor` bracket for `acquire_warm_editor(…)`
  → on success drive + release (container persists; teardown only on drive failure per §4.3); on
  busy/pinned-mismatch → today's ephemeral bracket verbatim. The returned handle says which mode was
  taken so the `finally` knows whether to `stop_editor`.
- `_save_and_swap_verified` reorders to cp_out-then-verify (§5.3).
- `preview_game.materialized_dx` inherits everything for free (it calls `run_materialize`).
- **Human-facing stderr line per materialize:** which path was taken (`warm reuse` / `warm boot` /
  `ephemeral fallback (busy)` / `ephemeral fallback (pinned)`) — one line, stderr only, so stdout
  stays pipe-clean.

## 7. Errors (named exit-2, never a traceback)

- Warm boot fails twice → remove container + volume, exit 2 naming the container + the captured
  `docker logs` tail.
- Warm-mode DRIVE failure → teardown + exit 2, message names warm mode and "a retry boots fresh".
- **Verify-container failure** (docker unavailable, image missing, the commandlet exiting non-zero or
  its stdout carrying `Commandlet … not found` / `Failed loading package`) → exit 2 naming the
  container and embedding the captured stdout tail. Note `Editor.ExecCommandlet` **does not abort on a
  failing script line** (`commands.md` "`EXEC <file>`": errors are skipped and the script continues),
  so success is judged by the *parsed dumps being present and well-formed*, never by exit code alone.
  A missing or unparseable dump is an error, never a silently empty qualification.
- Verify MISMATCH → exit 2 with `_first_diff`'s diagnostic (unchanged), warm editor left up (§4.3).
- Lock contention / pinned mismatch → NOT an error (silent fallback; the stderr mode line says so).
- Everything the ephemeral path already names is unchanged.

## 8. Tests

Offline (mocked docker/driver, like the warm-preview suite):
- fingerprint: tuple change (overlay mtime / composed-set stub file / mount pair / image id) → reboot;
  exact match → reuse; an OUT-of-composed-set stub-cache change → NO reboot; stopped (pinned or not)
  → reboot; running+mismatch+pinned → ephemeral fallback, container untouched.
- acquire ordering: inspect → marker touch → health probe (assert marker precedes probe).
- lock held → ephemeral fallback (`stop_editor` called on that path; NOT on the warm success path).
- health probe fail → one reboot attempt → second fail → container+volume removed + named exit 2.
- warm-mode drive error → container + volume + ini temp removed before lock release; exit 2 carries
  the warm-mode hint; no auto-retry occurred. **Verify FAILURE → editor NOT torn down** (§4.3).
- volume lifecycle: per-boot unique name; orphan sweep removes unattached `uedcli-editor-wp-*` **and
  `uned-wp-*`** volumes only, and never one with a container attached.
- watchdog gating: warm boot AND ephemeral boot both pass `UED_IDLE_S`; the standing-container config
  does not (assert absent).
- verify container: invoked with `--rm`, no wineprefix volume, the composed mounts + crafted ini, and
  the built map's HOST path; the script carries the referenced-package `OBJ LOAD`s before `MAP LOAD`.
- verify parsing: a commandlet stdout fixture parses to the same qualification the live-editor log
  fixture produced (the parsers are shared, so this pins the acquisition change); a commandlet whose
  stdout lacks the dump → named error, NOT an empty qualification.
- drive sequence on the mocked driver: `ensure_load` → ONE `map_new` (with dismissal) → re-add →
  rebuild; the reused-build defensive dismissal precedes the first command.

Integration (live, `-m integration`): a warm double-build; a concurrent-invocation fallback exercise;
a live idle self-death check on an EPHEMERAL editor (backdated marker → self-terminates — this is the
§1(c) leak regression and it is the one that matters most); and the SP-F.6 soak as a marked test.

## 9. Spike SP-F (BLOCKING build)

SP-E answered the reuse questions; SP-F answers what decision 6 introduces. Harnesses land in
`spikes/2026-07-26-commandlet-verify/`, per `dev/docs/rules/spikes.md` (committed, re-runnable, and
every checkable finding pinned by a committed regression).

1. **Baked prefix, no volume (§5.2).** Does `docker run --rm` with no `/wineprefix` mount run
   `UCC.exe` cleanly, repeatedly, and concurrently (≥3 at once)? If not, the fallback is a per-run
   anonymous volume, which `--rm` still reclaims.
2. **Loaded-class equivalence (§5.5.2).** On a real level, does the verify container's
   `OBJ LIST CLASS=Class` map equal the live build editor's? Measure the added `OBJ LOAD` cost.
   **Falsifier:** any bare class resolving to a different package than the live editor picks.
3. **Cross-level correctness (SP-E.2 re-test).** Castle → anchor → castle, each verified in its own
   one-shot container. SP-E.2 saw a castle actor appear in an anchor build's verify but could not
   trust it (flaky editor). **Falsifier:** any cross-level residue surviving in the verify direction —
   and separately, in the IMPORT direction, which §4.4 notes is NOT addressed by this change.
4. **Timing, measured not derived.** Directly time: warm drive, verify container end-to-end, cold
   ephemeral end-to-end. SP-E.5's ~42 s verify was derived by subtraction; §1's projected ~20 s / ~40 s
   stand or fall on this number.
5. **Reliability — the SP-E blocker's actual re-test.** ≥8 consecutive warm builds with the verify in
   its own container. **Acceptance: 0/N failures.** Anything else and the design is not shipped —
   SP-E's whole lesson is that ~50 % is what "mostly works" looked like.
6. **Clean RSS soak (§4.6).** ≥6 *successful* warm builds; decides whether a builds-per-container cap
   ships.
7. **Watchdog, end to end (§1(c)).** SIGKILL a materialize mid-drive; confirm the orphaned container
   self-terminates within the deadline and the orphan sweep then reclaims its volume. This is the leak
   regression and it must be live-verified, not reasoned about.

SP-E.7 (colliding bare names) stays deferred: for the verify direction decision 6 moots it; for the
import direction it needs a two-package colliding fixture that does not exist. It is filed on the
board rather than blocking here.

## 10. Risks / watch-list

- **`(path,size,mtime)` blind spot** (inherited from the preview fingerprint, restated because the
  output is a durable artifact): a same-size, mtime-preserving package/stub edit is missed → a
  silently stale build. Escape hatch: `docker rm -f uedcli-editor-<uid>`.
- **The verify is a CONTENT backstop only.** It compares the built map to the intended trunk; it
  cannot detect a stale resident package (same names, old bytes). Package freshness is solely the
  fingerprint's job. Moving the verify to a fresh container does not change this — if anything it
  sharpens it, since the verify container is now *always* fresh while the builder may not be.
- **A stale pinned editor** silently degrades every materialize to ephemeral-boot speed; the stderr
  mode line is the tell.
- **The commandlet is a second engine host to keep working.** It runs the same baked substrate, so it
  shares the stale-image trap and any substrate change now has two consumers. `quirks.md` records the
  matching failure mode: `Commandlet batchexport not found` when a container's `EditPackages` did not
  load `Editor` — always run it in a clean substrate container, which the one-shot is by construction.
- **Two verify-relevant facts remain UNPINNED** and are called out so nobody reads this spec as
  settling them: whether `MAP SAVE`'s `Save.tmp` is created in the destination directory (if so,
  concurrent saves into one directory collide — `commands.md`), and what exactly makes an `IMPORTADD`
  brush invisible to CSG.

## 11. Out of scope / follow-ups

- **`level materialize --native`** — ranked first overall by `spikes/headless-materialize/findings.md`
  (1.2 s, no Wine/Docker/X, with lighting, movers, names and paths) and explicitly deferred by
  decision 7. Board item.
- **The commandlet as a golden/oracle host** for the native byte-parity work, replacing
  `build_ued_golden.py`'s GUI drive — gated on a `BRUSH IMPORT`+`BRUSH ADD` vs `EDIT PASTE`
  byte-comparison. Board item.
- **A build-only container image** (no Xvfb/VNC/xdotool) for commandlet work.
- **`MAP EXPORT` inside the verify script** instead of a second `batchexport` invocation (§5.5.1).
- **`EXEC <file>` batch driving of the build** (spike PROVEN 2026-07-18): composes with, and does not
  block, this spec; ~6× less drive overhead and it rides through the GC dialog.
- `--editor`/`--native` flag split on materialize (the native cutover owns it).
- `stash intersect`/`deintersect` adopting the warm editor; warming the no-GUI UCC build containers.
- A user-facing pin (`--keep-alive` analogue) for the editor container.
- In-place reload of changed packages without a reboot (the fingerprint reboot is the v1 answer).
