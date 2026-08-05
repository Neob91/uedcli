#!/usr/bin/env bash
# min_trial.sh — one minimal-footprint boot trial on the host. Fresh dx-lum-uned
# container (Xvfb up, LAUNCH_UED=0), stages the minimal inputs, runs minimal_boot.sh,
# copies sample.log + DeusEx.log out, prints rc + peak memory.
# Usage: min_trial.sh <label> <outdir>   [knobs via MINSET/ENGINE/CACHE/WEDGE_S/WINDOW_S]
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../../.." && pwd)"
LABEL="${1:?label}"; OUT="${2:?outdir}"; mkdir -p "$OUT"
DXSYS="$REPO/.claude/worktrees/installer-url/dev/games/dxreal/system"
TEX="$REPO/_scratch/roomtex"
ROOM="$REPO/_scratch/roomexec/room.dx"
PKG="$REPO/dev/docs/spikes/2026-08-04-generic-hud-hide/harness/UedPreview.u"
C="dxmin-$LABEL"
[ -d "$DXSYS" ] || { echo "missing dxreal system at $DXSYS" >&2; exit 2; }
[ -e "$PKG" ]   || { echo "missing UedPreview.u at $PKG" >&2; exit 2; }

docker rm -f "$C" >/dev/null 2>&1 || true
docker run -d --name "$C" -e LAUNCH_UED=0 -e UED_GEOMETRY=800x600x24 \
  -v "$DXSYS":/gsys -v "$TEX":/gtex dx-lum-uned >/dev/null
for _ in $(seq 1 60); do docker exec "$C" bash -lc 'xdpyinfo -display :99 >/dev/null 2>&1' && break; sleep 1; done

docker exec "$C" bash -lc 'mkdir -p /work'
docker cp "$PKG"  "$C:/work/UedPreview.u" >/dev/null
docker cp "$ROOM" "$C:/work/room.dx" >/dev/null
docker cp "$HERE/minimal_boot.sh" "$C:/work/minimal_boot.sh" >/dev/null

echo "[trial:$LABEL] MINSET=${MINSET:-stock} ENGINE=${ENGINE:-} CACHE=${CACHE:-4} cap=$(docker exec "$C" cat /sys/fs/cgroup/memory.max)"
docker exec \
  -e MINSET="${MINSET:-stock}" -e ENGINE="${ENGINE:-}" -e CACHE="${CACHE:-4}" \
  -e WEDGE_S="${WEDGE_S:-45}" -e WINDOW_S="${WINDOW_S:-140}" \
  -e WINEESYNC="${WINEESYNC:-1}" -e WINEFSYNC="${WINEFSYNC:-1}" \
  "$C" bash /work/minimal_boot.sh > "$OUT/${LABEL}.console.log" 2>&1
RC=$?
docker cp "$C:/work/sample.log" "$OUT/${LABEL}.sample.log" >/dev/null 2>&1 || echo "no sample.log"
docker exec "$C" bash -lc 'tr -d "\000" < /work/dx/System/DeusEx.log' > "$OUT/${LABEL}.deusex.log" 2>/dev/null || true
docker cp "$C:/work/launch-err.log" "$OUT/${LABEL}.launch-err.log" >/dev/null 2>&1 || true
docker cp "$C:/work/launch.log"     "$OUT/${LABEL}.launch.log"     >/dev/null 2>&1 || true
if [ "${KEEP:-0}" = 1 ]; then echo "[trial:$LABEL] KEEP=1 container $C left running"; else docker rm -f "$C" >/dev/null 2>&1 || true; fi
echo "[trial:$LABEL] rc=$RC (0=linked 7=wedged 8=loaderror) -> $OUT/${LABEL}.*"
exit $RC
