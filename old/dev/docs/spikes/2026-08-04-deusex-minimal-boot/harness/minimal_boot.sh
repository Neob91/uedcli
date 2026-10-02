#!/usr/bin/env bash
# minimal_boot.sh — boot retail v68 DeusEx.exe with a MINIMAL game root to shrink the
# working set under the 6 GiB container cap. Runs INSIDE a dx-lum-uned container
# (Xvfb :99 up, LAUNCH_UED=0). /gsys = full retail System (ro mount), /gtex = textures.
# Samples cgroup memory + per-thread state each 2s; exits 0 on :7777 link, 7 on wedge,
# 8 on a DeusEx.log load error. Peak memory.current is printed at the end.
#
# Env knobs:
#   MINSET   stock|dx|full  which System packages to copy (default stock)
#   ENGINE   stock|dx        GameEngine + default player class (default matches MINSET)
#   CACHE    CacheSizeMegs   engine cache (default 4)
#   WEDGE_S  seconds before declaring a boot-banner wedge (default 45)
#   WINDOW_S total sample window seconds (default 140)
#   WINEESYNC/WINEFSYNC  passed through (default 1/1)
set -u
D=:99; R=/work/dx; GEXE=DeusEx.exe
MINSET="${MINSET:-stock}"; ENGINE="${ENGINE:-$MINSET}"; CACHE="${CACHE:-4}"
WEDGE_S="${WEDGE_S:-45}"; WINDOW_S="${WINDOW_S:-140}"
listening(){ netstat -ltn 2>/dev/null | grep -q ':7777 '; }

echo "[min] MINSET=$MINSET ENGINE=$ENGINE CACHE=$CACHE"
rm -rf "$R" && mkdir -p "$R/System" "$R/Maps" "$R/Textures"

# --- curated stock package set (NO DeusEx content) ---
STOCK_U="Core.u Engine.u IpDrv.u"
STOCK_DLL="Core.dll Engine.dll Render.dll SoftDrv.dll WinDrv.dll Window.dll IpDrv.dll Galaxy.dll Fire.dll MSVCRT.dll"
STOCK_INT="SoftDrv.int WinDrv.int Galaxy.int Render.int Engine.int Core.int IpDrv.int"
DX_EXTRA_U="DeusEx.u"

copy_one(){ [ -e "/gsys/$1" ] && cp "/gsys/$1" "$R/System/$1"; }

case "$MINSET" in
  full)
    cp -r /gsys/. "$R/System/" ;;
  *)
    copy_one DeusEx.exe; copy_one DeusEx.ini
    for f in $STOCK_U $STOCK_DLL $STOCK_INT; do copy_one "$f"; done
    [ "$MINSET" = dx ] && for f in $DX_EXTRA_U; do copy_one "$f"; done
    ;;
