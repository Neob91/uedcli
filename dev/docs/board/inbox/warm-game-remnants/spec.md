# `level photo --game` — warm reusable container + live map delivery (design spec)

**Status:** **BUILT 2026-07-17** (live-verified: cold boot → reuse 17s vs 79s → idle self-death).
Reviewed rounds 1–4 (8 cold reviewers), SP-R gate CONFIRMED live. The durable parts are folded into
`architecture.md` (§`level photo --game`) + `decisions.md` (2026-07-17 06:57/07:30/08:31) +
`unrealed/` memory; this ephemeral spec may now be pruned. Remaining/deferred items are on the board
(`board/inbox/`). Below is the as-designed record.

**SP-R verdicts (2026-07-17 live):** ✅ post-boot **Nth-`open` + symlink** resolution WORKS (gate
green, no Plan B needed) · ✅ unique names always load fresh content · ✅ RSS **flat** over 11 travels
(386→414 MiB — minimal leak; levels GC'd on travel) · ✅ **no silent NAME_SIZE collision at any
length** (resolves ≤180 chars, fails LOUDLY ~250; the "63-char silent truncation" fear did not
reproduce) · ✅ mission-map frame **clean** with the no-abort driver (conversation guard confirmed
unneeded).

**Builds on:** the shipped `--game` tier (board item `level-preview-game`,
board item `level-preview-game`; `preview_game.py` + `uedcli/game/`). Changes the
CONTAINER LIFECYCLE + MAP-DELIVERY only; SHOT grammar, posing, capture unchanged.

**Decisions:** `decisions.md` `2026-07-17 06:57` + the `07:30` supersession (per-user identity,
`materialized__`/`copied__` naming, foreground watchdog, single heartbeated marker).

---

## 1. Problem / motivation

The shipped `--game` tier boots a **per-command ephemeral** container: ~90 s (boot + travel) before
the first shot, killing the **edit → preview → edit** loop. Fix: (1) keep the game **warm** across
invocations; (2) deliver a changed level **without restarting**, guaranteeing a fresh read from the
package-name-keyed object pool.

**Cross-travel cleanliness — clean in practice.** The console re-spawns the link + re-applies
freeze/noclip/clean at each possession, so state doesn't bleed. R3/R4 reviewers flagged a *theoretical*
conversation-taint edge (if an `open`ed mission map auto-started a conversation in the ~1 s window
before freeze lands — `UedPreviewConsole.uc:24`'s `CheckAccum>=1.0` throttle — DeusEx's
`InConversation()` could reroute rendering to the conversation camera). **Empirically this does not
happen:** the 10 UNATCO shots this session were of `01_NYC_UNATCOHQ` (a mission map WITH intro
datalinks), rendered through the current driver that has **no** conversation abort, and came out clean
— because we possess a *preview* pawn and freeze the world (`bPlayersOnly`) rather than running the
mission as the real player, the conversation machinery never starts. So a driver conversation-abort is
**NOT a build item** — it's a watch-item: SP-R(e) simply *looks* at a conversation-prone frame, and we
add an abort only if a tainted frame is ever actually observed (§9).

---

## 2. Decisions

| # | Decision |
|---|---|
| D1 | **ONE reusable game container per Unix user** — `uedcli-game-preview-<uid>`, not machine-global, not a registry. |
| D2 | **A kernel `flock(2)` on an open fd** serializes access (SIGKILLed holder auto-releases). |
| D3 | **Idle self-death after 10 min** via a watchdog run **INLINE in `game-entrypoint.sh` (tini's direct child), NEVER backgrounded** — its `exit` stops the container (no `kill 1`; §4.3). |
| D4 | **Map delivery = a bind mount at `/resources/preview` (OUTSIDE the `/resources/r*` farm namespace) + a LOCAL Maps-farm symlink**, NOT a raw-bind-mount `Paths` glob. Preserves the esync boot fix. **Fallback (R4): `docker cp` a real file into `/work/dx/Maps` — the shipped, proven mechanism — if SP-R(b) shows the symlink form doesn't resolve.** |
| D5 | **Maps hash-named, kind-prefixed, dot-free, lowercased, length-CAPPED (§5.1).** Trunk `materialized__<level>__<hash12>[__<nonce>].dx`; `--map` `copied__<contenthash12>.<ext>`. UE1 FName cap is **63 usable (`NAME_SIZE`=64), truncated SILENTLY** (source-memory; **pin empirically in SP-R §8c** — R4-B). Whole stem is length-budgeted, hash+nonce guaranteed to survive, over-budget = **LOUD error** never truncation. Dot-free (`.`=UE1 `Package.Object` sep); **fully lowercased** (the farm link is lowercased and `open <stem>` resolves only via wine case-folding — §5.2, R4-B case-bridge). Prefixes guarantee a non-numeric first segment. |
| D6 | **Reload keying: filename-derived. Offline-CONFIRMED for the file; the RUNNING-ENGINE behavior is a LIVE GATE (SP-R §8).** Offline (via `pkg_write.py`/`parse_package`) proves only that the `.dx` header has GUID+generations and **no package-name field** → on disk, package identity is the filename stem. Whether the *running* engine (a) keys its resident pool by that FName not GUID and (b) re-resolves per-`open` is confirmed LIVE in SP-R(a)/(b) — it is NOT settled offline (R4-A M1). D6's "internal-rename" alternative is judged moot by the offline fact but is the documented fallback (§8, R3 MED-2). **No fresh-GUID belt-and-suspenders** — the preview `.dx` is built by `run_materialize` (the ephemeral UnrealEd path), which never calls `pkg_write.build_package`, so that GUID is not on the path; and on a *reused* name a mismatched GUID would trip a load ERROR, not a silent reload (R4-A H2 / R4-B Claim 3). The guarantee rests on the **unique filename alone**. |
| D7 | **`.dx` AND `.unr` for INPUT + GLOBS only** (`--map` + farm/Paths); trunk materialize stays `.dx`. |
| D8 | **Dir = existing `<project>/uedcli/tmp/preview/`**, bind-mounted at `/resources/preview/`. |

---

## 3. What is NOT changing / build-migration flags
SHOT grammar, the link surface (`Ping`, `UedPreviewLink.uc:88`), X-grab, `--native`, CLI flags.
Editor/materialize/stash stay per-command ephemeral. The esync symlink-farm boot is unchanged.
**Build MIGRATES shipped code (R3 F2):** `preview_game.py` writes `{level}.{hash}.dx` and travels to
the DOTTED stem `<level>.<hash>` (`:74`, `_stem` at `:278`) — code-plausibly unresolvable by `open`
(interior dot = `Package.Object` sep; the diagnosis is code-plausible, not independently proven —
R4-A L3), which is likely why the *trunk* preview path was never confirmed (only `--map` retail
names, no interior dots, were exercised). D5 replaces the write name, `_stem`, the `{level}.*.dx`
prune glob (`:92`), and the travel/`docker cp` names. The `/resources/preview` mount and the
entrypoint preview-symlink wiring + boot-time farm-namespace ASSERTION **do not exist yet** (R3 F7 /
R4) — both build items. (A DX-driver conversation abort is NOT a build item — §1/§9.)

---

## 4. The warm container (D1–D3)

### 4.1 Identity, lock, fingerprint — PER-USER
- Container `uedcli-game-preview-<uid>`; lock `~/.uedcli/game-preview.lock`.
- **Reuse fingerprint** (a container label) = hash of ALL of: (a) the **image id**
  (`docker image inspect`); (b) the **realpath-normalized ordered mount `source:dest` pairs** (incl.
  `<project>/uedcli/tmp/preview →/resources/preview` → embeds project identity, closes two-project
  reuse); (c) **`--size`** (baked at boot); (d) **the PROJECT-OVERLAY packages' `(path,size,mtime)`
  tuples** (R3 MED-4 — folded IN here; base game `.utx` immutable → EXCLUDED; NOT a byte-hash, NOT a
  separate post-reuse check). Deterministic. Mismatch → reboot (unless pinned — §4.7).

### 4.2 Lifecycle
```
open fd on ~/.uedcli/game-preview.lock ; flock(fd)                     # D2; bounded acquire timeout
  fp = fingerprint(image id, normalized mounts, size, overlay stat tuples)
  container = uedcli-game-preview-<uid>
  if up(container): docker exec touch /work/.last_use  (best-effort)   # R3 MED-5 — FIRST, before Ping
  if up AND label==fp AND Ping OK:
      if RSS(container) > CEILING or travel_count(container) >= N: reboot-fresh   # R3 HIGH-1/F6 — container-scoped
      else: REUSE
  elif up AND label!=fp AND pinned: ERROR "pinned other-project container live; docker rm -f <name>"
  else: docker rm -f stale; boot fresh, labelled fp   (~90s, once)
  start HEARTBEAT (daemon thread): every ~60s `docker exec` with a ≤30s TIMEOUT to touch /work/.last_use; SWALLOW ALL ERRORS  # R3 MED-3
  re-farm ONLY-new/vanished files (§4.4)
  deliver map (§5); (3-PHASE handshake §5.3) TravelToLevel <stem>  (skip iff on <stem> AND not --rebuild)
  for each shot: (link-op wrapper §4.5) pitch-clamp -> Screenshot -> X-grab -> cp out
finally: stop+join heartbeat WITH A BOUND (never hang on a wedged exec); close fd   # R3 MED-3 — must not hold the lock
```
No static in-use sentinel — the heartbeated `/work/.last_use` is the sole liveness signal. `.pinned`
(§4.7) is the only opt-in immortality. **Heartbeat is NEVER load-bearing for shutdown or the lock**
(R3 MED-3): bounded-timeout daemon thread; a wedged exec can neither hang `uedcli` exit nor keep the
`flock` held.

### 4.3 Idle self-death (D3)
The entrypoint, **only after link-up (READY)**, creates `/work/.last_use` and runs the watchdog
**inline** (tini's direct child):
```
: > /work/.last_use                       # created only at READY → "marker absent ⇒ not idle" during boot
while true:
  sleep 60
  [ -e /work/.pinned ] && continue                                    # §4.7
  if now - mtime(/work/.last_use) > 600: pkill -9 -f "$GEXE"; exit 0  # $GEXE not hardcoded (R4-A L1); inline exit ⇒ tini exits ⇒ container stops
```
- **Both fail-open exits must fail CLOSED (R4-A M3):** the relaunch-loop-exhausted branch
  (LINKED=0, `game-entrypoint.sh:131`) **and** the ini-patch-failure branch (`:92`) currently
  `exec tail -f /dev/null` → a marker-less, watchdog-less immortal zombie. Both become `exit 1`
  (container stops; the host already surfaced the error). Self-heals via §4.2 `rm -f stale` anyway,
  but the fail-closed rule must be applied to BOTH.
- 60 s heartbeat vs 600 s deadline (~10× margin); no single op exceeds it (`TRAVEL_TIMEOUT_S=480`).

### 4.4 Re-farm on reuse — DEFERRED (the fingerprint reboot covers the real case)
*As built (2026-07-17):* the reuse path does NOT re-run the farm. Project-overlay staleness (the
mutable case) is caught by the §4.1 fingerprint → a full reboot re-farms from scratch, which is
correct if heavier than an in-place delta. The only gap is a NEW **base** map appearing mid-session
(base packages are otherwise immutable) — not picked up until the next reboot. The additive re-farm
(add new symlinks + sweep dangling, never `rm -rf`) is **deferred** (boarded in `board/inbox/`); it was
not worth the complexity given the fingerprint reboot. The preview symlink still uses `ln -sf`
(tolerates EEXIST on same-hash re-preview — R4-A L2). Order on reuse: **add preview symlink → travel
(skipped iff already on `<stem>`) → shots**.

### 4.5 Link-op reboot/retry wrapper (R1/R2/R3)
On empty/timeout reply → `Ping`; if dead → **reboot-fresh → wait READY → re-run the FULL delivery →
retry once**. A **per-batch reboot budget (2–3)** caps churn; over budget → `GamePreviewError`. An
`ERR no-player` right after travel gets ONE bounded retry — **but see the §4.6 precondition: a
structurally playerless / uncarved map makes the retry futile** (R4-B), so no-player after the retry
errors clearly (it is a precondition failure, not a transient race). Poses are `_resolve_all`'d up
front and prior shots live on the host `out_dir` → a reboot loses neither.

### 4.6 Memory bound + player-spawn precondition
**Memory — SP-R DOWNGRADED this from a load-bearing concern to cheap insurance.** RSS stayed
**flat over 11 travels (386→414 MiB, no monotonic trend)** — levels are unloaded/GC'd on travel and
the interned-FName growth per unique stem is negligible (a few bytes). The reboot bound remains as a
belt-and-suspenders backstop, container-lifetime: a **container-side `/work/.travel_count`** (host
increments per travel) → reboot at the §4.2 reuse gate when `travel_count >= N (default 200 — raised
from 40 given the flat RSS)` OR `RSS > CEILING` (from `docker stats`, at lock-acquire). Not a tight
constraint; do NOT reboot aggressively.
**Player-spawn precondition (R4-B):** delivery assumes the map carves to ≥1 BSP node and spawns a
player (else `MatchViewportsToActors → "Failed to spawn player actor"` → `ERR no-player`, a
persistent not transient failure — `quirks.md` verified 2026-06-28). Given native materialize's
collision/BSP fragility, a playerless map is a precondition failure surfaced as a clear error.

### 4.7 `--keep-alive` = a pin (R1/R2)
Drops `/work/.pinned` (watchdog skips the kill) + prints the noVNC URL; un-pin = the user's `docker
rm -f`. A pinned container is never silently `rm -f`'d by a fingerprint mismatch (§4.2 errors).
**Sticky**: one `--keep-alive` pins for the container's whole life, across later normal previews
(document in `--help`, R3 LOW-4). Supersedes the base spec's "bypass finally teardown" definition
(there is no per-command teardown in the warm model — R3 F8).

---

## 5. Map delivery (D4, D5, D8)

### 5.1 Host side — hash-named write into `uedcli/tmp/preview/`, lowercased, length-capped
- **Trunk**: `materialized__<level>__<hash12>.dx` (`canonical_level_hash`; reuse if present).
  **`--rebuild`** appends a **SHORT unique nonce (6–8 base62, NOT uuid7 — R3 F1)**:
  `…__<hash12>__<nonce>.dx` → a never-resident name forces a fresh load.
- **`--map`**: copy to `…/copied__<contenthash12>.<ext>` (byte hash; identical → reuse).
- **Case + length (R4-B, R3 F1; SP-R-refined):** the FULL stem is **lowercased** (delivery resolves
  only via wine case-folding of the lowercased farm link). **SP-R finding:** the feared *silent*
  63-char truncation-collision **did not reproduce at any length** — names resolve correctly to ≥180
  chars and an over-long name (~250) **fails LOUDLY** (the `open` never resolves), not silently.
  Production stems are ≤~46 chars anyway (`materialized__<level>__<hash12>` + short nonce). So the
  length guard is cheap insurance, not load-bearing: keep a conservative bound (**cap at 120 chars**,
  comfortably below the ≥180 that still resolved and far below the ~250 loud-fail), **hash-compress
  `<level>` if over so hash+nonce always survive, else a named error** — never truncate.
- **Prune** per prefix, **N=8**, protecting the newest; count `--rebuild` variants.

### 5.2 Container side — bind mount + local farm symlink (verified boot-safe R3 F7)
`<project>/uedcli/tmp/preview/` bind-mounted ro at **`/resources/preview/`** — leading `p`, so the
`/resources/r*` farm glob never sweeps it and it never enters `Paths` (**boot-safety only — this is
NOT the same as post-boot resolvability, which is §5.3's gate; R4-B corrects §5.2's earlier
over-broad "verified" tag**). A boot-time **assertion** (build item) enforces "no `/resources/preview`
in `Paths`." Per preview the host symlinks the map into the local farm
(`ln -sf /resources/preview/<name> /work/dx/Maps/<name>`, `<name>` already lowercased), added
POST-boot → outside the esync startup enumeration. Reachable via relative Paths `../Maps/*.dx` +
`../Maps/*.unr`.

### 5.3 Travel + the post-boot-resolution GATE — CONFIRMED live (SP-R)
`open <stem>` destroys the link every time, so each inter-level delivery re-runs the base handshake:
`TravelToLevel <stem>` (reply-OK-then-`open`) → link dies → reconnect → poll `GetCurrentLevelName ==
<stem>`. Skipped iff already on `<stem>` AND not `--rebuild`.
**GATE RESOLVED ✅ (SP-R 2026-07-17, [results](../../../spikes/2026-07-17-game-preview-reload-keying/results.md)):**
5 post-boot **symlinked** travels to unique stems in **one reused container** all resolved
(`GetURLMap` == the exact stem each time), including a 2nd–5th `open` after prior travels and a
same-bytes-new-name case. So both untested deltas — **Nth-`open` in a warm container** and the
**symlink** delivery form — work. **Plan B is not needed** but stays documented: if a future substrate
breaks symlink resolution, fall back to D4's `docker cp` of a real file (the shipped mechanism); if
multi-travel resolution breaks, reboot-per-map-change (keeps warm reuse for re-poses).

---

## 6. `.dx` / `.unr` (D7)
`--map` accepts either; farm loops both + Paths carries `../Maps/*.dx` + `../Maps/*.unr`; `_stem`
strips both (verify + test). Edge: two same-content files differing only in extension → same
`copied__<hash>` stem, both on Paths → ambiguous; reject or extension-qualify. Trunk output stays
`.dx`.

---

## 7. Errors (named exit-2, never a traceback)
Existing `--game` paths + lock-acquire timeout, unsupported `--map` extension, re-farm failure, the
over-budget-stem error (§5.1), the pinned-vs-mismatch refusal (§4.7), the per-batch reboot-budget
exhaustion (§4.5), the player-spawn precondition failure (§4.6). Silent: the fingerprint reboot, the
transparent reboot-retry, the idle kill.

---

## 8. Spike — SP-R: **DONE ✅** ([results](../../../spikes/2026-07-17-game-preview-reload-keying/results.md))
**Step 0 (OFFLINE):** confirmed via `pkg_write.py`/`parse_package` — header carries GUID + generations,
NO package-name field → on-disk identity is filename-derived.
**Step 1 (LIVE, 2026-07-17):** all green, in ONE warm container, production-shaped dot-free lowercased
names:
- (a) ✅ `stemA`(A) then fresh unique `stemB`(B) both rendered their own content; a same-bytes-new-name
  case also loaded fresh → running engine keys by FName, reuses no resident.
- (b) ✅ **THE GATE** — 5 post-boot **symlinked** travels (incl. 2nd–5th `open` in the reused
  container) all resolved (`GetURLMap`==stem). Symlink form + Nth-open both work. Plan B not needed.
- (c) ✅ **NAME_SIZE** — no silent collision at any length (resolves ≤180 chars, fails LOUDLY ~250);
  the "63-char silent truncation" claim did not reproduce. §5.1 caps at 120 as insurance.
- (d) ✅ **RSS flat** (386→414 MiB over 11 travels) → §4.6 downgraded; N raised to 200.
- (e) ✅ mission map (`08_NYC_Bar`) rendered a **clean** posed frame with the no-abort driver →
  conversation abort confirmed unneeded (not a build item).
Harness: [`spike_reload.py`](../../../spikes/2026-07-17-game-preview-reload-keying/spike_reload.py),
[`extend_namesize.py`](../../../spikes/2026-07-17-game-preview-reload-keying/extend_namesize.py).

---

## 9. Risks / watch-list
- ~~Post-boot Nth-open + symlink resolution~~ — **RESOLVED ✅ (SP-R §8b)**; symlink form + Nth-open
  confirmed live. Plan B (§5.3) documented but unneeded.
- **esync regression** — D4 + §5.2 (boot-safe R3 F7; assertion is a build item).
- ~~Permanent FName growth~~ — **downgraded (SP-R §8d)**; RSS flat, reboot bound is insurance only.
- **Conversation/datalink taint** — **confirmed NOT observed (SP-R §8e)** on a real mission map. Not a
  build item; add an abort only if a tainted frame ever appears.
- **Playerless/uncarved map** — precondition, clear error not a retry (§4.6, R4-B).
- **Same-size mtime-preserving overlay edits** — `(path,size,mtime)` misses them; `docker rm -f` is
  the escape (R3 LOW-2). `--rebuild` reloads the MAP only, not textures (R3 LOW-1).
- **Case-folding bridge** — lowercased stems + wine case-insensitivity (D5/§5.1); a mixed-case stem
  reaching `open` would break it, so lowercasing is enforced at generation (R4-B).
- **Heartbeat-thread wedge** — bounded-timeout daemon; never load-bearing (§4.2).
- **Worst-case batch wall-time** ≈ reboot-budget × ~900 s — note vs a 20-min hang detector.

## 10. Out of scope
A per-project pool (D1 = one per user); `.unr` OUTPUT from materialize; PlayerStart auto-injection; a
`--size` change forcing a reboot (viewport baked at boot — `--help` note).
