#!/usr/bin/env bash
# relaunch_loop.sh — the intermittent-race mitigation: assemble ONE minimal stock
# game root, then relaunch DeusEx.exe up to MAXTRIES times (wineserver -k + fresh
# wine each attempt re-rolls the wineserver-IPC lost-wakeup race). On the FIRST
# attempt that binds :7777, render the textured room (render_frame.py) and stop.
# Runs INSIDE a dx-lum-uned container (Xvfb :99, LAUNCH_UED=0). /gsys full System
# (ro), /gtex textures. Minimal footprint: stock engine, no DeusEx.u, CacheSizeMegs=4.
set -u
D=:99; R=/work/dx; GEXE=DeusEx.exe
MAXTRIES="${MAXTRIES:-40}"; POLL_S="${POLL_S:-75}"; WEDGE_S="${WEDGE_S:-40}"; CACHE="${CACHE:-4}"
listening(){ netstat -ltn 2>/dev/null | grep -q ':7777 '; }
memc(){ awk '{printf "%d", $1/1024/1024}' /sys/fs/cgroup/memory.current 2>/dev/null; }

echo "[loop] assembling minimal stock game root (cache=$CACHE)"
rm -rf "$R" && mkdir -p "$R/System" "$R/Maps" "$R/Textures"
STOCK="Core.u Engine.u IpDrv.u Core.dll Engine.dll Render.dll SoftDrv.dll WinDrv.dll Window.dll IpDrv.dll Galaxy.dll Fire.dll MSVCRT.dll SoftDrv.int WinDrv.int Galaxy.int Render.int Engine.int Core.int IpDrv.int DeusEx.exe DeusEx.ini"
for f in $STOCK; do [ -e "/gsys/$f" ] && cp "/gsys/$f" "$R/System/$f"; done
cp /work/UedPreview.u "$R/System/"
cp /work/room.dx "$R/Maps/room.dx"
for f in /gtex/*.utx /gtex/*.UTX; do [ -e "$f" ] && cp "$f" "$R/Textures/"; done
echo "[loop] root: $(du -sh "$R" | cut -f1), $(ls "$R/System" | wc -l) System files"

python3 - "$R/System/DeusEx.ini" "$CACHE" <<'PY'
import sys
ini, cache = sys.argv[1], sys.argv[2]
raw = open(ini, "rb").read().decode("latin-1"); lines = raw.split("\r\n")
eng_fix = {"gameengine":"GameEngine=Engine.GameEngine",
  "gamerenderdevice":"GameRenderDevice=SoftDrv.SoftwareRenderDevice",
  "renderdevice":"RenderDevice=SoftDrv.SoftwareRenderDevice",
  "windowedrenderdevice":"WindowedRenderDevice=SoftDrv.SoftwareRenderDevice",
  "console":"Console=UedPreview.UedPreviewConsole",
  "defaultgame":"DefaultGame=Engine.GameInfo","defaultservergame":"DefaultServerGame=Engine.GameInfo",
  "root":None,"editorengine":"EditorEngine=Editor.EditorEngine"}
url_fix = {"localmap":"LocalMap=room.dx","map":"Map=room.dx","class":"Class=Engine.Camera"}
win_fix = {"windowedcolorbits":"WindowedColorBits=32","windowedviewportx":"WindowedViewportX=640",
  "windowedviewporty":"WindowedViewportY=480","startupfullscreen":"StartupFullscreen=False"}
out, section, saw_paths = [], "", False
for l in lines:
    s=l.strip()
    if s.startswith("[") and s.endswith("]"): section=s.lower(); out.append(l); continue
    k=l.split("=",1)[0].strip().lower()
    if k=="paths":
        if not saw_paths: out+=["Paths=../System/*.u","Paths=../Maps/*.dx","Paths=../Textures/*.utx"]; saw_paths=True
        continue
    if k=="firstrun": out.append("FirstRun=400"); continue
    if section=="[engine.engine]" and k in eng_fix:
        v=eng_fix.pop(k);  out.append(v) if v else None; continue
    if section=="[url]" and k in url_fix: out.append(url_fix.pop(k)); continue
    if section=="[windrv.windowsclient]" and k in win_fix: out.append(win_fix.pop(k)); continue
    out.append(l)
def inject(sec,kvs):
    if not kvs: return
    try: i=out.index(sec)
    except ValueError: out.append(sec); i=len(out)-1
    out[i+1:i+1]=kvs
inject("[Engine.Engine]",[v for v in eng_fix.values() if v])
inject("[URL]",list(url_fix.values())); inject("[WinDrv.WindowsClient]",list(win_fix.values()))
inject("[Engine.GameEngine]",[f"CacheSizeMegs={cache}"])
open(ini,"wb").write(("\r\n".join(out)).encode("latin-1"))
print("[loop] ini patched: GameEngine=Engine.GameEngine Class=Engine.Camera cache="+cache)
PY

export WINEESYNC=1 WINEFSYNC=1 WINEDLLOVERRIDES="winealsa.drv=d"
cd "$R/System"
DISPLAY=$D wineserver -k 2>/dev/null || true
DISPLAY=$D timeout 40 wineboot -u >/dev/null 2>&1 || true

LINKED=0; WON=0
for try in $(seq 1 "$MAXTRIES"); do
  DISPLAY=$D wineserver -k 2>/dev/null || true; pkill -9 -f "$GEXE" 2>/dev/null || true; sleep 1
  rm -f Running.ini; : > DeusEx.log
  setsid bash -c "DISPLAY=$D WINEESYNC=1 WINEFSYNC=1 WINEDLLOVERRIDES=winealsa.drv=d exec wine $GEXE -log -nosound" \
    >/work/launch.log 2>/work/launch-err.log &
  el=0
  while [ "$el" -lt "$POLL_S" ]; do
    if listening; then LINKED=1; break; fi
    sleep 3; el=$((el+3))
    # wedge detect: past WEDGE_S with the log still at the banner or empty -> relaunch fast
    if [ "$el" -ge "$WEDGE_S" ]; then
      ll=$(wc -l < DeusEx.log 2>/dev/null || echo 0)
      [ "$ll" -le 22 ] && break
    fi
  done
  ll=$(wc -l < DeusEx.log 2>/dev/null || echo 0)
  if [ "$LINKED" = 1 ]; then
    echo "[loop] attempt $try/$MAXTRIES LINKED at ${el}s mem=$(memc)MiB loglines=$ll"
    WON=$try; break
  fi
  wch=$(cat /proc/$(pgrep -f "$GEXE" 2>/dev/null | head -1)/wchan 2>/dev/null || echo gone)
  echo "[loop] attempt $try/$MAXTRIES WEDGE el=${el}s mem=$(memc)MiB loglines=$ll wchan=$wch"
done

if [ "$LINKED" != 1 ]; then
  echo "[loop] ALL $MAXTRIES attempts wedged. Final evidence:"
  P=$(pgrep -f "$GEXE" 2>/dev/null | head -1)
  echo "  mem.current=$(memc)MiB cap=$(( $(cat /sys/fs/cgroup/memory.max)/1024/1024 ))MiB"
  echo "  mem.events: $(tr '\n' ' ' < /sys/fs/cgroup/memory.events)"
  echo "  DeusEx.exe main wchan=$(cat /proc/$P/wchan 2>/dev/null) state=$(sed -n 's/^State:\s*//p' /proc/$P/status 2>/dev/null)"
  echo "[loop] --- DeusEx.log tail ---"; tail -8 DeusEx.log 2>/dev/null | tr -d '\000'
  echo "[loop] --- launch-err.log tail ---"; tail -12 /work/launch-err.log 2>/dev/null | tr -d '\000'
  exit 7
fi

echo "[loop] LINK WON on attempt $WON — rendering"
python3 /work/render_frame.py || { echo "[loop] render_frame.py FAILED"; exit 8; }
ls -la /work/game_preview_here.png 2>/dev/null && echo "[loop] RENDER OK"
exit 0
