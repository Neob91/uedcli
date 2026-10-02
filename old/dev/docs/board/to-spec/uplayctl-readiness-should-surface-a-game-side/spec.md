# Spec — surface a game-side `Critical Error` instead of a generic readiness timeout

## Goal

When the game crashes into a modal `Critical Error` during boot or map travel, fail fast with the
actual engine error and its backtrace, exit 2 naming it — never a content-free "level never
became X"/"never possessed a pawn" timeout that sends the operator down the wrong path (the whole
"link doesn't survive travel" wild-goose chase this item records was a crashed, wedged game).

## Current state

The `--game` preview readiness has two poll loops, neither of which notices a crash where the
process is still alive but wedged on a modal:

- `preview_game._wait_ready` (`uedcli/preview_game.py:308`) polls for port 7777 listening; it fails
  only on CONTAINER death (`docker ps` empty → dumps `docker logs --tail 8`) or the whole-boot
  timeout (`BOOT_TIMEOUT_S = 900`). A crashed-but-alive game keeps the container up, so it waits the
  full budget.
- `preview_batch.travel` (`uedcli/game/preview_batch.py:193`) runs in-container: phase 3 polls
  `current_level()` for up to `timeout` (480s) and then raises the generic
  `"never possessed a pawn on %r within %ds"`. On a `Critical Error` the link socket never re-listens
  on 7777, so `current_level()` returns `None` forever and this is exactly the wait that burns.

The engine writes the crash to `DeusEx.log` (in-container at `/work/dx/System/DeusEx.log`) with a
`Critical:`/`Exiting due to error`/`History:` backtrace, and the modal window is titled `Critical
Error` on `:99`. The entrypoint's boot loop (`game-entrypoint.sh:118`) likewise only reports the
generic `link never bound` when a boot-time crash wedges the link.

## Design (the fix)

Detect a game-side crash and surface it wherever we currently wait blindly for the link. Both signals
are reachable in-container from `preview_batch.py`:

- LOG (primary — carries the real error): scan `DeusEx.log` for the first `Critical:` /
  `Exiting due to error` line and the following `History:` backtrace chain. This is the message that
  actually tells the operator what broke.
- WINDOW (secondary — cheap liveness): `xdotool search --name "Critical Error"` on `:99` confirms the
  process is wedged on a modal even if the log flush lags.

Wire it into the poll loops so a crash short-circuits the long wait:

- In `preview_batch.travel`, each poll iteration (all three phases) also checks for a crash; on a hit,
  raise a NAMED error carrying the extracted `Critical:` line + `History:` chain instead of waiting
  out the 25s/60s/480s deadlines.
- The raised error propagates as today: `preview_batch` emits it / exits non-zero, `run_batch`
  surfaces the batch error, and `render_shots` turns it into a `GamePreviewError` → exit 2. A crash
  is PERMANENT — it must NOT trigger a reboot-retry that would just re-crash and re-wait; treat it
  like the existing `"actor not found"` non-retryable guard (`preview_game.py:690`) so the real error
  reaches the user on the first crash, not after `REBOOT_BUDGET` re-crashes.
- Give `preview_game._wait_ready` the same crash check during its boot poll (log/window), so a
  boot-time crash fails fast with the engine error rather than at `BOOT_TIMEOUT_S`.

Message shape: `game crashed: <Critical: line>` followed by the indented `History:` chain, one exit-2
error. Extraction must degrade cleanly — a truncated/absent log yields "game crashed (no error text
captured)" rather than a traceback.

## Edge cases & errors

- Crash vs slow-but-healthy boot: only a crash SIGNAL (log `Critical:`/`Exiting due to error`, or the
  `Critical Error` window) short-circuits — a growing-but-slow log must still wait (the entrypoint's
  existing progressing-boot logic). Do not treat generic `Warning:` lines as crashes.
- `Failed to spawn player actor` is the recorded instance (a `PlayerStart`-less or solid/uncarved
  level, `unrealed/quirks.md` "How brushes enter the level"). The model-side `trunk_has_playerstart`
  pre-check (`preview_game.py:209`) already catches the missing-PlayerStart case for trunk previews;
  this handles the ones that only surface in the running engine (retail `--map`, uncarved geometry).
- Never let a raw exception reach the user (`CLAUDE.md`): a log-read/xdotool failure during detection
  falls back to the existing timeout error, it does not crash the detector.
- Hang-detector discipline still applies to the surrounding waits (`rules/background-work.md`).

## Tests / how it's pinned

- OFFLINE unit test of the log-scan extractor: feed a captured `DeusEx.log` tail with a
  `Critical: … / History: …` block and assert it yields the named error + backtrace; feed a clean
  boot log and assert no false positive.
- OFFLINE test that a crash error is classified non-retryable (no reboot-retry) in the
  `render_shots` loop, parallel to the `"actor not found"` guard.
- A committed golden `DeusEx.log` fragment (the `Failed to spawn player actor` crash) under
  `fixtures/`, cited from the extractor test.

## Open questions

- Detection source and where it fires — log-scan, window-title, or both; travel poll only, or the
  boot poll too. See `questions/`.
