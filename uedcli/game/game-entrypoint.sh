#!/usr/bin/env bash
# game-entrypoint.sh — baked into uedcli-game; runs as the container CMD after the base
# brings up Xvfb/noVNC (LAUNCH_UED=0). Assembles a minimal game root, wires the package
# search path FROM THE COMPOSED CONFIG MOUNTS (dev/docs/direction/containers.md, 2026-07-16 15:49 UTC — the
# /resources/<n> mounts ARE the composed ~/.uedcli + project paths, project first), boots
# the staged boot map, and leaves the travel to the HOST (the 3-phase handshake lives in
# preview_game.py — unlike uplayctl's entrypoint, which travels itself).
#   env: UED_GAME_SYSTEM=/resources/rNNN   (the mount holding the game exe + System code)
#        UED_GAME_EXE=DeusEx.exe           (per-substrate; host substrate table)
#        UED_SIZE_X/UED_SIZE_Y             (WindowedViewportX/Y, default 1280x960)
# Readiness signal: port 7777 listening (the console-spawned link). No log scraping.
set -u
D=:99; R=/work/dx; PKG=/opt/uedpreview
GEXE="${UED_GAME_EXE:-DeusEx.exe}"
listening(){ netstat -ltn 2>/dev/null | grep -q ':7777 '; }

echo "[uedcli-game] assembling game root (system=$UED_GAME_SYSTEM exe=$GEXE)"
rm -rf "$R" && mkdir -p "$R/Maps" "$R/Textures" "$R/Sounds" "$R/Music"
cp -r "$UED_GAME_SYSTEM" "$R/System"           # writable copy: inis, logs, our .u
cp "$PKG/pkg/UedPreview.u" "$PKG/pkg/UedPreviewDX.u" "$R/System/"
cp "$PKG/BootMap.dx" "$R/Maps/UedPreviewBoot.dx"
# The TARGET map is docker-cp'd into $R/Maps by the host before it travels there.

# SYMLINK-FARM the composed content into LOCAL game-root dirs, then use STOCK RELATIVE Paths
# (../Textures/*.utx …) — do NOT glob the raw /resources bind mounts from Paths.  WHY (both
# cold reviewers, 2026-07-16): wine 8.0 on this 5.15 kernel runs on esync (WINEFSYNC is inert —
# futex_waitv is 5.16+), whose startup has an intermittent lost-wakeup `pipe_read` deadlock.
# Globbing 7-9 RAW overlay/bind-mount dirs at the first-package-bind moment stretches that race
# window to ~90% wedge; a small LOCAL symlink-farm dir (what uplayctl does, and what uedcli did
# before the 2026-07-14 asset-wiring cutover) enumerates in microseconds and almost never loses
# the wakeup.  The COMPOSED CONFIG still decides WHAT gets farmed — every /resources/<n> mount is
# a composed dir (project first), so `ln -s` first-wins = project shadows base by stem
# (dev/docs/direction/containers.md, 2026-07-16 15:49).  A stray file in a raw mount can't hang the glob either.
# The farmed link NAME is LOWERCASED: UE1 package names are case-insensitive (FName), but Linux
# is case-sensitive, so `CoreTex.utx` (project) and `coretex.utx` (base) would otherwise farm as
# two distinct files and the project shadow would SILENTLY MISS.  Lowercasing collapses
# case-variants to one name, so `ln -s` (no -f = first-wins) shadows project-over-base correctly
# by stem.  Safe: the engine matches a requested package to a filename case-insensitively, and a
# package's real name lives in its header, not the filename.
farm() { local f="$1" dst="$2"; [ -e "$f" ] && \
  ln -s "$f" "$dst/$(basename "$f" | tr '[:upper:]' '[:lower:]')" 2>/dev/null; }
