#!/usr/bin/env bash
# matrix_incontainer.sh — run the whole sync/cpuset mitigation matrix inside ONE container.
# Container start + `wineboot -u` under arm64 emulation costs ~6 min; doing that per trial makes
# N>=5 take hours. So: assemble the game root + wineboot ONCE, then loop launches, killing the
# wineserver between each so the per-trial WINEESYNC/WINEFSYNC/cpuset takes effect. Classifies
# each launch LINK (:7777 bound) vs WEDGE (log frozen <=23 lines at banner, 0% cpu).
# Runs INSIDE a dx-lum-uned container (Xvfb :99, LAUNCH_UED=0).
#   CONFIGS  space-list of labels (default: all)   N  trials per config (default 5)
#   WIN      per-launch link wait seconds (default 75)
set -u
D=:99; R=/work/dx; GEXE=DeusEx.exe
N="${N:-5}"; WIN="${WIN:-75}"
CONFIGS="${CONFIGS:-esync-fsync fsync-only server-side esync-only cpuset1 cpuset1-fsync}"
listening(){ netstat -ltn 2>/dev/null | grep -q ':7777 '; }

echo "[mx] assembling game root"
rm -rf "$R" && mkdir -p "$R/System" "$R/Maps" "$R/Textures"
cp -r /gsys/. "$R/System/"
cp /work/UedPreview.u "$R/System/"
cp /work/room.dx "$R/Maps/room.dx"
for f in /gtex/*.utx /gtex/*.UTX; do [ -e "$f" ] && cp "$f" "$R/Textures/"; done

python3 - "$R/System/DeusEx.ini" <<'PY'
import sys
ini = sys.argv[1]
fix = {"localmap":"LocalMap=room.dx","console":"Console=UedPreview.UedPreviewConsole",
       "gamerenderdevice":"GameRenderDevice=SoftDrv.SoftwareRenderDevice",
       "renderdevice":"RenderDevice=SoftDrv.SoftwareRenderDevice","windowedcolorbits":"WindowedColorBits=32",
       "startupfullscreen":"StartupFullscreen=False","windowedviewportx":"WindowedViewportX=1280",
       "windowedviewporty":"WindowedViewportY=960","firstrun":"FirstRun=400"}
raw = open(ini,"rb").read().decode("latin-1"); out=[]; seen=False
for l in raw.split("\r\n"):
    k=l.split("=",1)[0].strip().lower()
    if k=="paths":
        if not seen: out+=["Paths=../System/*.u","Paths=../Maps/*.dx","Paths=../Textures/*.utx"]; seen=True
        continue
    out.append(fix.pop(k) if k in fix else l)
i=out.index("[Core.System]"); out[i+1:i+1]=list(fix.values())
open(ini,"wb").write(("\r\n".join(out)).encode("latin-1")); print("[mx] ini patched")
PY

cd "$R/System"
export WINEDLLOVERRIDES="winealsa.drv=d"
echo "[mx] wineboot -u (one-time, slow under emulation)"
DISPLAY=$D wineserver -k 2>/dev/null || true
DISPLAY=$D WINEESYNC=0 WINEFSYNC=0 timeout 300 wineboot -u >/dev/null 2>&1 || true
DISPLAY=$D wineserver -k 2>/dev/null || true; sleep 2

env_for(){ case "$1" in
  esync-fsync)   echo "WINEESYNC=1 WINEFSYNC=1" ;;
  fsync-only)    echo "WINEESYNC=0 WINEFSYNC=1" ;;
  server-side)   echo "WINEESYNC=0 WINEFSYNC=0" ;;
  esync-only)    echo "WINEESYNC=1 WINEFSYNC=0" ;;
  cpuset1)       echo "WINEESYNC=1 WINEFSYNC=1 __TASK=taskset -c 0" ;;
  cpuset1-fsync) echo "WINEESYNC=0 WINEFSYNC=1 __TASK=taskset -c 0" ;;
esac; }

RES=/work/matrix.result; : > "$RES"
for cfg in $CONFIGS; do
  spec="$(env_for "$cfg")"; TASK=""; ENVV=""
  for tok in $spec; do case "$tok" in __TASK=*) TASK="taskset -c 0";; taskset|-c|0) ;; *) ENVV="$ENVV $tok";; esac; done
  pass=0
  for i in $(seq 1 "$N"); do
    DISPLAY=$D wineserver -k 2>/dev/null || true; pkill -9 -f "$GEXE" 2>/dev/null || true; sleep 2
    rm -f Running.ini; : > DeusEx.log
    setsid bash -c "DISPLAY=$D $ENVV WINEDLLOVERRIDES=winealsa.drv=d exec $TASK wine $GEXE -log -nosound" \
      >/work/launch.log 2>/work/launch-err.log &
    linked=0; t=0
    while [ $t -lt "$WIN" ]; do listening && { linked=1; break; }; sleep 3; t=$((t+3)); done
    ll=$(wc -l < DeusEx.log 2>/dev/null || echo 0)
    if [ "$linked" = 1 ]; then pass=$((pass+1)); r="LINK @~${t}s"; else r="WEDGE (log=$ll)"; fi
    echo "[$cfg] trial $i/$N: $r   (env:$ENVV task:${TASK:-none})" | tee -a "$RES"
  done
  echo "=== [$cfg] LINK $pass/$N ===" | tee -a "$RES"
done
DISPLAY=$D wineserver -k 2>/dev/null || true; pkill -9 -f "$GEXE" 2>/dev/null || true
echo "[mx] complete"
