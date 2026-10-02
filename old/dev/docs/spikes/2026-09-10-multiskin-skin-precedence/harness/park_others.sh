#!/usr/bin/env bash
# Move every window EXCEPT the given one off-screen (keeping its size), so an
# `import -window` of the survivor reads real pixels instead of whatever is stacked over it
# (X11 here has no backing store). Never moves the survivor: a `CAMERA OPEN` viewport blanks to
# black on any re-render (`unrealed/rendering.md`).
set -eu
keep="$1"
export DISPLAY=:99
wmctrl -l -G | while read -r id _d _x _y w h _rest; do
  [ "$id" = "$keep" ] && continue
  wmctrl -i -r "$id" -e "0,3200,3200,$w,$h"
done
sleep 1
wmctrl -l -G
