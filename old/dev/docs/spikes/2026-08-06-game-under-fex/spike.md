# Spike: can DeusEx.exe render a preview frame under FEX+wine-10 without the object-system corruption? (2026-08-06)

**Question.** `level preview --game` runs `DeusEx.exe` under wine. On arm64 the FEX+wine-10 runtime
(the one that makes the *editor* work — spike `2026-08-06-materialize-under-fex`) corrupts the object
system when the game loads a map via `ClientTravel`: `ULevel::PostLoad` access violation (our room),
`StaticAllocateObject`/`GObjAvailable` assertion (OG maps). The owner wants ONE runtime (FEX+wine-10)
for both editor and game. Can the game's corruption be solved? Lead to test first: is it render-device
/ OpenGL-related, like the editor's `SoftDrv` fix?

## TL;DR

The "corruption" is **not** intrinsic to FEX+wine-10 loading our content. **Our `room.dx` loads and
`PostLoad`s cleanly under FEX+wine-10 when loaded via the engine's BOOT map path** (`LoadMap: entry.dx`
→ `Bringing Level Entry.MyLevel up for play`, no crash). The crash is specific to the **runtime
`ClientTravel` path taken FROM the fully-loaded menu** (`DX.dx` → `room.dx`). So the fix direction is
*load the preview map through the boot path, not a runtime travel* — not a render-device or FEX-config
change.

