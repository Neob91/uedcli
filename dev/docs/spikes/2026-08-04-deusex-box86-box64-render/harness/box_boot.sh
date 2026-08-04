#!/usr/bin/env bash
# box_boot.sh — boot retail v68 DeusEx.exe under box64 (native arm64, NO qemu) with a
# minimal game root + UedPreview console. Polls :7777. exit 0 = link, 7 = wedge, 8 = load error.
set -u
BOX=/root/box64/build/box64
WINELOADER=/usr/lib/wine/wine; WINESERVER=/usr/lib/wine/wineserver
R=/root/gameroot; D=:99; GEXE=DeusEx.exe
ENGINE="${ENGINE:-stock}"; CACHE="${CACHE:-4}"
WEDGE_S="${WEDGE_S:-60}"; WINDOW_S="${WINDOW_S:-180}"
export WINEDEBUG=-all WINEARCH=win32 WINEPREFIX=/root/wp32
export WINELOADER WINESERVER BOX64_LOG=0
export BOX64_NOBANNER=1
listening(){ netstat -ltn 2>/dev/null | grep -q ':7777 '; }

python3 - "$R/System/DeusEx.ini" "$ENGINE" "$CACHE" <<'PY'
import sys
ini, engine, cache = sys.argv[1], sys.argv[2], sys.argv[3]
raw = open(ini, "rb").read().decode("latin-1"); lines = raw.split("\r\n")
if engine == "stock":
    game_engine="Engine.GameEngine"; default_game="Engine.GameInfo"
    player_class="Engine.Camera"; root=""; cache_section="[Engine.GameEngine]"
else:
    game_engine="DeusEx.DeusExGameEngine"; default_game="DeusEx.DeusExGameInfo"
    player_class="DeusEx.JCDentonMale"; root="DeusEx.DeusExRootWindow"; cache_section="[DeusEx.DeusExGameEngine]"
eng_fix={"gameengine":f"GameEngine={game_engine}","gamerenderdevice":"GameRenderDevice=SoftDrv.SoftwareRenderDevice",
    "renderdevice":"RenderDevice=SoftDrv.SoftwareRenderDevice","windowedrenderdevice":"WindowedRenderDevice=SoftDrv.SoftwareRenderDevice",
    "console":"Console=UedPreview.UedPreviewConsole","defaultgame":f"DefaultGame={default_game}",
    "defaultservergame":f"DefaultServerGame={default_game}","root":(f"Root={root}" if root else None),
    "editorengine":"EditorEngine=Editor.EditorEngine"}
url_fix={"localmap":"LocalMap=room.dx","map":"Map=room.dx","class":f"Class={player_class}"}
win_fix={"windowedcolorbits":"WindowedColorBits=32","windowedviewportx":"WindowedViewportX=640",
    "windowedviewporty":"WindowedViewportY=480","startupfullscreen":"StartupFullscreen=False"}
out,section,saw_paths=[],"",False
for l in lines:
    s=l.strip()
    if s.startswith("[") and s.endswith("]"): section=s.lower(); out.append(l); continue
    k=l.split("=",1)[0].strip().lower()
    if k=="paths":
        if not saw_paths: out+=["Paths=../System/*.u","Paths=../Maps/*.dx","Paths=../Textures/*.utx"]; saw_paths=True
        continue
    if k=="firstrun": out.append("FirstRun=400"); continue
    if section=="[engine.engine]" and k in eng_fix:
        v=eng_fix.pop(k);
        if v is not None: out.append(v)
        continue
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
inject(cache_section,[f"CacheSizeMegs={cache}"])
open(ini,"wb").write(("\r\n".join(out)).encode("latin-1"))
print(f"[box] ini: GameEngine={game_engine} Class={player_class} root={root or '(none)'}")
PY

pgrep -f "Xvfb $D" >/dev/null 2>&1 || { Xvfb $D -screen 0 1024x768x24 >/tmp/xvfb.log 2>&1 & sleep 2; }
cd "$R/System"
DISPLAY=$D $BOX $WINESERVER -k 2>/dev/null || true
rm -f Running.ini; : > DeusEx.log
echo "[box] launch: box64 wine $GEXE"
setsid bash -c "cd $R/System; DISPLAY=$D BOX64_LOG=0 exec $BOX $WINELOADER $GEXE -log -nosound" \
  >/tmp/launch.log 2>/tmp/launch-err.log &

t=0; LINKED=0; ERRORED=0
while [ "$t" -lt "$WINDOW_S" ]; do
  LL=$(wc -l < DeusEx.log 2>/dev/null || echo 0)
  if listening; then echo "=== LINK BOUND t=${t}s (log=$LL) ==="; LINKED=1; break; fi
  if grep -qaiE 'Failed to load|Can.t find|Critical:|appError|Assertion' DeusEx.log 2>/dev/null; then
    echo "=== LOAD ERROR t=${t}s ==="; ERRORED=1; break; fi
  if ! pgrep -f "$GEXE" >/dev/null 2>&1 && [ "$t" -gt 10 ]; then
    echo "=== GAME PROCESS GONE t=${t}s (log=$LL) ==="; ERRORED=2; break; fi
  [ $((t % 10)) -eq 0 ] && echo "[box] t=${t}s log=$LL"
  sleep 3; t=$((t+3))
done
echo "[box] done LINKED=$LINKED ERRORED=$ERRORED"
echo "[box] --- DeusEx.log tail ---"; tail -25 DeusEx.log 2>/dev/null | tr -d '\000'
echo "[box] --- launch-err tail ---"; tail -20 /tmp/launch-err.log 2>/dev/null | tr -d '\000' | grep -vaE '^\[BOX'
[ "$LINKED" = 1 ] && exit 0
[ "$ERRORED" = 1 ] && exit 8
[ "$ERRORED" = 2 ] && exit 9
exit 7
