#!/usr/bin/env bash
# boot_game.sh — boot retail v68 DeusEx.exe (SoftDrv, headless :99) with the engine-only
# spike UedPreview.u + room.dx, and wait for the console-spawned link on :7777. Runs INSIDE
# a dx-lum-uned container whose base entrypoint already brought up Xvfb on :99 (LAUNCH_UED=0).
# Adapted from uedcli/game/game-entrypoint.sh (the proven boot recipe: FirstRun=400 skips the
# first-time-config modal; the SMART relaunch loop rides out wine's intermittent pipe_read
# startup wedge). Inputs (already in place by the host):
#   /gsys      dxreal retail System (ro mount)     /gtex   room textures (ro mount)
#   /work/UedPreview.u   the compiled spike pkg    /work/room.dx   the textured room map
set -u
D=:99; R=/work/dx; GEXE=DeusEx.exe
listening(){ netstat -ltn 2>/dev/null | grep -q ':7777 '; }

echo "[boot] assembling game root"
rm -rf "$R" && mkdir -p "$R/System" "$R/Maps" "$R/Textures"
cp -r /gsys/. "$R/System/"
cp /work/UedPreview.u "$R/System/"
cp /work/room.dx "$R/Maps/room.dx"
for f in /gtex/*.utx /gtex/*.UTX; do [ -e "$f" ] && cp "$f" "$R/Textures/"; done

python3 - "$R/System/DeusEx.ini" "${UED_SIZE_X:-1280}" "${UED_SIZE_Y:-960}" <<'PY'
import sys
ini, sx, sy = sys.argv[1], sys.argv[2], sys.argv[3]
fix = {"localmap": "LocalMap=room.dx",
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
        if not seen_paths:
            out += ["Paths=../System/*.u", "Paths=../Maps/*.dx", "Paths=../Textures/*.utx"]
            seen_paths = True
        continue
    out.append(fix.pop(k) if k in fix else l)
for v in fix.values():                         # any missing key: append into [URL] is wrong; put in [Core.System]
    pass
if fix:
    i = out.index("[Core.System]")
    out[i+1:i+1] = list(fix.values())
open(ini, "wb").write(("\r\n".join(out)).encode("latin-1"))
print("[boot] ini patched")
PY

export WINEESYNC="${WINEESYNC:-1}" WINEFSYNC="${WINEFSYNC:-1}" WINEDLLOVERRIDES="winealsa.drv=d"
cd "$R/System"
DISPLAY=$D wineserver -k 2>/dev/null || true
DISPLAY=$D timeout 30 wineboot -u >/dev/null 2>&1 || true
_launch(){
  DISPLAY=$D wineserver -k 2>/dev/null || true; sleep 1
  rm -f Running.ini; : > DeusEx.log
  setsid bash -c "DISPLAY=$D WINEESYNC=$WINEESYNC WINEFSYNC=$WINEFSYNC WINEDLLOVERRIDES=winealsa.drv=d exec wine $GEXE -log -nosound" \
    >/work/launch.log 2>/work/launch-err.log &
}
LINKED=0
for _try in $(seq 1 "${UED_LAUNCH_TRIES:-10}"); do
  echo "[boot] launch attempt $_try" >&2
  _launch
  sleep "${UED_WEDGE_S:-40}"
  if listening; then LINKED=1; break; fi
  if [ "$(wc -l < DeusEx.log 2>/dev/null || echo 0)" -le 22 ]; then
    echo "[boot] frozen at boot banner (pipe_read wedge) — fast relaunch" >&2
    pkill -9 -f "$GEXE" 2>/dev/null || true; DISPLAY=$D wineserver -k 2>/dev/null || true; sleep 2; continue
  fi
  echo "[boot] progressing — waiting for link" >&2
  for _ in $(seq 1 "${UED_ATTEMPT_S:-240}"); do listening && { LINKED=1; break; }; sleep 1; done
  [ "$LINKED" = "1" ] && break
  pkill -9 -f "$GEXE" 2>/dev/null || true; DISPLAY=$D wineserver -k 2>/dev/null || true; sleep 2
done
[ "$LINKED" = "1" ] || { echo "[boot] FATAL: link never bound"; tail -30 DeusEx.log 2>/dev/null | tr -d '\000'; exit 1; }
echo "[boot] READY link-up"
