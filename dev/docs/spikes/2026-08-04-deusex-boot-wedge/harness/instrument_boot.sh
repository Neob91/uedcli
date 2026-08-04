#!/usr/bin/env bash
# instrument_boot.sh — single-launch DeusEx.exe boot with per-2s sampling to decide
# OOM vs deadlock. Runs INSIDE a dx-lum-uned container (Xvfb :99 up, LAUNCH_UED=0).
# Captures per sample: cgroup memory.current/events/stat(pgmajfault,pgfault), and for
# every thread of the wine/DeusEx/qemu tree: State, Name, wchan, cpu-ticks (utime+stime).
# Emits /work/sample.log (one block per tick) and exits when :7777 binds or window ends.
#
# Env knobs (all optional):
#   UED_CPUSET   — if set, taskset -c <value> the wine launch (e.g. "0" or "0-1")
#   WINEESYNC WINEFSYNC — passed through (default 1/1, the harness default)
#   WINE_DISABLE_FAST_SYNC — passed through if set
#   UED_WINDOW_S — sample window seconds (default 120)
#   UED_INI_EXTRA — extra ini key=val lines appended to [Core.System], ';'-separated
set -u
D=:99; R=/work/dx; GEXE=DeusEx.exe
WIN=${UED_WINDOW_S:-120}
listening(){ netstat -ltn 2>/dev/null | grep -q ':7777 '; }

echo "[inst] assembling game root"
rm -rf "$R" && mkdir -p "$R/System" "$R/Maps" "$R/Textures"
cp -r /gsys/. "$R/System/"
cp /work/UedPreview.u "$R/System/"
cp /work/room.dx "$R/Maps/room.dx"
for f in /gtex/*.utx /gtex/*.UTX; do [ -e "$f" ] && cp "$f" "$R/Textures/"; done

python3 - "$R/System/DeusEx.ini" "${UED_INI_EXTRA:-}" <<'PY'
import sys
ini = sys.argv[1]
extra = sys.argv[2] if len(sys.argv) > 2 else ""
fix = {"localmap": "LocalMap=room.dx",
       "console": "Console=UedPreview.UedPreviewConsole",
       "gamerenderdevice": "GameRenderDevice=SoftDrv.SoftwareRenderDevice",
       "renderdevice": "RenderDevice=SoftDrv.SoftwareRenderDevice",
       "windowedcolorbits": "WindowedColorBits=32",
       "startupfullscreen": "StartupFullscreen=False",
       "windowedviewportx": "WindowedViewportX=1280",
       "windowedviewporty": "WindowedViewportY=960",
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
i = out.index("[Core.System]")
inject = list(fix.values()) + [e for e in extra.split(";") if e.strip()]
out[i+1:i+1] = inject
open(ini, "wb").write(("\r\n".join(out)).encode("latin-1"))
print("[inst] ini patched; injected:", inject)
PY

export WINEESYNC="${WINEESYNC:-1}" WINEFSYNC="${WINEFSYNC:-1}" WINEDLLOVERRIDES="winealsa.drv=d"
[ -n "${WINE_DISABLE_FAST_SYNC:-}" ] && export WINE_DISABLE_FAST_SYNC
cd "$R/System"
DISPLAY=$D wineserver -k 2>/dev/null || true
DISPLAY=$D timeout 30 wineboot -u >/dev/null 2>&1 || true
DISPLAY=$D wineserver -k 2>/dev/null || true; sleep 1
rm -f Running.ini; : > DeusEx.log

TASK=""
[ -n "${UED_CPUSET:-}" ] && TASK="taskset -c ${UED_CPUSET}"
echo "[inst] launch: $TASK wine $GEXE (ESYNC=$WINEESYNC FSYNC=$WINEFSYNC FASTSYNC_DIS=${WINE_DISABLE_FAST_SYNC:-unset})"
setsid bash -c "DISPLAY=$D WINEESYNC=$WINEESYNC WINEFSYNC=$WINEFSYNC WINEDLLOVERRIDES=winealsa.drv=d exec $TASK wine $GEXE -log -nosound" \
  >/work/launch.log 2>/work/launch-err.log &
LAUNCH_PGID=$!

SL=/work/sample.log; : > "$SL"
mgline(){ awk -v k="$1" '$1==k{print $2}' /sys/fs/cgroup/memory.stat; }
LINKED=0
t=0
while [ "$t" -lt "$WIN" ]; do
  {
    echo "=== t=${t}s $(date +%H:%M:%S) ==="
    echo "mem.current=$(cat /sys/fs/cgroup/memory.current 2>/dev/null) mem.max=$(cat /sys/fs/cgroup/memory.max 2>/dev/null)"
    echo "mem.events: $(tr '\n' ' ' < /sys/fs/cgroup/memory.events 2>/dev/null)"
    echo "mem.events.local: $(tr '\n' ' ' < /sys/fs/cgroup/memory.events.local 2>/dev/null)"
    echo "pgfault=$(mgline pgfault) pgmajfault=$(mgline pgmajfault) anon=$(mgline anon) file=$(mgline file)"
    echo "loglines=$(wc -l < DeusEx.log 2>/dev/null || echo 0)"
    # every thread of the wine/DeusEx tree
    for p in $(pgrep -f -d' ' 'DeusEx.exe|wine|qemu' 2>/dev/null); do
      [ -d /proc/$p ] || continue
      for tid in $(ls /proc/$p/task 2>/dev/null); do
        st=$(awk '/^State:/{print $2$3} /^Name:/{n=$2} END{print n}' /proc/$p/task/$tid/status 2>/dev/null)
        state=$(sed -n 's/^State:\s*//p' /proc/$p/task/$tid/status 2>/dev/null)
        name=$(sed -n 's/^Name:\s*//p' /proc/$p/task/$tid/status 2>/dev/null)
        wch=$(cat /proc/$p/task/$tid/wchan 2>/dev/null)
        # utime+stime (fields 14,15) from stat
        ticks=$(awk '{print $14+$15}' /proc/$p/task/$tid/stat 2>/dev/null)
        echo "  pid=$p tid=$tid name=$name state=$state wchan=${wch:-?} cputicks=${ticks:-?}"
      done
    done
  } >> "$SL"
  if listening; then echo "=== LINK BOUND at t=${t}s ===" >> "$SL"; LINKED=1; break; fi
  sleep 2; t=$((t+2))
done

echo "[inst] done window; LINKED=$LINKED loglines=$(wc -l < DeusEx.log 2>/dev/null)"
echo "[inst] --- DeusEx.log tail ---"; tail -25 DeusEx.log 2>/dev/null | tr -d '\000'
echo "[inst] LINKED=$LINKED"
[ "$LINKED" = "1" ] && exit 0 || exit 7
