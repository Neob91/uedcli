#!/bin/bash
# Real ctrl+left-click at window-relative coords in the ephemeral editor.
# Mirrors wine_ctl.py cmd_click (focus, window-relative -> absolute, XTEST click)
# but wraps the click in keydown/keyup ctrl inside ONE xdotool chain.
set -e
X="$1"; Y="$2"; MOD="${3:-ctrl}"
docker exec -i -e DISPLAY=:99 pivot-probe python3 - "$X" "$Y" "$MOD" <<'PY'
import subprocess, sys, re
sys.path.insert(0, "/opt/uned")
import wine_ctl
x, y, mod = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
wid = wine_ctl._assert_alive()
wine_ctl._focus(wid, 0.3)
ox, oy = wine_ctl._window_position(wid)
chain = ["xdotool", "mousemove", str(ox + x), str(oy + y)]
if mod != "none":
    chain += ["keydown", mod, "click", "1", "keyup", mod]
else:
    chain += ["click", "1"]
subprocess.run(chain, check=True)
print("clicked", ox + x, oy + y, "mod=", mod)
PY
