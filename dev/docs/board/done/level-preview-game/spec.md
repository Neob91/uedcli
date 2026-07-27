# `level preview --game` — one-exec batch driver + settle-gated PrepareCamera

**Status:** **BUILT + live-verified 2026-07-17** (warm reuse ~2.2s, 10-shot batch 8.37s all distinct;
cold ~60s). Pivoted from the persistent-daemon idea after a 2-reviewer design gate — both recommended
this lighter one-exec path; §§below keep the daemon design as the REJECTED alternative. Durable parts
folded into `architecture.md` (§`level preview --game`) + `decisions.md` (2026-07-17 14:42) + memory;
this ephemeral spec may now be pruned. ≤1s (unmet — dev-CLI startup floor) boarded in `inbox.md`.
Optimizes the docker-drive of the warm container built in
`specs/2026-07-17-game-preview-warm-container.md`; keeps that spec's per-user identity, flock,
fingerprint, post-boot-symlink delivery, fail-closed boot, and the inline bash idle-watchdog.

**Motivation (Andrzej):** a same-map repeat preview took ~9s for ONE screenshot — almost entirely
docker-CLI round-trip overhead (~8 reuse-gate probes incl. a ~1–2s `docker stats`, + a per-op
`docker exec` for deliver/travel/each pose/each grab, + a `docker cp` per shot). Target: **a same-map
1-shot preview in ≤1s.** Directive: "only ONE `docker exec`, not multiple."

## 1. The one-exec model (why, not a daemon)
Both design reviewers: a single in-container **batch script** run via ONE `docker exec` captures
essentially the whole 9s→~1s win, satisfies "one docker exec" literally, and is a low-risk
consolidation of the just-shipped build — whereas a persistent published-port daemon buys only ~one
exec-spawn (~0.4s) more at the cost of a long-lived server, a collision-prone published port, a wire
protocol, and a testability/lifecycle regression. So: **no daemon.**

Per warm preview batch the host makes exactly:
- **one `docker inspect`** (cold-path reuse gate): `State.Running` + the fingerprint label + pinned
  label, in a single call — replaces `_container_up`/`_label_of`/`_is_pinned`/`_novnc` and the
  `docker stats` RSS probe.
- **one `docker exec`** running the in-container batch script (`preview_batch.py`, baked into the
  image), which does the WHOLE batch against the in-game link and returns all PNGs.
- (`docker run` only on create; `docker rm -f` only on reboot — both cold-path, unchanged.)

## 2. The in-container batch script (`preview_batch.py`)
Invoked as one `docker exec <name> python3 /opt/uedpreview/preview_batch.py`, fed a request on
**stdin** (JSON: `{deliver:<mapfilename>, stem:<stem>, rebuild:<bool>, shots:[[x,y,z,pitchUU,yawUU],…]}`)
and emitting a **length-framed stream on stdout** (per shot: a JSON status line `{ok:true}`/`{ok:false,err}`
then, iff ok, a 4-byte big-endian length + the PNG bytes). It:
1. `DELIVER`: `ln -sf /resources/preview/<mapfilename>` into the local Maps dir (in-process fs op).
2. `TRAVEL <stem>`: the 3-phase handshake over the in-game link — **reconnecting the link socket
   after every `open`** (the engine DESTROYS the TcpLink on travel — `UedPreviewLink.uc:109`; the
   console re-spawns a fresh listener, so the link connection is transient and re-established each
   travel and at start). **Skip iff a live `GetURLMap` already == `<stem>` and not rebuild** (the
   skip is decided against a LIVE query, never a cached value). Bumps `/work/.travel_count`.
3. Per shot: `PrepareCamera x y z pitchUU yawUU` → **block for its `OK` (settle-gated, §3)** → X-grab
   the game window (`import -window`) → stream the PNG. On grab failure emit `{ok:false,err}` and
   the host closes + reboot-retries (framing has no in-band resync).
4. Reads the game PID (`pgrep $GEXE`) once for RSS if asked; tolerates absence.
All socket reads are **bounded** (timeouts); a wedged link → nonzero exit → host reboot-retries.

