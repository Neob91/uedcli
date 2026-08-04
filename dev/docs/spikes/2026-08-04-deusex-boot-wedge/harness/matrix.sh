#!/usr/bin/env bash
# matrix.sh <config-label> <N> <outdir> — run N boot trials of one config, tally link vs wedge.
# The config is selected by <config-label>; each maps to a set of env knobs. Trials run
# sequentially (emulation is CPU-heavy; parallel booting would bias the timing-race result).
# Prints one line per trial (LINK/WEDGE + link-time) and a final tally.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
LABEL="${1:?config-label}"; N="${2:?N}"; OUT="${3:?outdir}"; mkdir -p "$OUT"
WIN="${MATRIX_WINDOW_S:-90}"

case "$LABEL" in
  esync-fsync)   E=("WINEESYNC=1" "WINEFSYNC=1") ;;                       # current default
  fsync-only)    E=("WINEESYNC=0" "WINEFSYNC=1") ;;                       # no esync, fsync via futex_waitv
  server-side)   E=("WINEESYNC=0" "WINEFSYNC=0") ;;                       # pure wineserver sync
  esync-only)    E=("WINEESYNC=1" "WINEFSYNC=0") ;;                       # esync, no fsync
  cpuset1)       E=("WINEESYNC=1" "WINEFSYNC=1" "UED_CPUSET=0") ;;        # serialize threads, default sync
  cpuset1-fsync) E=("WINEESYNC=0" "WINEFSYNC=1" "UED_CPUSET=0") ;;        # serialize + fsync-only
  *) echo "unknown config: $LABEL" >&2; exit 2 ;;
esac

pass=0; fail=0
for i in $(seq 1 "$N"); do
  RL="$LABEL-t$i"
  start=$(date +%s)
  ( export "${E[@]}"; UED_WINDOW_S="$WIN" "$HERE/run_trial.sh" "$RL" "$OUT" >/dev/null 2>&1 )
  rc=$?
  el=$(( $(date +%s) - start ))
  # link time: last t= in sample.log before LINK BOUND
  lt=$(grep -oE 'LINK BOUND at t=[0-9]+' "$OUT/$RL.sample.log" 2>/dev/null | grep -oE '[0-9]+' | tail -1)
  ll=$(grep -oE 'loglines=[0-9]+' "$OUT/$RL.sample.log" 2>/dev/null | grep -oE '[0-9]+' | tail -1)
  if [ "$rc" = "0" ]; then pass=$((pass+1)); echo "  [$LABEL] trial $i: LINK  (link@${lt}s, wall ${el}s, finallog=$ll)";
  else fail=$((fail+1)); echo "  [$LABEL] trial $i: WEDGE (wall ${el}s, finallog=$ll)"; fi
done
echo "=== [$LABEL] TALLY: LINK=$pass / $N  (knobs: ${E[*]}) ==="
