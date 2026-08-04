# Spike: bypass the retail CD check and boot DeusEx.exe to a preview frame under FEX+wine-10 (2026-08-04)

**Question.** The parent spike (`2026-08-04-deusex-fex-wine10-rpcss`) got `DeusEx.exe` booting under
FEX+wine-10 to the engine banner, then blocked on the retail **CD check** (minimal set) or the **6 GiB
memory cap** (full set). Bypass the CD check on a right-sized package set, hold memory under the cap,
reach the UedPreview `:7777` link, and render `game_preview_here.png`.

## TL;DR — both named walls cleared; a third wall (DeusEx's own Entry→DX boot travel) blocks `:7777`. No frame — not faked.

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
