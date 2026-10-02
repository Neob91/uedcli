# Spike: run retail x86 `DeusEx.exe` on this arm64 host via box86/box64, not qemu (2026-08-04)

**Question.** The qemu-user path deadlocks in wine's wineserver IPC at boot (~0/48 binds — a
lost-wakeup; see `2026-08-04-deusex-boot-wedge`). Can box86/box64 (ptitSeb, purpose-built to run
Win32 games on arm64) run `DeusEx.exe` instead, bind the UedPreview link on `:7777`, and render a
frame?

## TL;DR

- **box86 is impossible on this host — a hardware wall, not a config.** box86 is an *armhf* (32-bit
  ARM) binary. This CPU is Apple Silicon (cpuinfo features `jscvt`, `paca`/`pacg`, `dcpodp`), which
  implements no AArch32 EL0. A 32-bit ARM binary here is caught by a `qemu-arm` binfmt handler that is
  registered precisely *because* native aarch32 can't run. So "box86" could only ever run
  under qemu — the layer the mission set out to escape.
- **box64 is the right tool and its stack works, qemu-free.** box64 is a native arm64 binary. Built
  from source with `-DBOX32=ON`, it ran, in order: an x86_64 hello, an i386 hello (via BOX32), the
  x86 wine loader (`wine-8.0`), and `wine cmd /c echo` — the full wineserver IPC roundtrip that
  deadlocks under qemu. None of this touches qemu. Evidence: `evidence/box-stack-proof.txt`.
- **`DeusEx.exe` does NOT boot under box64+box32 — deterministic, and it fails earlier than qemu.**
  3/3 boots: the process starts but writes **zero** `DeusEx.log` lines and never binds `:7777`
  (`evidence/deusex-reliability.result`). qemu at least reached the 21-line CPU-detect banner and
  bound occasionally; box32 dies/wedges before the game opens its log. So it is not the qemu
  coin-flip — it is a consistent wall.
- **Cause = BOX32 is experimental and its i386 glibc-symbol coverage is incomplete.** Multiple wine
  modules fail PLT relocation under box32 (`evidence/box32-reloc-errors.txt`), the load-bearing one
  being **`nsiproxy.so`** (wine's network layer): `if_nameindex` / `if_freenameindex` not found. Also
  `libsystemd` (`__openat64_2`), `libkrb5` (`res_nsearch`), `libgbm` (`drmGetDevice2`). A broken
  `nsiproxy` alone would block the `:7777` listen even if the renderer came up. The BOX32 option help
  says "experimental, do not use"; this is that.
- **No frame rendered.** The wall is upstream of rendering: the game never initialises far enough to
  bind the link the pose/grab step drives. Not faked.

## Trivial-stack proof (all qemu-free — `evidence/box-stack-proof.txt`)

```
# box64 --version:        Box64 arm64 v0.4.5 5656dec with Dynarec ...
# box64 ELF machine:      AArch64
# box64 runs x86_64:      HELLO ... sizeof(long)=8
# box32 runs i386:        HELLO ... sizeof(long)=4
# box64 runs x86 wine:    wine-8.0 (Debian 8.0~repack-4)
# box64 wine cmd /c echo: BOX64_WINE_IPC_OK      <- the IPC path qemu deadlocks on
```

## `DeusEx.exe` result — 3/3 identical (`evidence/deusex-reliability.result`)

```
trial=1 maxlog=0 bound=0 proc_alive_at_end=1 t~80s
trial=2 maxlog=0 bound=0 proc_alive_at_end=1 t~80s
trial=3 maxlog=0 bound=0 proc_alive_at_end=1 t~80s
```

`maxlog=0`: the game never wrote a log line. `bound=0`: `:7777` never came up. The process stays alive
(wedged), unlike a clean crash. Config was the proven `minimal_boot.sh` recipe (stock `GameEngine`,
`SoftDrv`, `UedPreviewConsole`, minimal System set), ported from `qemu wine` to `box64 wine`.

## The box32 relocation failures (`evidence/box32-reloc-errors.txt`, ANSI-stripped)

```
[BOX32] Error: Symbol if_nameindex not found ... in .../wine/i386-unix/nsiproxy.so
[BOX32] Error: Symbol if_freenameindex not found ... in .../wine/i386-unix/nsiproxy.so
[BOX32] Error: relocating Plt symbols in elf nsiproxy.so
[BOX32] Error: Symbol __openat64_2 not found ... in libsystemd.so.0
[BOX32] Error: Symbol res_nsearch not found ... in libkrb5.so.3
[BOX32] Error: Symbol drmGetDevice2 not found ... in libgbm.so.1
```

These are box32 gaps in the i386 libc/loader it presents, not missing distro packages — installing
`libdbus/libcups/libsdl2:i386` did not change the result. Fixing them means patching box64's BOX32
glibc coverage (upstream), out of scope for this spike.

## Environment / repro

- Native arm64 `debian:bookworm` container (`uname -m` = aarch64; **no** `--platform linux/amd64`, so
  no qemu in the loop). `pids.max=512` inside the container — build box64 with `make -j2`, not `-jN`,
  or `cc` dies with `Resource temporarily unavailable` (errno 11).
- Confirming the box86 wall: a static armhf busybox (extracted from an alpine `arm/v7` image via
  `docker save`; do not `--platform`-pull-and-run, it OOMs the daemon) is caught by `qemu-arm` binfmt
  (`qemu-arm: Could not open '/lib/ld-musl-armhf.so.1'`) — never executed natively.
- Full repeatable stack: `harness/box_setup.sh`. Game boot: `harness/box_boot.sh` (stages the same
  minimal root the qemu spike used). Reliability loop: `harness/deusex_reliability.sh`.
- This is a shared host; another session's qemu `dxboot*` containers intermittently saturate the pid
  table, so `docker exec` fails transiently (`setns ... resource temporarily unavailable`) — retry.

## Not pinned with a test

Per `rules/spikes.md`, this is an environmental/tooling wall (like `deusex-boot-wedge`), not a stable
fact about the binary or a golden — no regression test. The re-runnable harness + captured evidence
are the committed artifact.

## Bottom line

box86: impossible here (no aarch32 on Apple Silicon). box64: the correct qemu-free tool, and its wine
stack works — but its experimental BOX32 can't carry `DeusEx.exe`'s Win32 network/init path today, so
the engine render route stays blocked on this box. Two forward options, both non-trivial: (a) patch
box64 BOX32's i386 glibc symbol coverage (`nsiproxy` first) and retry; (b) drop box32 by using a
64-bit-only wine with new-WoW64 to run the Win32 game under mature box64 x86_64 — needs a newer wine
than Debian 8.0. The other non-qemu emulator on this host, **FEX** (`fextest-img`, native arm64, runs
32- and 64-bit x86 without aarch32), is the more likely near-term win and is worth a separate spike.
