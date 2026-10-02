+++
priority = "p2"
kind = "debug"
summary = "Spike FEX (fextest-img) to run x86 DeusEx.exe on arm64 without qemu"
+++

# Spike FEX (fextest-img) to run x86 DeusEx.exe on arm64 without qemu

The qemu-user boot path deadlocks in wineserver IPC (`2026-08-04-deusex-boot-wedge`). box86/box64
was tried next (`2026-08-04-deusex-box86-box64-render`): box86 is impossible here (armhf, no aarch32
EL0 on this Apple-Silicon CPU); box64 is native arm64 and runs x86 wine cleanly (incl. the wineserver
IPC roundtrip qemu deadlocks on), but its experimental BOX32 can't carry `DeusEx.exe`'s Win32
init/network path — `nsiproxy.so` fails PLT relocation (`if_nameindex` missing), 0/3 boots bind.

FEX is the third non-qemu x86-on-arm64 emulator, native arm64, runs 32- and 64-bit x86 with no
aarch32 requirement, and generally more complete than box64 BOX32. A `fextest-img` (ubuntu 24.04 +
FEX, ~19 GB) already exists locally from earlier exploration. Worth a spike: boot `DeusEx.exe` under
FEX with the same minimal root + UedPreview console (`box_boot.sh` recipe), check whether it binds
`:7777` and renders.

Alternative to also weigh: 64-bit-only wine with new-WoW64 (needs wine newer than Debian 8.0) to run
the Win32 game under mature box64 x86_64, dropping box32 entirely.
