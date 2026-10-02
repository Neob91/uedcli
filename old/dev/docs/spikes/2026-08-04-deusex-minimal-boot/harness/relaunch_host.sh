#!/usr/bin/env bash
# relaunch_host.sh — host driver for the relaunch loop. Frees leftover dx* boot
# containers, starts ONE fresh minimal container, stages inputs + scripts, runs
# relaunch_loop.sh (up to MAXTRIES boots), and on a win copies game_preview_here.png out.
# Usage: relaunch_host.sh <outdir>
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../../.." && pwd)"
OUT="${1:?outdir}"; mkdir -p "$OUT"
DXSYS="$REPO/.claude/worktrees/installer-url/dev/games/dxreal/system"
TEX="$REPO/_scratch/roomtex"
ROOM="$REPO/_scratch/roomexec/room.dx"
PKG="$REPO/dev/docs/spikes/2026-08-04-generic-hud-hide/harness/UedPreview.u"
C="dxmin-loop"

docker ps -a --format '{{.Names}}' | grep -E '^dxmin|^dxboot' | xargs -r docker rm -f >/dev/null 2>&1 || true
docker run -d --name "$C" -e LAUNCH_UED=0 -e UED_GEOMETRY=800x600x24 \
  -v "$DXSYS":/gsys -v "$TEX":/gtex dx-lum-uned >/dev/null
for _ in $(seq 1 60); do docker exec "$C" bash -lc 'xdpyinfo -display :99 >/dev/null 2>&1' && break; sleep 1; done

docker exec "$C" bash -lc 'mkdir -p /work'
docker cp "$PKG"  "$C:/work/UedPreview.u" >/dev/null
docker cp "$ROOM" "$C:/work/room.dx" >/dev/null
docker cp "$HERE/relaunch_loop.sh" "$C:/work/relaunch_loop.sh" >/dev/null
docker cp "$HERE/render_frame.py"  "$C:/work/render_frame.py" >/dev/null

echo "[host] cap=$(docker exec "$C" cat /sys/fs/cgroup/memory.max) starting relaunch loop MAXTRIES=${MAXTRIES:-40}"
docker exec -e MAXTRIES="${MAXTRIES:-40}" -e POLL_S="${POLL_S:-75}" -e WEDGE_S="${WEDGE_S:-40}" -e CACHE="${CACHE:-4}" \
  "$C" bash /work/relaunch_loop.sh
RC=$?
docker cp "$C:/work/game_preview_here.png" "$OUT/game_preview_here.png" >/dev/null 2>&1 \
  && echo "[host] PNG -> $OUT/game_preview_here.png" || echo "[host] no PNG (rc=$RC)"
docker rm -f "$C" >/dev/null 2>&1 || true
echo "[host] rc=$RC (0=linked+rendered 7=all-wedged 8=render-fail)"
exit $RC
