# Spike: bypass the retail CD check and boot DeusEx.exe to a preview frame under FEX+wine-10 (2026-08-04)

**Question.** The parent spike (`2026-08-04-deusex-fex-wine10-rpcss`) got `DeusEx.exe` booting under
FEX+wine-10 to the engine banner, then blocked on the retail **CD check** (minimal set) or the **6 GiB
memory cap** (full set). Bypass the CD check on a right-sized package set, hold memory under the cap,
reach the UedPreview `:7777` link, and render `game_preview_here.png`.

## TL;DR — a real DeusEx frame RENDERS under FEX+wine-10 (no patch). Both named walls cleared; the room-specific in-game preview is still blocked (map + FireTexture).

**Real frame captured — `evidence/game_preview_deusex_menu.png`** (deterministic, md5 `4fe486ca`, 3/3
identical grabs): the Deus Ex main-menu 3D logo (wing + Earth globe), SoftDrv-rendered by retail
`DeusEx.exe` (game **v1.112fm**) booting its **real menu** under FEX+wine-10, with the
`UedPreview.UedPreviewConsole` link bound on `:7777`. Route (matches the 2026-08-03 recipe, no binary
patch): stage the **full** DeusEx content graph (System + Textures + Sounds + Music + real `Entry.dx`/
`DX.dx` menu maps), `ENGINE=dx` (`DeusExGameEngine`), `CacheSizeMegs=4`, `-nosound`; the forced
`Entry`→`DX` travel now **succeeds** into the real menu (both levels "up for play"), the console spawns
`UedPreviewLink: listening on 7777`, `GetCurrentLevelName`/`Clean generic` work, and `import` X-grabs
the SoftDrv viewport. Peak `memory.current` **~6.10 GiB / 6.144 GiB cap, oom_kill=0**. The
`Anomalous singularity`/FireTexture render warnings are non-fatal for the menu.

**Still blocked: travelling to OUR textured preview room.** `TravelToLevel room.dx` over the link is a
real `ClientTravel` that *does* `LoadMap` our map (unlike the startup browse) but then dies two ways:
(1) our uedcli/editor-built maps crash the DeusEx engine in `ULevel::PostLoad` (`(Level room.MyLevel)`,
raw access violation, no message) while a **real** DeusEx map (`Entry.dx`) loads fine — so our maps
aren't DeusEx-engine-native (need a real DeusEx-editor build + real textures, not uedcli `Amark`);
(2) with `Class=DeusEx.JCDentonMale` the travel spawns JCDenton's inventory, and SoftDrv crashes
rendering `FireTexture Effects.Electricity.Nano_SFX` on `LodMesh DeusExItems.LaserBeam`
(`TravelPostAccept` → `SpawnPlayActor`, `evidence/travel-firetexture-crash-stack.png`). Setting
`[DefaultPlayer] Class=Engine.Camera` does **not** help — `DeusExGameInfo` forces `JCDentonMale`
regardless (`Possessed PlayerPawn: JCDentonMale`). In the menu the same FireTexture error is caught by
the guarded render loop and recovered; during a travel it fires in an unguarded `ProcessEvent` path and
is fatal. So under the DeusEx engine the **menu is the only stable render state**; rendering our
textured room needs a DeusEx-editor-native map AND a way past the JCDenton FireTexture crash (a game
whose `GameInfo` allows a spectator, or a renderer that survives `Effects.Electricity.Nano_SFX`).
Note the stock engine loads our room fine but is blocked by the Entry→DX travel (binary patch,
permission-denied) — so neither engine currently renders our own room.

## Follow-up: can the dx engine travel to ANY preview level? No — the travel-load wall

After the menu binds `:7777`, `TravelToLevel <map>` over the link crashes for every fresh target,
each differently, while only the pre-cached intro `Entry.dx` survives PostLoad:

| Travel target                     | Result |
|-----------------------------------|--------|
| our synthetic `room.dx`           | `ULevel::PostLoad` access violation (no message) |
| tiny **native** `DXOnly.dx` (has `DeusExLevelInfo`, deps already menu-loaded) | **also** `ULevel::PostLoad` — so it's not the LevelInfo class, and not new-content volume |
| real mission `08_NYC_Bar.dx` (pulls NewYorkCity/UNATCO/FreeClinic/…) | `Assertion GObjAvailable … StaticAllocateObject (Class PathNode)` — object-alloc exhaustion |
| `Entry.dx` (intro, content pre-cached from boot) | PostLoad OK ("up for play"), then the JCDenton FireTexture render crash |

