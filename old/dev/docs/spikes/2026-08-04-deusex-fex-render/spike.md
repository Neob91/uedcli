# Spike: render `DeusEx.exe` under FEX-emu (native arm64 x86 JIT), not qemu (2026-08-04)

**Question.** qemu-i386 deadlocks wine's wineserver IPC at boot; box64's experimental BOX32 can't
carry `DeusEx.exe`'s init (`2026-08-04-deusex-box86-box64-render`). FEX-emu JITs x86 to native arm64
(no aarch32, no qemu). Can FEX run a *minimal* wine — services trimmed, since DeusEx uses no COM/OLE —
so `DeusEx.exe` fits under the host's shared `pids.max=512`, binds the UedPreview link on `:7777`, and
renders a frame?

## TL;DR — FEX escapes the qemu CPU wall, but wine's OWN prefix bring-up fork-storms under FEX, and the shared pid cap is saturated by co-tenants. No frame.

- **FEX runs x86 wine natively here — confirmed.** FEX guest `uname -m` = `x86_64`; `wine --version`
  → `wine-8.0`. No qemu in the loop. The qemu-i386 crash class is escaped.
- **Any real Win32 launch fork-storms `wineboot.exe`.** On the pre-built prefix, `wine cmd` /
  `wineboot -u` climb ~4→99 tasks in ~1.5 s and fail `rc=53`. Root cause is wine's OLE cross-process
  marshaling failing under FEX: `ole:CoMarshalInterface ... hr 0x80004002 (E_NOINTERFACE)`,
  `ole:start_rpcss Failed to open service manager`. This is the exact FEX wall the KHSimulator
  write-up hit (`/workspace/plc/docs/khsimulator-wine-crash.md`). It is in wine's **own** service
  bring-up, **upstream of the app** — so "DeusEx needs no COM/OLE" does not help, and no
  `WINEDLLOVERRIDES` (tested: `mscoree,mshtml,winemenubuilder,plugplay=`), persistent `wineserver`,
  or `DISPLAY` stops it.
- **A fresh prefix doesn't storm but can't load kernel32.** `wineboot -i` on a fresh `WINEPREFIX`
  (WINEDLLPATH set to the guest x86 PE dirs) → single `wineboot.exe`, then `could not load
  kernel32.dll, status c0000135`, `rc=53`. A separate FEX/WoW64 init wall.
- **`pids.max=512` is shared and immovable.** `--pids-limit` is ignored (fresh `alpine`
  `--pids-limit=4096` still reads `pids.max=512`); every container reads the *same* `pids.current`.
  It is consumed by co-tenants — another session's qemu `dxboot*` DeusEx attempts (70–77 tasks each),
  the owner's `sim-stack` co-sims, and the rootless-Docker infra. Measured `pids.current` swung
  362 → 466 → 498 → **a sustained 512/512** that blocked even `docker exec` into my own container for
  >7 min.
- **`DeusEx.exe` never bound `:7777`.** Launch at `pids.current=501/512` → wine's first `fork` failed
  immediately (my wine stuck at 8 tasks, `DeusEx.log` 0 lines). A retry at 425/512 started a wine
  process, but the slice re-saturated to 512/512 (a co-tenant storm) before it progressed;
  `DeusEx.log` was never written. **No frame rendered — not faked.**

## The wall, with numbers (`evidence/pids-and-boot-results.txt`)

```
FEX guest uname -m            x86_64            # native x86 on arm64, no qemu
wine --version               wine-8.0
alpine --pids-limit=4096     pids.max=512       # limit ignored; cap is the shared slice
wine cmd / wineboot -u       4 -> ~99 tasks/1.5s, rc=53   # wineboot.exe fork-storm (E_NOINTERFACE)
fresh-prefix wineboot -i     could not load kernel32.dll c0000135, rc=53
DeusEx.exe @ 501/512         fork fails, DeusEx.log=0 lines, :7777 unbound
shared pids.current          362 .. 498 .. 512/512 sustained (co-tenant dxboot* storms)
```

The storm errors verbatim: `evidence/fex_wineboot_storm_errors.txt`. The `c0000135`:
`evidence/fresh-prefix-c0000135.txt`.

## Why the mission's lever doesn't reach

The plan was to disable wine's service stack (rpcss/services/plugplay) because DeusEx uses no
COM/OLE. But the fan-out that matters is not the app's — it is `wineboot`'s. On every cold launch,
wine runs `wineboot`, which starts `services.exe` → `rpcss`; `rpcss`'s OLE marshaling returns
`E_NOINTERFACE` under FEX, so the service never comes up, `wineboot` retries, and the retries
fork-bomb `wineboot.exe` to the pid cap. There is no wine-8.0 knob that skips the rpcss attempt, so
the app is never reached. wine-9/10 handles COM under new-WoW64 differently and a newer FEX has wine
IPC fixes — neither is available in this rootfs (its wine is 8.0; its `wine64:amd64` 9.0 package is
half-installed, `iU`).

## Environment / repro

- Native arm64 (`uname -m` = aarch64). FEX from `fextest-img:latest` (`/usr/bin/FEXInterpreter`,
  `FEXBash`); RootFS = `/root/dtools-rootfs`, an exported Debian x86 wine-8.0 userland baked into that
  image. Config `~/.config/fex-emu/Config.json` → `{"Config":{"RootFS":"dtools"}}`.
- Gotchas that cost time, pinned here so the next run skips them:
  - `docker exec` **without `-i` silently discards heredoc stdin** → 0-byte scripts that "run" but do
    nothing. Use `docker cp` to place guest scripts, or `docker exec -i`.
  - FEX presents `RootFS` as guest `/` for **reading** (scripts under
    `/root/dtools-rootfs/tmp/x.sh` are guest `/tmp/x.sh`), but routes guest `/tmp` **writes** to the
    container's real `/tmp`. Read outputs from container `/tmp`, not the RootFS tree.
  - The recipe's `WINEDLLPATH` dirs (`/usr/lib/{i386,x86_64}-linux-gnu/wine/*-windows`) exist **only
    inside the guest** (the RootFS), not on the container fs — check them with `FEXBash`, not
    `docker exec ... ls`.
  - FEX guest threads do not reap promptly after `pkill`; the only clean reset is recreating the
    container.
- Harness: `harness/wcmd.sh` `wboot.sh` `wboot2.sh` `wsrv.sh` `wfresh.sh` (the five wine-cost probes),
  `harness/dxlaunch2.sh` (the DeusEx launch). Each host driver measured my container's own task count
  (clean attribution) and the shared `pids.current`, with a guard that kills on climb to protect
  co-tenant containers.

## Not pinned with a test

Per `rules/spikes.md`, this is an environmental/tooling wall (like `deusex-box86-box64-render` and
`deusex-boot-wedge`), not a stable fact about the binary or a golden. The re-runnable harness +
captured numbers are the committed artifact.

## Bottom line

FEX clears the qemu CPU-emulation crash (native x86 wine-8.0 runs). It does **not** clear wine's
IPC/OLE under FEX: `rpcss` marshaling fails `E_NOINTERFACE`, so wine's `wineboot` fork-storms before
any app runs, and a fresh prefix hits `c0000135` instead. Compounding it, the shared `pids.max=512`
is saturated by co-tenant containers (another live qemu-DeusEx session + the co-sims + Docker infra),
so even a working minimal wine would have no headroom. `DeusEx.exe` did not bind `:7777`; no frame.
Forward paths, none available in-sandbox: newer FEX + wine-9/10 (new-WoW64 COM), or a real arm64 host
without the nested-rootless pid cap and without competing sessions.