# System is DIFFERENT: it was `cp -r`'d whole (DeusEx.exe / *.dll / DeusEx.ini + base *.u),
# ORIGINAL case — the launch (`wine DeusEx.exe`) and LocalMap depend on that case, and a
# lowercased farm link would DUPLICATE a cp'd file instead of shadowing it.  So System keeps
# original-case links (a code overlay is additively-named — LUM_Core.u etc — and `ln -s`'s
# exact-name reject makes the cp'd base *.u win, which is correct for core code).
farm_sys() { local f="$1"; [ -e "$f" ] && ln -s "$f" "$R/System/$(basename "$f")" 2>/dev/null; }
for d in $(ls -d /resources/r* 2>/dev/null | sort); do   # r000 = first (project) → wins
  for f in "$d"/*.utx; do farm "$f" "$R/Textures"; done
  for f in "$d"/*.uax; do farm "$f" "$R/Sounds"; done
  for f in "$d"/*.umx; do farm "$f" "$R/Music"; done
  for f in "$d"/*.u; do farm_sys "$f"; done
  for f in "$d"/*.dx; do farm "$f" "$R/Maps"; done
  for f in "$d"/*.unr; do farm "$f" "$R/Maps"; done   # Unreal/UT maps (spec D7); DeusEx ships none
done

# Ini patch: replace the boot keys in place (exact names, hard error if missing so nothing
# lands in the wrong section); Paths are the STOCK RELATIVE farm globs (local dirs).  CRLF is
# preserved — wine's ini parser WEDGES silently on LF (quirks.md).
python3 - "$R/System/DeusEx.ini" <<'PY'
import os, sys
ini = sys.argv[1]
sx, sy = os.environ.get("UED_SIZE_X", "1280"), os.environ.get("UED_SIZE_Y", "960")
fix = {"localmap": "LocalMap=UedPreviewBoot.dx",
       "console": "Console=UedPreview.UedPreviewConsole",
       "gamerenderdevice": "GameRenderDevice=SoftDrv.SoftwareRenderDevice",
       "renderdevice": "RenderDevice=SoftDrv.SoftwareRenderDevice",
       "windowedcolorbits": "WindowedColorBits=32",
       "startupfullscreen": "StartupFullscreen=False",
       "windowedviewportx": f"WindowedViewportX={sx}",
       "windowedviewporty": f"WindowedViewportY={sy}",
       "firstrun": "FirstRun=400"}
raw = open(ini, "rb").read().decode("latin-1")
out, seen_paths = [], False
for l in raw.split("\r\n"):
    k = l.split("=", 1)[0].strip().lower()
    if k == "paths":
        if not seen_paths:                         # replace the stock Paths block with the farm globs
            out += ["Paths=../System/*.u", "Paths=../Maps/*.dx", "Paths=../Maps/*.unr",
                    "Paths=../Textures/*.utx", "Paths=../Sounds/*.uax", "Paths=../Music/*.umx"]
            seen_paths = True
        continue
    out.append(fix.pop(k) if k in fix else l)
if fix:
    sys.exit("DeusEx.ini missing expected keys (cannot place safely): " + ", ".join(sorted(fix)))
if not seen_paths:                                 # no stock Paths at all → put the block in [Core.System]
    i = out.index("[Core.System]")
    out[i + 1:i + 1] = ["Paths=../System/*.u", "Paths=../Maps/*.dx", "Paths=../Maps/*.unr",
                        "Paths=../Textures/*.utx", "Paths=../Sounds/*.uax", "Paths=../Music/*.umx"]
open(ini, "wb").write(("\r\n".join(out)).encode("latin-1"))
print("ini patched; relative farm Paths (CRLF preserved)")
PY
# Fail CLOSED on a boot error (spec §4.3): exit → tini exits → the container STOPS. A
# marker-less `tail -f /dev/null` here would strand an un-killable zombie (no /work/.last_use
# ⇒ the idle watchdog never fires). The host surfaces the error from the boot-death.
[ $? -eq 0 ] || { echo "[uedcli-game] FATAL: ini patch failed" >&2; exit 1; }

# Launch under esync/fsync + the relaunch-on-deadlock loop (spec §5 gate fold: the wine
# server-side-sync startup wedge still fires frequently; retry instead of hanging the
# host's guard on one wedged instance). Readiness = the link's port, never the log.
export WINEESYNC="${WINEESYNC:-1}" WINEFSYNC="${WINEFSYNC:-1}"
DISPLAY=$D wineserver -k 2>/dev/null || true
DISPLAY=$D timeout 30 wineboot -u >/dev/null 2>&1 || true
cd "$R/System"
_launch() {
  DISPLAY=$D wineserver -k 2>/dev/null || true
  sleep 1
  rm -f Running.ini; : > DeusEx.log
  setsid bash -c "DISPLAY=$D WINEESYNC=$WINEESYNC WINEFSYNC=$WINEFSYNC WINEDLLOVERRIDES=winealsa.drv=d exec wine $GEXE -log -nosound" \
    >/work/launch.log 2>/work/launch-err.log &
}
# SMART relaunch: the wine `pipe_read` startup deadlock (0% CPU, log frozen at the ~21-line
# CPU-detect banner) is intermittent — retry it FAST.  But a HEALTHY boot on a loaded box is
# merely slow (it loads ~20 packages then the map), so once the log grows past the banner we
# WAIT patiently instead of killing progress.  Wedge-detect: log still ≤22 lines after
# UED_WEDGE_S → relaunch immediately; progressing → poll up to UED_ATTEMPT_S for the link.
LINKED=0
for _try in $(seq 1 "${UED_LAUNCH_TRIES:-8}"); do
  echo "[uedcli-game] launching (attempt $_try/${UED_LAUNCH_TRIES:-8})" >&2
  _launch
  sleep "${UED_WEDGE_S:-35}"
  if listening; then LINKED=1; break; fi
  if [ "$(wc -l < DeusEx.log 2>/dev/null || echo 0)" -le 22 ]; then
    echo "[uedcli-game] frozen at boot banner (pipe_read wedge) — fast relaunch" >&2
    pkill -9 -f "$GEXE" 2>/dev/null || true; DISPLAY=$D wineserver -k 2>/dev/null || true; sleep 2
    continue
  fi
  echo "[uedcli-game] boot progressing (log grew) — waiting for the link" >&2
  for _ in $(seq 1 "${UED_ATTEMPT_S:-160}"); do listening && { LINKED=1; break; }; sleep 1; done
  [ "$LINKED" = "1" ] && break
  echo "[uedcli-game] progressed but no link in ${UED_ATTEMPT_S:-160}s — relaunching" >&2
  pkill -9 -f "$GEXE" 2>/dev/null || true; DISPLAY=$D wineserver -k 2>/dev/null || true; sleep 2
done
if [ "$LINKED" != "1" ]; then
  echo "[uedcli-game] FATAL: link never bound" >&2
  exit 1                       # fail CLOSED (spec §4.3): no marker/watchdog zombie; host reports it
fi
echo "[uedcli-game] READY link-up"

# Idle self-death (spec §4.3, D3). WARM containers (UED_IDLE_S>0) run an INLINE watchdog —
# tini's DIRECT child, so its `exit` stops the container (a backgrounded `&` watchdog would
# not be tini's child and its exit wouldn't stop anything; `kill 1` is a no-op). The liveness
# marker /work/.last_use is created ONLY NOW (at READY) so "marker absent ⇒ still booting, not
# idle"; the in-container batch script (preview_batch.py) `touch`es it throughout each run (per
# travel poll + per shot) so a long batch is not idle-killed mid-flight. EPHEMERAL containers (idle unset/
# ≤0, e.g. the offline spike path) keep the old wait — the host tears them down.
IDLE="${UED_IDLE_S:-0}"
[[ "$IDLE" =~ ^[0-9]+$ ]] || IDLE=0        # fail closed on a malformed value → ephemeral, not an erroring loop
if [ "$IDLE" -le 0 ]; then
  exec tail -f /dev/null
fi
: > /work/.last_use
echo "[uedcli-game] warm: idle self-death after ${IDLE}s (pin with /work/.pinned)"
while true; do
  sleep 60
  [ -e /work/.pinned ] && continue                       # --keep-alive pin (spec §4.7)
  now=$(date +%s); last=$(stat -c %Y /work/.last_use 2>/dev/null || echo "$now")
  if [ $((now - last)) -ge "$IDLE" ]; then
    echo "[uedcli-game] idle ${IDLE}s — self-terminating" >&2
    pkill -9 -f "$GEXE" 2>/dev/null || true
    exit 0                     # INLINE exit ⇒ tini exits ⇒ container stops (spec D3)
  fi
done
