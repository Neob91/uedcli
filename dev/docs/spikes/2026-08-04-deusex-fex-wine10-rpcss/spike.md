# Spike: does wine-10 clear the rpcss/OLE wall under FEX? (2026-08-04)

**Question.** `2026-08-04-deusex-fex-render` found that FEX runs x86 wine natively here (escaping the
qemu-i386 deadlock), but wine-**8**'s prefix bring-up fork-storms under FEX: `wineboot` climbs to ~99
tasks and fails `rc=53`, root-caused to `rpcss`/OLE marshaling returning `E_NOINTERFACE (0x80004002)`.
That spike's forward path named wine-9/10 (new-WoW64 COM) as the likely fix. Build a wine-**10** x86
userland, run it under the same FEX, and settle it: does wine-10 clear the wall — and if so, does
`DeusEx.exe` boot and render?

## TL;DR — wine-10 clears the wall. `wineboot` completes, IPC works, no fork-storm. DeusEx boots under FEX+wine-10 through full engine init but is blocked short of the `:7777` link by the retail CD check (minimal set) or the immovable 6 GiB memory cap (full set). No frame — not faked.

- **Step 1 (the make-or-break): YES.** Under FEX, x86 `wine-10.0`:
  - `wineboot -u` → **`rc=0`** (wine-8 was `rc=53`). A **warm** second `wineboot` is also `rc=0`.
  - `wine cmd /c echo` → prints, **`rc=0`**, deterministic **3/3** (wine-8 fork-stormed and failed).
  - `services.exe` stays running (`Ssl`); the prefix is fully populated.
  - **No fork-storm**: pids peaked **≤127** (wine-8 stormed to ~99 tasks *and* died).
  - Honest nuance: the same transient error *strings* still appear early
    (`apartment_get_local_server_stream Failed: 0x80004002`, `start_rpcss Failed to open RpcSs
    service`, a couple of reaped zombie `rpcss.exe`). Under wine-8/FEX these cascaded into the
    terminal fork-storm; under wine-10/FEX they are the **normal lazy-start race** — wine recovers,
    `services.exe` brings the endpoint up, and the boot completes. The wall that blocked the app (the
    storm + `rc=53`) is gone. Evidence: `evidence/step1-rpcss-cleared.txt`, `evidence/rpcss-sequence.txt`.
- **A second wall, orthogonal to wine version, also had to fall: `c0000135`.** A fresh prefix under
  FEX died `could not load kernel32.dll, status c0000135` for *both* wine-8 and wine-10. Cause: FEX
  serves RootFS files to the ELF loader, but wine's runtime **guest `open()`** for PE dlls hits the
  host container fs directly (no RootFS fallback), so `…/i386-windows/kernel32.dll` returned
  `c000003a`. Fix: `dpkg-deb -x` the wine debs into **both** the RootFS **and** the container's real
  `/`. With the PE dlls on the real fs, kernel32 loads and `wineboot` proceeds.
- **Step 2 — DeusEx runs under FEX+wine-10, further/cleaner than qemu, but no frame.**
  `DeusEx.exe` connects to X (a native-arm64 `Xvfb` container over TCP) and boots through full engine
  init — `Bound to Engine.dll/Core.dll/Window.dll`, Name/Object subsystems, CPU-detect — to the
  21-line banner (`evidence/deusex-boot-banner.txt`). That is the *exact* point the qemu path was
  called a "lost-wakeup deadlock" in `2026-08-04-deusex-boot-wedge`; under FEX+wine-10 it is not a
  silent wedge — it pops a visible **"Cd Required At Startup"** dialog (retail CD copy-protection).
  The UedPreview `:7777` link binds *after* the CD check in engine startup, so the CD gate blocks it.
  - Minimal package set → the CD dialog is deterministic (memory-light).
  - Full retail `System` (satisfies deps; needed to get past `MissingIni`/`appInit` —
    `evidence/missing-ini-dialog.png`) → exhausts the **6 GiB** cap (`memory.current` 6.40/6.44 GiB,
    `memory.events max` in the thousands, then any fork OOM-killed `137`). This is the same immovable
    memory wall `deusex-boot-wedge` documented; `drop_caches` is denied so the 296 MB System's page
    cache can't be reclaimed.
  - **`DeusEx.exe` never bound `:7777`; no frame rendered.**

## The numbers

```
FEX guest uname -m           x86_64                 # native x86 on arm64, no qemu
wine --version               wine-10.0              # winehq wine-stable 10.0.0.0~bookworm-1, pinned
wineboot -u rc               0                      # wine-8 was 53
warm wineboot -u rc          0
wine cmd /c echo rc          0  (3/3 deterministic) # wine-8: fork-storm, failed
peak pids during wineboot    127                    # wine-8 stormed to ~99 AND failed
kernel32 load failures       0                      # after PE dlls placed on the real fs
DeusEx.exe under FEX+wine10   boots to 21-line banner, X window up, then CD dialog
DeusEx full-System boot       memory.current 6.40 / 6.44 GiB  -> OOM 137
DeusEx :7777 bind             never
```

## Verdict against the mission's two outcomes

Outcome **(A)**: wine-10 clears the rpcss/OLE wall under FEX. DeusEx then boots but is blocked short
of `:7777` — **not** by a pid cap (pids had headroom, ~90–400 free once the co-tenant `dxboot`
storm subsided), but by (i) the retail CD check on a minimal set and (ii) the 6 GiB memory cap on the
full set. Both are orthogonal to FEX/wine/rpcss. So: the CPU-emulation wall (qemu) and the IPC/OLE
wall (wine-8) are both cleared; what remains is DeusEx's own CD DRM and this box's memory ceiling.

## Not pinned with a test

Per `rules/spikes.md`, this is an environmental/tooling result (like the parent `deusex-fex-render`
and `deusex-boot-wedge`), not a stable fact about a binary or a golden — it can't run in CI (needs
FEX + a 6 GB container + an X host). The committed artifact is the re-runnable `harness/` plus the
captured numbers and logs in `evidence/`.

## Environment / repro

Native arm64 host. `fextest-img:latest` (`/usr/bin/FEXInterpreter`, `FEXBash`; RootFS
`/root/dtools-rootfs` = Debian bookworm x86 wine-8, FEX name `dtools`). `harness/README.md` has the
build (wine-10 via `dpkg-deb -x` into both fs), the launch, and the gotchas. Shared caps on this box
are immovable: `pids.max` 512 (co-tenant `dxboot*`/`sim-stack` churn), `memory.max` 6 GiB per
container, `drop_caches` denied. The Docker daemon also bounced ~every 15–20 min (all containers exit
255 together) — build state persisted because the containers were created without `--rm`.
