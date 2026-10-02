# Spike: can a minimal game root shrink DeusEx.exe under the 6 GiB cap and boot it? (2026-08-04)

**Question.** The `2026-08-04-deusex-boot-wedge` spike root-caused the `DeusEx.exe` boot wedge as a
lost-wakeup deadlock *triggered by memory pressure* — a fresh full-content boot fills the 6 GiB
container cap to 98%, and the reclaim churn stalls the wineserver startup IPC. The 6 GiB cap is
unraisable here. So the only remaining lever is to **shrink the guest working set below the cap with
headroom**: a bare textured-brush preview needs almost none of the DeusEx content. Does a minimal game
root (stock engine, no `DeusEx.u`/content, small `CacheSizeMegs`) drop memory well under 6 GiB, and
does that let it boot reliably?

## TL;DR — shrinking the footprint worked; it did NOT stop the deadlock

- **The footprint shrank a lot.** A minimal stock-engine root (Core/Engine/IpDrv + SoftDrv + one
  texture + `room.dx` + engine-only `UedPreview.u`, no `DeusEx.u`, no content, `CacheSizeMegs=4`) boots
  to a **peak `memory.current` of ~4.27 GiB (4 581 285 888 B, 71% of the 6 GiB cap, ~1.7 GiB headroom)**
  — versus 5.9–6.3 GiB / 98% for the full-content boot. Game root on disk: 6.2 MiB, 22 System files.
- **It still deadlocks.** Every boot wedges with the **same lost-wakeup signature** as the full boot:
  `DeusEx.exe` main thread parked in `pipe_read` (the wineserver reply pipe), `wineserver64` in
  `do_epoll_wait`, wine helper threads in `futex_wait_queue`, 0% CPU, `oom_kill=0`. `DeusEx.log` is
  frozen at **0 lines** (even earlier than the full boot's 21-line CPU-detect banner — the wedge is in
  the wineserver handshake *before* the game's main runs).
- **Reliability: 0/N. <!--LOOP_RESULT-->** Relaunch-until-a-boot-wins (the production
  `game-entrypoint.sh` mitigation) does not clear it: every attempt wedged at ~42 s, `mem≈4.3 GiB`,
  `wchan=pipe_read`, `loglines=0`.
- **Conclusion the owner needs.** The prior spike's "memory pressure *at the cap* is the trigger" model
  is too narrow: at **71% of cap with 1.7 GiB of headroom and `oom_kill=0`, the boot still wedges**. So
  either the trigger is not headroom-at-the-cap but the intrinsic major-fault churn of amd64-wine-under-
  arm64-qemu startup (this minimal boot still logs **~906 000 major faults**, essentially the same as
  the full boot), or the deadlock is not memory-triggered at all. Reducing the working set — the only
  lever available on this box — is **not sufficient** to boot the in-game preview here. The preview
  render path stays blocked on this host.

## Decisive evidence — minimal stock boot, `evidence/stock-1.sample.log` (t=58 s)

```
[min] game root: 6.2M, System files: 22
[min] ini: GameEngine=Engine.GameEngine DefaultGame=Engine.GameInfo Class=Engine.Camera cache=4 root=(none)
mem.current=4553383936  peak=4581285888   # 4.27 GiB peak, 71% of the 6 GiB cap
mem.events: ... max 68715 oom 0 oom_kill 0 oom_group_kill 0
pgfault=564300813 pgmajfault=906462        # ~906k major faults — same order as the full boot
loglines=0                                 # DeusEx.log never written — wedge is pre-game-main
  DeusEx.exe   tid=381 state=S wchan=pipe_read        # blocked on the wineserver reply
  wine         tid=407 state=S wchan=futex_wait_queue
  wineserver64 tid=421 state=S wchan=do_epoll_wait    # idle, request never arrives
```

`oom_kill=0` + all threads parked in wait wchans + faults not runaway = **deadlock, not OOM**, exactly
as the prior spike classified it — but now demonstrably **with memory headroom**, which removes
"pressure at the cap" as the sole explanation.

## Smallest footprint tested (boots to the same wedge, does not link)

Stock engine, no `DeusEx.u`. `Engine.u` provides concrete stock `Camera`/`Spectator` `PlayerPawn`
subclasses and a base `GameInfo`, so the DeusEx content graph (player `JCDentonMale` →
`DeusExCharacters`, `DeusExRootWindow` → `DeusExUI`, etc.) is never pulled.

- **System (22 files):** `Core.u Engine.u IpDrv.u`; `Core.dll Engine.dll Render.dll SoftDrv.dll
  WinDrv.dll Window.dll IpDrv.dll Galaxy.dll Fire.dll MSVCRT.dll`; the matching `.int`s; `DeusEx.exe`
  `DeusEx.ini`; plus `UedPreview.u`.
- **Maps/Textures:** `room.dx` (engine-only textured brush) + `Amark.utx`.
- **`DeusEx.ini`:** `GameEngine=Engine.GameEngine`, `DefaultGame=Engine.GameInfo`,
  `Class=Engine.Camera`, `Root` removed, `Console=UedPreview.UedPreviewConsole`,
  `RenderDevice=WindowedRenderDevice=SoftDrv.SoftwareRenderDevice`, `CacheSizeMegs=4`,
  `WindowedViewportX/Y=640/480`, `FirstRun=400`; `-nosound`.

`CacheSizeMegs` was not the lever — the working set is dominated by mmap'd file pages
(`file≈3.3 GiB`) and the qemu/wine emulation baseline, not the engine object cache; 4 MiB already
wedges with headroom, so raising or lowering it changes nothing about the deadlock.

## Render — not captured

The generic stock-field clean render (`render_frame.py`: pose the `Engine.Camera` pawn at room
centre, `Clean generic`, X-grab the SoftDrv window to `game_preview_here.png`) is wired and ready, but
no boot linked `127.0.0.1:7777`, so there is no frame to grab. This is an **environment wall, not a
harness gap** — the same `UedPreview.u`/link/room rendered on 2026-08-03 at a lower-pressure moment
(board `engine-only-uedpreview-via-regular-ucc-renders`). The in-game preview cannot be booted on this
box even at minimal footprint.

## Not pinned with a unit test

Per `rules/spikes.md`: the result is an environmental/timing wall, not a stable fact about the binary
or a golden. The re-runnable harness + captured `memory.current`/wchan evidence are the committed
artifact. The one checkable *binary* fact used here — `Engine.u` ships concrete stock `Camera`/
`Spectator` `PlayerPawn` subclasses and a base `GameInfo`, so a stock-only boot needs no `DeusEx.u` —
could be pinned against `dev/games/dxreal/system/Engine.u`, but that boot never completed, so the
claim is only schema-level (the class-name strings are present) and is left as prose.

## Files

- `harness/minimal_boot.sh` — assemble a minimal (`stock`/`dx`/`full`) game root, patch `DeusEx.ini`,
  boot once, sample `memory.current`/events/per-thread wchan each interval; classifies link/wedge/error.
- `harness/min_trial.sh` — host driver: fresh container, stage inputs, run `minimal_boot.sh`, copy logs.
- `harness/relaunch_loop.sh` — assemble once, relaunch up to `MAXTRIES` times (re-roll the race), render
  on the first link. `harness/relaunch_host.sh` — its host driver.
- `harness/render_frame.py` — pose + generic clean + X-grab to `game_preview_here.png` (unused: no link).
- `evidence/stock-1.sample.log`, `stock-1.console.log` — the minimal-boot wedge with 4.27 GiB peak.
- `evidence/relaunch.console.log` — the relaunch-loop tally. <!--LOOP_EVIDENCE-->
```