Hypotheses tested and **ruled out** (all reproduce the identical `ULevel::PostLoad` fault):
- **`LIBGL_ALWAYS_SOFTWARE=1`** (the editor's env difference) — no effect. The game already uses
  `SoftDrv` render devices; forcing software GL changes nothing.
- **FEX memory-ordering** (`VectorTSOEnabled=1`, `Multiblock=0`) — no effect. Consistent with the
  fault being *deterministic* (an ordering race would be flaky).
- **`WINE_LARGE_ADDRESS_AWARE=1`** (the 2 GiB 32-bit VA ceiling — banner `Virt=2097024K`) — no
  effect; `Virt=` unchanged, same crash.

**Frame not captured.** Turning the "room as boot map" insight into a rendered frame is blocked by a
*separate, environmental* failure: a lost-wakeup boot-IPC wedge (`DeusEx.exe` idle at 0% CPU, log
frozen at the 21-line CPU-detect banner — the exact wedge `uedcli/game/game-entrypoint.sh` documents
and beats with a relaunch loop). In this session it hit ~100% of launches (likely concurrent load
from the parallel editor track + container churn), so no boot reached `:7777` to pose+grab room. This
is orthogonal to the object-system question.

## What was proven, with evidence

### 1. The crash reproduces exactly as documented (`evidence/00-primary-crash-stack.txt`, `01-baseline-crash-room.png`)
dx engine (`DeusExGameEngine`) boots the full menu (`Entry`→`DX`), binds `:7777`
(`evidence/00-menu-baseline.png`), responds `LevelName DX.dx`. `TravelToLevel room.dx` over the link →
link dies. Primary stack (before the reentrant `Double fault` flood that masks it):

```
Log: LoadMap: room.dx?...   Loading: Package room / Package Amark
Critical: ULevel::PostLoad          <- raw fault, no access-violation message
Critical: (Level room.MyLevel)  ... UGameEngine::LoadMap  LoadURL  Browse  ClientTravel  UGameEngine::Tick
```

### 2. Our room `PostLoad`s CLEANLY via the boot path (`evidence/expAp-room-bootloads.log`)
Install `room.dx` as `Maps/Entry.dx` (the engine's hardcoded first boot map), dx engine:
```
Log: LoadMap: entry.dx
Log: Bringing Level Entry.MyLevel up for play (0)...   <- room content, ULevel::PostLoad ran, NO crash
Log: Browse: DX.dx?...  LoadMap: DX.dx  Bringing Level DX.MyLevel up for play   <- onward travel ALSO ok
ScriptLog: UedPreviewLink(spike): listening on 7777
```
So room is FEX-valid; `ULevel::PostLoad` on room is fine. The asymmetry is the tell: `Entry(room)→DX`
(travel while only a small level is resident) **works**; `DX(menu)→room` (travel while the ~25-package
menu graph is resident) **crashes**. The corruption correlates with a `ClientTravel` load+GC while the
large menu content graph is resident — not with our map, not with `PostLoad` per se, and not with the
render device.

## Verdict on the owner's question (one FEX+wine-10 runtime for both)

Editor: already works under FEX+wine-10 (`SoftDrv`). Game: the object-system "corruption" is **not** a
blanket FEX incompatibility — it is confined to the runtime menu→map `ClientTravel`. The engineering
path to one runtime is to **reach the preview map through the boot `LoadMap`, not a runtime travel**:
- Boot the game with the preview map AS the boot map (`Entry.dx`), so it loads via the clean path.
- Prevent the hardcoded onward `Entry`→`DX` travel from carrying us into the menu (e.g. make the `DX`
  target unloadable so `Browse` fails and the engine rests in the boot level; **not yet confirmed the
  console keeps ticking / `:7777` binds in that resting state — the boot wedge blocked verifying it**).

Remaining true blocker for a *rendered frame* here is the environmental boot-IPC wedge, which is a
known, retry-beatable issue (see `game-entrypoint.sh`), not the corruption.

## Ruled out / still open

- Ruled out as the cause: `LIBGL_ALWAYS_SOFTWARE`, `SoftDrv` (already on), FEX VectorTSO/Multiblock,
  `WINE_LARGE_ADDRESS_AWARE`, audio subsystem (`AudioDevice=`/`UseDirectSound=False` — still wedged
  at the banner, so audio is not the wedge either).
- Open (blocked by the boot wedge, not disproven): does the engine rest in `Entry(room)` with `:7777`
  bound when the onward `DX` travel is made to fail? If yes, that renders our room via the clean path.
- Open: WHY the menu-resident `ClientTravel` corrupts under FEX but not qemu+wine-8 (VA
  fragmentation/exhaustion vs GC-over-large-object-set under FEX). The boot-path fix sidesteps it, so
  this is diagnosis, not a blocker.

## Harness (`harness/`, re-runnable)

Own docker namespace (network `fexnet-game`; containers `xdisp-game` native-arm64 Xvfb :99/TCP,
`fex-game` `fextest-wine10-dxfull` running `DeusEx.exe` under FEX, `driver-game` `dx-lum-uned-game`
for X screenshots + a reliable native `:7777` port-probe).
- `trial.sh` — boot the dx menu, `TravelToLevel <map>` over `:7777`, classify SURVIVED/CRASHED, dump
  the primary crash stack. Knobs: `LIBGL`, `WLAA`; FEX config via `~/.config/fex-emu/Config.json`.
- `boot_grab.sh` / `boot_grab2.sh` — boot via the BOOT-LoadMap path (install a chosen map as
  `Entry.dx`), then pose/clean over `:7777`. `boot_grab2` warms one persistent wineserver and retries
  DeusEx-only on a banner-wedge (keeping the server).
- `host_boot.sh` / `host_boot3.sh` — host-side orchestrators that poll `:7777` from `driver-game`
  (native python) instead of FEXBash `netstat` (which hangs), and kill DeusEx by exact name.
- `mkini.py`, `recipe_ini.py`, `drive_render.py` — seeded from the CD-bypass spike.

### Gotchas pinned so the next run skips them (cost real time here)
- **`pkill -9 -f DeusEx.exe` self-kills** the driver: the launch command line contains `DeusEx.exe`,
  so `-f` matches the driver shell. Kill by exact name: `pkill -9 -x DeusEx.exe`.
- **`docker restart`/recreate drops the i386 binfmt** → direct `wine` routes to a broken `qemu-i386`
  (`Could not open /lib/ld-linux.so.2`). Run every wine command via `FEXBash -c "wine …"` (explicit
  FEX, binfmt-independent). The game launch already does; maintenance (`wineserver -k`, `wineboot`)
  must too.
- **FEXBash `netstat` is slow/hangs under load** — poll `:7777` from a native container instead.
- **The host has no `pkill`/`ps`** — cannot kill host-side orchestrators by name; use TaskStop /
  disciplined single runs (concurrent orchestrators launch competing DeusEx and guarantee wedges).
- FEX-2607 rejects JSON keys `ParanoidTSO`/`MemcpySetTSO` (accepts `VectorTSOEnabled`, `Multiblock`);
  check `FEXGetConfig --tso-emulation-info`.
- FEX leaves DeusEx **zombies** after a kill (thread-reap); harmless (no port/memory) but they pile up
  and a dirty container's boots degrade — prefer a fresh `docker run` over `docker restart`.

## Not pinned with a test

Environmental/tooling result (needs FEX + a 16 GiB container + an X host), like the parent FEX spikes
— can't run in CI. The committed artifacts are `harness/` + `evidence/` (crash stack + PNGs +
`expAp-room-bootloads.log`). The one checkable behavioural fact — *room `PostLoad`s cleanly via the
boot map but crashes via menu `ClientTravel` under FEX* — should be pinned in the build phase that
wires the boot-path preview, against the committed `room.dx`.
