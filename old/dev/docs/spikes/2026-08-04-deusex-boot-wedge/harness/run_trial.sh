#!/usr/bin/env bash
# run_trial.sh — one instrumented boot trial. Boots a dx-lum-uned container (Xvfb up,
# LAUNCH_UED=0), stages inputs + instrument_boot.sh, runs it, copies sample.log out.
# Usage: run_trial.sh <label> <outdir>   [env knobs via UED_*/WINE* exported by caller]
#   Optional: DOCKER_MEM=<val> passes --memory (to test if the cap is raisable)
#             DOCKER_CPUSET=<val> passes --cpuset-cpus
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../../.." && pwd)"
LABEL="${1:?label}"; OUT="${2:?outdir}"; mkdir -p "$OUT"
DXSYS="$REPO/.claude/worktrees/installer-url/dev/games/dxreal/system"
TEX="$REPO/_scratch/roomtex"
ROOM="$REPO/_scratch/roomexec/room.dx"
PKG="$REPO/dev/docs/spikes/2026-08-04-generic-hud-hide/harness/UedPreview.u"
C="dxboot-$LABEL"

[ -d "$DXSYS" ] || { echo "missing dxreal system at $DXSYS" >&2; exit 2; }
[ -e "$PKG" ] || { echo "missing UedPreview.u at $PKG" >&2; exit 2; }

docker rm -f "$C" >/dev/null 2>&1 || true
RUNARGS=(-d --name "$C" -e LAUNCH_UED=0 -e UED_GEOMETRY=1400x1050x24 -v "$DXSYS":/gsys -v "$TEX":/gtex)
[ -n "${DOCKER_MEM:-}" ] && RUNARGS+=(--memory="$DOCKER_MEM" --memory-swap="$DOCKER_MEM")
[ -n "${DOCKER_CPUSET:-}" ] && RUNARGS+=(--cpuset-cpus="$DOCKER_CPUSET")
echo "[trial:$LABEL] docker run ${RUNARGS[*]##*/}"
docker run "${RUNARGS[@]}" dx-lum-uned >/dev/null
for _ in $(seq 1 60); do docker exec "$C" bash -lc 'xdpyinfo -display :99 >/dev/null 2>&1' && break; sleep 1; done

docker exec "$C" bash -lc 'mkdir -p /work'
docker cp "$PKG"  "$C:/work/UedPreview.u" >/dev/null
docker cp "$ROOM" "$C:/work/room.dx" >/dev/null
docker cp "$HERE/instrument_boot.sh" "$C:/work/instrument_boot.sh" >/dev/null

echo "[trial:$LABEL] cap=$(docker exec "$C" cat /sys/fs/cgroup/memory.max) knobs: UED_CPUSET=${UED_CPUSET:-} WINEESYNC=${WINEESYNC:-1} WINEFSYNC=${WINEFSYNC:-1} WINE_DISABLE_FAST_SYNC=${WINE_DISABLE_FAST_SYNC:-} UED_INI_EXTRA=${UED_INI_EXTRA:-}"
set +e
docker exec \
  -e UED_CPUSET="${UED_CPUSET:-}" -e WINEESYNC="${WINEESYNC:-1}" -e WINEFSYNC="${WINEFSYNC:-1}" \
  -e WINE_DISABLE_FAST_SYNC="${WINE_DISABLE_FAST_SYNC:-}" -e UED_WINDOW_S="${UED_WINDOW_S:-120}" \
  -e UED_INI_EXTRA="${UED_INI_EXTRA:-}" \
  "$C" bash /work/instrument_boot.sh > "$OUT/${LABEL}.console.log" 2>&1
RC=$?
set -e
docker cp "$C:/work/sample.log" "$OUT/${LABEL}.sample.log" >/dev/null 2>&1 || echo "no sample.log"
docker exec "$C" bash -lc 'tr -d "\000" < /work/dx/System/DeusEx.log' > "$OUT/${LABEL}.deusex.log" 2>/dev/null || true
docker rm -f "$C" >/dev/null 2>&1 || true
echo "[trial:$LABEL] rc=$RC (0=linked, 7=wedged)  -> $OUT/${LABEL}.*"
exit $RC
