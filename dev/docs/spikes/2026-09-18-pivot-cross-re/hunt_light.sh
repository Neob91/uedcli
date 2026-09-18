#!/bin/bash
# Click a small grid around the light sprite until EDIT COPY reports a selected actor.
for x in 778 779 780 781 782 783; do
  for y in 249 251 253 255 257 259; do
    bash _scratch/pivotre/ctrlclick.sh "$x" "$y" none >/dev/null
    sleep 0.4
    out=$(docker exec pivot-probe python3 /opt/uned/wine_ctl.py edit-copy 2>&1 | grep -c "Begin Actor")
    if [ "$out" != "0" ]; then
      echo "HIT at $x,$y -> $out actor(s)"
      docker exec pivot-probe python3 /opt/uned/wine_ctl.py edit-copy 2>&1 | grep "Begin Actor"
      exit 0
    fi
  done
done
echo "no hit"
