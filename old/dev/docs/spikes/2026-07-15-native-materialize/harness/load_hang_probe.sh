#!/usr/bin/env bash
# load_hang_probe.sh — boot a map headless and pin WHERE the loader stalls.
#
# The native-built real levels (NativeUnatco.dx etc.) load-HANG: DeusEx.exe spins ~95% CPU for
# minutes with no link-up.  This probe boots the map in the dx-lum-game container, then samples,
# on a fixed cadence: (a) DeusEx.exe CPU%, (b) DeusEx.log line count + last line, (c) whether the
# console link is up.  A CPU-bound loop shows as "CPU high, log line count FROZEN" — and the last
# log line names the load phase that is looping.  Bounded; never an open-ended wait.
#
# Usage: load_hang_probe.sh <MAP> [minutes]      (default 7 min)
# Writes a transcript to /tmp/loadhang_<MAP>.txt and the full container log to
#   dev/docs/spikes/2026-07-15-native-materialize/harness/_out/loadhang_<MAP>.log  (gitignored _out).
set -u
MAP="${1:-NativeUnatco}"
MINS="${2:-7}"
CN="loadhang-$MAP"
ASSETS=/home/neob91/Games/LutrisDX/drive_c/DX
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/_out"; mkdir -p "$OUT"
RESULT="/tmp/loadhang_${MAP}.txt"; : > "$RESULT"
LOGCOPY="$OUT/loadhang_${MAP}.log"

log(){ echo "$@" | tee -a "$RESULT"; }
log "[loadhang] map=$MAP cn=$CN mins=$MINS  $(date -u +%H:%M:%S)Z"

docker rm -f "$CN" >/dev/null 2>&1 || true
# Give it plenty of link budget so the probe (not the relaunch wrapper) owns the timeout, and a
# single launch attempt so we watch ONE load rather than relaunch churn.
docker run -d --name "$CN" -e LAUNCH_UED=0 -e DX_MAP="$MAP" \
  -e BOOT_LINK_S=$((MINS*60)) -e DX_LAUNCH_TRIES=1 -e DX_ATTEMPT_S=$((MINS*60)) \
  --cap-add=SYS_PTRACE \
  -v "$ASSETS":/deusex:ro dx-lum-game >/dev/null 2>>"$RESULT" || { log "RUN_FAILED"; exit 1; }

LOG=/work/dx/System/DeusEx.log
END=$(( $(date +%s) + MINS*60 ))
prev_lines=-1; frozen=0
while [ "$(date +%s)" -lt "$END" ]; do
  sleep 15
  alive=$(docker ps --format '{{.Names}}' | grep -cx "$CN")
  if [ "$alive" != "1" ]; then log "[$(date -u +%H:%M:%S)Z] CONTAINER_DIED"; break; fi
  # DeusEx.exe CPU% (sum across threads) + RSS, from ps inside the container
  read cpu rss <<<"$(docker exec "$CN" sh -c "ps -eo pcpu,rss,comm 2>/dev/null | awk '/DeusEx.exe/{c+=\$1; r+=\$2} END{printf \"%.0f %d\", c, r}'" 2>/dev/null)"
  lines=$(docker exec "$CN" sh -c "wc -l < $LOG 2>/dev/null || echo 0" 2>/dev/null)
  last=$(docker exec "$CN" sh -c "tail -n 1 $LOG 2>/dev/null" 2>/dev/null)
  link=$(docker exec "$CN" sh -c "netstat -ltn 2>/dev/null | grep -q ':7777 ' && echo UP || echo down" 2>/dev/null)
  if [ "$lines" = "$prev_lines" ]; then frozen=$((frozen+1)); else frozen=0; fi
  prev_lines="$lines"
  log "[$(date -u +%H:%M:%S)Z] cpu=${cpu:-?}% rss=${rss:-?}KB loglines=${lines:-?} frozen=${frozen}x link=${link:-?} last='${last}'"
  # link up alone is NOT proof of load: :7777 listens on the boot DX.dx BEFORE the travel.
  # Confirm GetCurrentLevelName actually equals the target map before declaring loaded.
  if [ "$link" = "UP" ]; then
    lvl=$(docker exec "$CN" python3 - <<'PY' 2>/dev/null
import socket
try:
    s=socket.create_connection(("127.0.0.1",7777),timeout=5); s.settimeout(4)
    try: s.recv(256)
    except OSError: pass
    s.sendall(b"#9 GetCurrentLevelName\n"); buf=b""
    while b"OK " not in buf and b"ERR " not in buf:
        d=s.recv(4096)
        if not d: break
        buf+=d
    for ln in buf.decode(errors="replace").replace("\r","").splitlines():
        if "LevelName " in ln: print(ln.split("LevelName ",1)[1].strip())
except Exception: pass
PY
)
    if [ "$lvl" = "$MAP" ]; then
      log "LOADED_OK level='$lvl' (target reached, no hang)"; break
    else
      log "  (link up on '${lvl:-?}', not yet target '$MAP' — travel in progress/failed; keep watching)"
    fi
  fi
done

log "=== DeusEx.log tail (last 40) ==="
docker exec "$CN" sh -c "tail -n 40 $LOG 2>/dev/null" | tee -a "$RESULT"
docker cp "$CN:$LOG" "$LOGCOPY" 2>/dev/null && log "[full log copied to $LOGCOPY ($(wc -l < "$LOGCOPY" 2>/dev/null) lines)]"
log "LOADHANG_DONE map=$MAP"
docker rm -f "$CN" >/dev/null 2>&1 || true