At the menu, `memory.stat` is **anon 822 MiB / file 4983 MiB, oom_kill=0** — so it is **not** the cgroup
OOM-killer. It's process-internal allocation failure: the 32-bit `DeusEx.exe` sits near its ~2 GiB
virtual address space (banner `Virt=2097024K`) after mmapping the ~25 menu packages + wine DLLs under
FEX, so a travel's load/`StaticAllocateObject` fails and corrupts the object system. `Entry.dx` escapes
only because its content is already resident. Evidence: `evidence/boot-dxengine-travel-crashes.log`.
(The 2026-08-03 recipe rendered a room under **qemu** with **minimal** content staged and game **v68**
— our `dxreal` reports **v1.112fm** in-game and ignores `LocalMap=room.dx` at boot, always going
Entry→DX; harness `harness/recipe_ini.py`/`fex_recipe.sh` reproduce the recipe config faithfully and
still land in the menu.)

**Net:** under FEX+wine-10 the dx engine binds `:7777` and renders the **menu** (delivered frame), but
cannot travel to any preview level here — travel-load hits the 32-bit address-space / 6 GiB-cap wall.
Rendering **our** textured room needs the stock engine (loads our room fine) past its Entry→DX travel
(the permission-denied binary patch), or a from-scratch DeusEx-native room built so it loads without a
fresh content pull — neither reachable in this session without the patch grant or a much larger build.

## (Prior finding, superseded by the above for the dx engine) — both named walls cleared; DeusEx's own Entry→DX boot travel blocks `:7777` under the STOCK engine.

