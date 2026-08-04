# Harness — render `DeusEx.exe` under FEX + wine-10

Runs against the `fextest-img:latest` container (FEX-emu + a Debian-bookworm x86
wine-8 RootFS at `/root/dtools-rootfs`, exposed to FEX as RootFS name `dtools`).

## Build the wine-10 x86 userland (`setup_all.sh`, runs in the container)
1. `cp -a /root/dtools-rootfs /root/wine10-rootfs`.
2. Download the winehq `wine-stable` 10.0 debs (amd64 + i386) and `dpkg-deb -x`
   each into **both** `/root/wine10-rootfs` **and** the container's real `/`.
   The rootfs copy lets FEX load the ELF loader + `.so`s; the real-fs copy is
   required because FEX serves rootfs files only to the loader — wine's runtime
   **guest `open()`** for PE dlls hits the host fs directly with no rootfs
   fallback, so PE dlls (`kernel32.dll` …) must exist on the real fs or wine
   dies `could not load kernel32.dll c0000135`.
3. Symlink `~/.local/share/fex-emu/RootFS/wine10 -> /root/wine10-rootfs`, copy a
   working `/etc/resolv.conf` in, set `Config.json` RootFS to `wine10`.

Pin exactly wine-10: `winehq-stable` currently resolves to 11.0.

## Run
- rpcss test: `FEXBash -c '/opt/wine-stable/bin/wine wineboot -u'` then
  `wine cmd /c echo` on a fresh `WINEARCH=win32` prefix.
- DeusEx: game root on the **real fs** (`/game`), full retail `System` (all inis
  or `MissingIni`/`appInit`), `DISPLAY=<xhost-ip>:99` to a native-arm64 Xvfb
  container. `launch_loop.sh` relaunches on the ≤22-line banner freeze.
- `mkini.py <DeusEx.ini> stock 4` patches the ini (stock engine, UedPreview
  console, `LocalMap=room.dx`, `FirstRun=400`, paths).

## Gotchas (cost time; pinned so the next run skips them)
- FEX guest **writes** go to the container's real fs, **reads** fall back to the
  RootFS. So apt-under-FEX writes into the container, not the rootfs — build the
  userland with `dpkg-deb -x` on the arm64 side, not apt-under-FEX.
- FEX guest threads don't reap after `pkill`/`wineserver -k`; stale `DeusEx.exe`
  hold `DeusEx.log` (sharing violation `c0000043`). Clean reset = recreate the
  container, or use a unique `-log=` per attempt.
