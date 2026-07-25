#!/usr/bin/env bash
# Clean instrumented boot of a map; watch DeusEx.log for the render crash.
# Usage: boot_watch.sh <MAP> [minutes]
set -u
MAP="${1:-NativeLit}"
MINS="${2:-6}"
CN="bootwatch-$MAP"
RESULT=/tmp/bootwatch_result.txt
: > "$RESULT"
echo "[boot_watch] map=$MAP cn=$CN mins=$MINS" | tee -a "$RESULT"

docker rm -f "$CN" >/dev/null 2>&1 || true
# Launch the game container directly (mirror session-run.sh) so we control the name.
ASSETS=/home/neob91/Games/LutrisDX/drive_c/DX
HERE=/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uplayctl/game
export UPLAYCTL_ASSET_ROOT="$ASSETS"
echo "[boot_watch] building image..." | tee -a "$RESULT"
flock /tmp/dx-lum-imgbuild.lock bash "$HERE/build-image.sh" >>"$RESULT" 2>&1
echo "[boot_watch] running container..." | tee -a "$RESULT"
docker run -d --name "$CN" -e LAUNCH_UED=0 -e DX_MAP="$MAP" \
  -e BOOT_LINK_S=600 -e DX_LAUNCH_TRIES=8 -e DX_ATTEMPT_S=90 \
  --cap-add=SYS_PTRACE \
  -v "$ASSETS":/deusex:ro dx-lum-game >/dev/null 2>>"$RESULT" || { echo "RUN_FAILED" | tee -a "$RESULT"; exit 1; }

END=$(( $(date +%s) + MINS*60 ))
last_lvl=""
while [ "$(date +%s)" -lt "$END" ]; do
  sleep 12
  alive=$(docker ps --format '{{.Names}}' | grep -cx "$CN")
  if [ "$alive" != "1" ]; then echo "[$(date +%H:%M:%S)] CONTAINER_DIED" | tee -a "$RESULT"; docker logs "$CN" 2>&1 | tail -20 | tee -a "$RESULT"; break; fi
  # current level via console
  lvl=$(docker exec "$CN" python3 - <<'PY' 2>/dev/null
import socket
try:
    s=socket.create_connection(("127.0.0.1",7777),timeout=5); s.settimeout(4)
    try: s.recv(256)
    except OSError: pass
    s.sendall(b"#9 GetCurrentLevelName\n")
    buf=b""
    while b"OK " not in buf and b"ERR " not in buf:
        d=s.recv(4096)
        if not d: break
        buf+=d
    for ln in buf.decode(errors="replace").replace("\r","").splitlines():
        if "LevelName " in ln: print(ln.split("LevelName ",1)[1].strip())
except Exception as e:
    pass
PY
)
  # singularity count + log size
  sing=$(docker exec "$CN" sh -c 'grep -c "Anomalous singularity" /work/dx/System/DeusEx.log 2>/dev/null || echo 0')
  logsz=$(docker exec "$CN" sh -c 'wc -c < /work/dx/System/DeusEx.log 2>/dev/null || echo 0')
  echo "[$(date +%H:%M:%S)] level='${lvl:-?}' singularities=$sing logbytes=$logsz" | tee -a "$RESULT"
  if [ "${sing:-0}" -gt 0 ]; then
    echo "CRASH_REPRODUCED level='$lvl' singularities=$sing" | tee -a "$RESULT"
    break
  fi
  if [ "$lvl" = "$MAP" ] && [ "$lvl" = "$last_lvl" ]; then
    : # on target, keep watching for singularities
  fi
  last_lvl="$lvl"
done
echo "=== entrypoint log tail ===" | tee -a "$RESULT"
docker logs "$CN" 2>&1 | tail -25 | tee -a "$RESULT"
echo "BOOTWATCH_DONE" | tee -a "$RESULT"