## 3. `PrepareCamera` — the settle moves into the verb (uscript)
Rename the link verb `Screenshot` → **`PrepareCamera`** (it never captured anything — it poses the
camera; the X-grab is the real screenshot). Crucially it **defers its `OK` until the posed frame has
been drawn**, so `OK` IS the "safe to grab now" signal and the host/script needs no sleep/poll:
- The handler sets `SetupPreviewState` + `SetLocation` + `ViewRotation` (unchanged pose math, incl.
  the single `BaseEyeHeight` eye→pawn subtraction and level-horizon roll), records the pending
  request id + a shot-pending flag, and returns WITHOUT replying.
- The `OK` fires only after a frame has demonstrably rendered with that pose — via
  `UedPreviewConsole.PostRender(Canvas)` (fires AFTER the frame draws) or an N-tick gate in the
  link's `Tick()` (runs pre-render, so wait ≥1 tick past the pose). **Spike the true minimum N**
  (render + the small extra X-blit lag before the window pixels update); it is tens of ms, not 400,
  and can NEVER grab a stale pre-pose frame because `OK` gates it. A bounded fallback timer replies
  an error if no frame is seen (never hang the batch).
Why a settle exists at all: posing the camera does not repaint the window — the game's own render
loop does, on its next pass; grabbing before that pass captures the previous pose's pixels.

## 4. What is DELETED vs the 2026-07-17 build
`docker stats` RSS probe; the heartbeat daemon thread (`_start_heartbeat`/`_stop_heartbeat`) and its
`.last_use` touches — a sub-second batch never nears the 600s idle window, so ONE marker `touch` at
batch start suffices (done inside the exec, or dropped if the watchdog reads travel activity); the
per-op host helpers that were `docker exec` (`_touch_marker`, `_symlink_preview`, `xgrab`,
`_link_alive`, `_travel_count`, `_bump_travel_count`) and `_rss_mib`; the per-shot `docker cp`; the
0.4s host settle sleep. The link client + travel + xgrab logic MOVE into `preview_batch.py`.

## 5. What STAYS (unchanged, preserved contracts)
The entrypoint boot (symlink-farm + relative Paths + relaunch loop — esync fix untouched); the inline
bash idle-watchdog + `/work/.last_use` + `/work/.pinned` (reviewers: keep — tiny, proven, tini's
child, independent of the control path); the fingerprint as a docker LABEL (read by the one inspect);
per-user identity + flock; D5 delivered-map naming; the `/resources/preview` mount + post-boot symlink
delivery (SP-R gate); fail-closed boot; `--keep-alive` pin; `.dx`/`.unr`; the reboot-retry budget
(host-side); the 3-phase travel handshake (now inside the batch script).

## 6. Host changes (`preview_game.py`)
- `acquire`: flock; ONE `docker inspect` → running? label==fp? pinned? → reuse / reboot(`rm -f`+run) /
  pinned-mismatch-error / RSS-or-travel-over-bound reboot (RSS now read by the batch script's trailer
  next call, or dropped — it's insurance; flat per SP-R). On absent/dead → `docker run` + wait for
  boot (a cold-path `docker ps`/`logs` liveness+diagnostic poll stays — NOT the hot path).
- `render`: build the request, ONE `docker exec … preview_batch.py` with the JSON on stdin, parse the
  framed PNG stream to `out_dir`. A nonzero exit / dropped stream → reboot-retry (bounded budget).
- Keep every docker call behind the `_run` seam so offline tests still mock it; add offline unit tests
  for the framed-stream parse + the request build. `preview_batch.py` gets its own offline unit tests
  (fake link socket + fake `import`).

## 7. Risks / open
- **Stale-frame settle (the one correctness risk)** — retired by §3's OK-gates-on-render + the spike;
  a bounded fallback prevents a hang.
- **Batch-script robustness** — bounded socket reads; a wedged link → nonzero exit → host reboots.
- **Framing desync** — the discriminated `{ok}`-line-then-optional-PNG has no in-band recovery; the
  only resync is close + reboot-retry (stated so the host implements it).
- **RSS bound** — de-scoped to a stdout trailer or dropped (flat per SP-R); no `docker stats`.

## 8. Out of scope
The boot/esync mechanism; the daemon (rejected); the SHOT grammar/pose math; the native tier.