- **CD check (Wall 1): cracked and bypassed.** The retail `DeusEx.exe` (engine v1100, Jan 2001 build —
  **not** GOG/no-CD; `dxreal` is retail) CD check is a single `GFileManager->FileSize` probe for
  **`<CdPath>\Textures\Palettes.utx`**; size `> 0` ⇒ CD present. `CdPath=..\` resolves to the game root,
  so **staging `Palettes.utx` (412 KB) into the game-root `Textures/`** clears the "Cd Required At
  Startup" dialog. Full disassembly: `evidence/cd_check_decode.txt`. (Bonus: the same check is skipped
  outright when `GIsEditor != 0` — why the ucc/editor preview path never hit this wall.)
- **Memory (Wall 2): fits with headroom in a clean container.** Stock-engine + full retail `System`,
  `CacheSizeMegs=4`, mono/gecko disabled, **fresh** container: peak `memory.current` **~5.87–6.11 GiB**
  vs the 6.144 GiB cap, **`oom_kill=0`**, stable. The parent spike's 6.44 GiB OOM was the accumulated
  page-cache of a reused container plus the first-run Wine-Mono GUI install; neither is intrinsic. The
  full `System` (not stock-minimal) is required to clear `MissingIni`/`appInit` (`evidence/err-1`).
- **DeusEx boots deeper than any prior attempt here**: past CD + recovery-mode + the entry map, to
  `Bringing Level Entry.MyLevel up for play` with a spawned `Engine.Camera` player and the game viewport
  window open — then dies.
- **Wall 3 (new, orthogonal to FEX/CD/memory): DeusEx's `UGameEngine` auto-travels `Entry`→`DX.dx`
  and that game-travel is rejected.** After the entry map comes up, the engine browses a **hardcoded**
  `DX.dx` (its standalone default start map) — ignoring `[URL] Map`/`LocalMap` in every ini *and* the
  command-line URL — and fails **before** `LoadMap` with an empty reason (`Failed to enter DX.dx: `,
  `evidence/err-3`, `evidence/boot-log-flushed-dx-dx-fail.log`). The `UedPreviewConsole` never ticks to
  spawn the link, so **`:7777` never binds and no frame renders.** This is a DeusEx boot-sequence quirk,
  not a CD or memory wall; prior spikes never reached it (they wedged on memory first), so the
  `render_frame`/minimal-boot game-boot path was never actually validated end-to-end.
- **Two follow-up fixes tested and disproven:**
  - *Rename the room to `DX.dx`* (make the forced-travel target be our room): **does not work.** With
    `Maps\DX.dx` = our room (byte-identical to the `Entry.dx` that loads fine), the browse still fails
    with **no `LoadMap: DX.dx` / `Loading: Package DX` line** — `UGameEngine::Browse` rejects the travel
    *before* loading our map, so the map content is irrelevant. Disassembly of `Browse`
    (`Engine.dll` @ `0x1038b0fb`) shows a local map with a level already "up for play" takes the
    server/network-travel dispatch, not a direct `LoadMap`. Not a filename/case/path issue: `DX.dx` is
    found by the same resolver that found `Entry.dx`.
  - *Use the real DeusEx engine* (`DeusEx.DeusExGameEngine`, a real `GameInfo`): **needs the full
    content graph.** Init dies at `StaticLoadClass`/`InitEngine` with `Can't find file for package
    'Effects'` — `DeusExItems`→`Effects.utx` (a texture package) isn't staged; the real boot pulls the
    whole DeusEx content tree, and `DX.dx` is then the real menu map (overwriting it with our room
    defeats the menu boot). Memory still fit (peak 6.08 GiB). Evidence:
    `evidence/boot-dxengine-effects-missing.log`.
- **Option (a) — neuter the forced travel by binary-patching `Engine.dll` — designed but BLOCKED by the
  permission system.** The minimal patch: make `UGameEngine::Browse` (VA `0x1038ad30`, file `0x8ad30`)
  return success without traveling — `55 8b ec 6a ff 68 2a fe` → `b8 01 00 00 00 c2 4c 00`
  (`mov eax,1; ret 0x4c`) — so the `Entry`→`DX.dx` auto-travel is a no-op and the engine stays in the
  already-up Entry level (our room), where `UedPreviewConsole` can bind `:7777`. Script:
  `harness/apply_engine_patch.py`. The Claude Code permission classifier **denies** running it (patching
  a game binary reads as DRM circumvention). Per `CLAUDE.md`, an agent's sanction is not user consent —
  only the user or the permission system is — so this needs the user's explicit go-ahead; not evaded.

## The bypass chain (each step pinned by an error the previous one produced)

| Symptom (dialog / log)                    | Cause                                             | Fix |
|-------------------------------------------|---------------------------------------------------|-----|
| `Cd Required At Startup`                  | `FileSize(<CdPath>\Textures\Palettes.utx) == 0`   | stage `Palettes.utx` in game-root `Textures/` |
| `MisingIni`, `History: appInit`           | stock-minimal `System` missing appInit deps       | stage the full retail `System` (94 files, 296 MB) |
| `Deus Ex Recovery Mode` (modal)           | stale `Running.ini` (killed session never cleared)| `rm -f Running.ini` before each launch |
| `Failed to enter Entry: entry.dx`         | `UGameEngine::Init` browses hardcoded `Entry` first| provide `Maps/Entry.dx` |
| `Failed to enter DX.dx:` (empty reason)   | forced `Entry`→`DX.dx` game-travel is rejected     | **unsolved** — see Wall 3 |

## Numbers (clean container, stock engine + full System, CACHE=4)

```
wine --version              wine-10.0             # rebuilt via setup_all.sh (dpkg-deb -x into rootfs AND real /)
CD dialog with Palettes.utx GONE               # was deterministic without it
peak memory.current         5.87 – 6.11 GiB / 6.144 GiB cap,  oom_kill=0
boot reaches               "Bringing Level Entry.MyLevel up for play", Engine.Camera spawned
then                        Browse: DX.dx?Name=Player?Class=Engine.Camera  ->  Failed to enter DX.dx:
:7777 bind                  never
frame                       none
```

## Not pinned with a test

Environmental/tooling result (needs FEX + a 6 GB container + an X host), like the parent spikes — can't
run in CI. The re-runnable `harness/` plus captured logs/PNGs in `evidence/` are the committed artifact.
The one checkable *binary* fact — the retail v1100 CD check is a `FileSize` probe for
`Textures\Palettes.utx` at `CdPath` — is documented in `evidence/cd_check_decode.txt` against the
committed `dev/games/dxreal/system/DeusEx.exe`; left as prose (the game binary isn't in CI either).

## Environment / repro

Native arm64 host, Docker. Two containers on one user network (`fexnet`):
- **fex** — from `fextest-img:latest` (FEX-emu + Debian-bookworm x86 wine-8 RootFS at `/root/dtools-rootfs`,
  RootFS name `dtools`). `harness/setup_all.sh` builds the wine-10 x86 userland; `harness/fex_launch.sh`
  stages/launches; `harness/mkini.py` patches `DeusEx.ini`. Game root on the **real fs** at `/game`.
- **xdisp2** — native-arm64 Ubuntu running `Xvfb :99 -listen tcp -ac`; `fex` renders to it over TCP
  (`DISPLAY=<xdisp2-ip>:99`).

Gotchas that cost time, pinned so the next run skips them:
- Fresh Wine prefix + `DISPLAY` set ⇒ the **Wine-Mono GUI installer** pops and stalls; disable with
  `WINEDLLOVERRIDES=mscoree=d;mshtml=d` and boot the prefix once headless (no `DISPLAY`).
- The `[URL]` browse map/class come from **`Default.ini` + `User.ini`** (`[DefaultPlayer]`), not just
  `DeusEx.ini` — but even patching all three doesn't move the browse off the hardcoded `DX.dx`.
- FEX guest threads don't reap after `pkill`/`wineserver -k`; page cache doesn't drop (denied). A dirty
  container starts near the cap and wedges — **launch each attempt in a fresh container** for a true peak.
- The Docker daemon bounces periodically (containers exit 255, user networks vanish). Bake progress into
  a committed image (`docker commit`) so a bounce doesn't lose the wine-10 build / staged game.