esac
cp /work/UedPreview.u "$R/System/"
cp /work/room.dx "$R/Maps/room.dx"
for f in /gtex/*.utx /gtex/*.UTX; do [ -e "$f" ] && cp "$f" "$R/Textures/"; done
echo "[min] game root: $(du -sh "$R" | cut -f1), System files: $(ls "$R/System" | wc -l)"

python3 - "$R/System/DeusEx.ini" "$ENGINE" "$CACHE" <<'PY'
import sys
ini, engine, cache = sys.argv[1], sys.argv[2], sys.argv[3]
raw = open(ini, "rb").read().decode("latin-1")
lines = raw.split("\r\n")

# stock engine: drop DeusEx.u dependency entirely (GameEngine, GameInfo, player, root, audio)
if engine == "stock":
    game_engine = "Engine.GameEngine"
    default_game = "Engine.GameInfo"
    player_class = "Engine.Camera"
    root = ""                    # no DeusExRootWindow
    cache_section = "[Engine.GameEngine]"
else:
    game_engine = "DeusEx.DeusExGameEngine"
    default_game = "DeusEx.DeusExGameInfo"
    player_class = "DeusEx.JCDentonMale"
    root = "DeusEx.DeusExRootWindow"
    cache_section = "[DeusEx.DeusExGameEngine]"

# per-key rewrites within [Engine.Engine]
eng_fix = {
    "gameengine": f"GameEngine={game_engine}",
    "gamerenderdevice": "GameRenderDevice=SoftDrv.SoftwareRenderDevice",
    "renderdevice": "RenderDevice=SoftDrv.SoftwareRenderDevice",
    "windowedrenderdevice": "WindowedRenderDevice=SoftDrv.SoftwareRenderDevice",
    "console": "Console=UedPreview.UedPreviewConsole",
    "defaultgame": f"DefaultGame={default_game}",
    "defaultservergame": f"DefaultServerGame={default_game}",
    "root": (f"Root={root}" if root else None),
    "editorengine": "EditorEngine=Editor.EditorEngine",
}
url_fix = {
    "localmap": "LocalMap=room.dx",
    "map": "Map=room.dx",
    "class": f"Class={player_class}",
}
win_fix = {
    "windowedcolorbits": "WindowedColorBits=32",
    "windowedviewportx": "WindowedViewportX=640",
    "windowedviewporty": "WindowedViewportY=480",
    "startupfullscreen": "StartupFullscreen=False",
}
firstrun_val = "FirstRun=400"

out, section = [], ""
saw_paths = False
for l in lines:
    s = l.strip()
    if s.startswith("[") and s.endswith("]"):
        section = s.lower()
        out.append(l); continue
    k = l.split("=", 1)[0].strip().lower()
    if k == "paths":
        if not saw_paths:
            out += ["Paths=../System/*.u", "Paths=../Maps/*.dx", "Paths=../Textures/*.utx"]
            saw_paths = True
        continue
    if k == "firstrun":
        out.append(firstrun_val); continue
    if section == "[engine.engine]" and k in eng_fix:
        v = eng_fix.pop(k)
        if v is not None: out.append(v)
        continue
    if section == "[url]" and k in url_fix:
        out.append(url_fix.pop(k)); continue
    if section == "[windrv.windowsclient]" and k in win_fix:
        out.append(win_fix.pop(k)); continue
    out.append(l)

# append any missing keys to their sections; set CacheSizeMegs in the engine section
def inject(sec, kvs):
    if not kvs: return
    try: i = out.index(sec)
    except ValueError:
        out.append(sec); i = len(out) - 1
    out[i+1:i+1] = kvs

inject("[Engine.Engine]", list(v for v in eng_fix.values() if v))
inject("[URL]", list(url_fix.values()))
inject("[WinDrv.WindowsClient]", list(win_fix.values()))
inject(cache_section, [f"CacheSizeMegs={cache}"])

open(ini, "wb").write(("\r\n".join(out)).encode("latin-1"))
print(f"[min] ini: GameEngine={game_engine} DefaultGame={default_game} Class={player_class} "
      f"cache={cache} root={root or '(none)'}")
PY

export WINEESYNC="${WINEESYNC:-1}" WINEFSYNC="${WINEFSYNC:-1}" WINEDLLOVERRIDES="winealsa.drv=d"
cd "$R/System"
DISPLAY=$D wineserver -k 2>/dev/null || true
DISPLAY=$D timeout 30 wineboot -u >/dev/null 2>&1 || true
DISPLAY=$D wineserver -k 2>/dev/null || true; sleep 1
rm -f Running.ini; : > DeusEx.log
echo "[min] launch wine $GEXE"
setsid bash -c "DISPLAY=$D WINEESYNC=$WINEESYNC WINEFSYNC=$WINEFSYNC WINEDLLOVERRIDES=winealsa.drv=d exec wine $GEXE -log -nosound" \
  >/work/launch.log 2>/work/launch-err.log &

SL=/work/sample.log; : > "$SL"
mgline(){ awk -v k="$1" '$1==k{print $2}' /sys/fs/cgroup/memory.stat; }
PEAK=0; LINKED=0; ERRORED=0; t=0
while [ "$t" -lt "$WINDOW_S" ]; do
  MC=$(cat /sys/fs/cgroup/memory.current 2>/dev/null || echo 0)
  [ "$MC" -gt "$PEAK" ] && PEAK=$MC
  LL=$(wc -l < DeusEx.log 2>/dev/null || echo 0)
  {
    echo "=== t=${t}s $(date +%H:%M:%S) mem.current=$MC peak=$PEAK loglines=$LL ==="
    echo "mem.events: $(tr '\n' ' ' < /sys/fs/cgroup/memory.events 2>/dev/null)"
    echo "pgfault=$(mgline pgfault) pgmajfault=$(mgline pgmajfault) anon=$(mgline anon) file=$(mgline file)"
    for p in $(pgrep -f -d' ' 'DeusEx.exe|wine|qemu' 2>/dev/null); do
      [ -d /proc/$p ] || continue
      for tid in $(ls /proc/$p/task 2>/dev/null); do
        state=$(sed -n 's/^State:\s*//p' /proc/$p/task/$tid/status 2>/dev/null)
        name=$(sed -n 's/^Name:\s*//p' /proc/$p/task/$tid/status 2>/dev/null)
        wch=$(cat /proc/$p/task/$tid/wchan 2>/dev/null)
        echo "  pid=$p tid=$tid name=$name state=$state wchan=${wch:-?}"
      done
    done
  } >> "$SL"
  if listening; then echo "=== LINK BOUND t=${t}s ===" >> "$SL"; LINKED=1; break; fi
  # fast fail on a package load error (not a wedge)
  if grep -qiE 'Failed to load|Can.t find|Critical:|appError|Assertion' DeusEx.log 2>/dev/null; then
    echo "=== LOAD ERROR t=${t}s ===" >> "$SL"; ERRORED=1; break; fi
  # note if the game process vanished (crash/kill vs wedge)
  if ! pgrep -f "$GEXE" >/dev/null 2>&1 && [ "$t" -gt 8 ]; then
    echo "=== GAME PROCESS GONE t=${t}s ===" >> "$SL"; ERRORED=2; break; fi
  sleep "${SAMPLE_S:-2}"; t=$((t+${SAMPLE_S:-2}))
done

echo "[min] done: LINKED=$LINKED ERRORED=$ERRORED peak.mem.current=$PEAK ($((PEAK/1024/1024)) MiB) cap=$(cat /sys/fs/cgroup/memory.max)"
echo "[min] --- DeusEx.log tail ---"; tail -20 DeusEx.log 2>/dev/null | tr -d '\000'
echo "[min] --- launch-err.log tail ---"; tail -15 /work/launch-err.log 2>/dev/null | tr -d '\000'
[ "$LINKED" = 1 ] && exit 0
[ "$ERRORED" = 1 ] && exit 8
[ "$ERRORED" = 2 ] && exit 9
exit 7
