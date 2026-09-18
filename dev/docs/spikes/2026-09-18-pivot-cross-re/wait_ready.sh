#!/bin/bash
# Poll the ephemeral editor container until wine_ctl reports a resolved window id.
c="${1:-pivot-probe}"
for i in $(seq 1 40); do
  s=$(docker exec "$c" python3 /opt/uned/wine_ctl.py status 2>&1)
  if echo "$s" | grep -qE 'window=[0-9]'; then
    echo "READY after ${i} polls: $s"
    exit 0
  fi
  sleep 5
done
echo "NOT READY: $s"
exit 1
