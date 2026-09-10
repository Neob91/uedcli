#!/usr/bin/env bash
# Poll an ephemeral UED22 container until its editor window resolves (parallel-editors.md
# "Readiness": require a NUMERIC window id, not the bare substring).
set -u
c="$1"
for _ in $(seq 1 30); do
  out=$(docker exec "$c" python3 /opt/uned/wine_ctl.py status 2>&1)
  if printf '%s' "$out" | grep -q 'window=[0-9]'; then echo "READY $out"; exit 0; fi
  sleep 5
done
echo "TIMEOUT $out"
exit 1
