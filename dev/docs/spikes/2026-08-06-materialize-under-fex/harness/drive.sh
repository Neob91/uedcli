#!/bin/bash
# drive.sh — type one UnrealEd command box line into the FEX editor via the amd64 `driver`
# container over the shared xdisp display, by window title (cross-container: no editor PID here).
# Usage: DISPLAY set by caller; args: the command line. Prints "CRASH" if a Critical Error opens.
set -u
D=":99"; XIP="${XIP:?}"
export DISPLAY="$XIP$D"
line="$*"
# biggest "Unreal Editor 2.2 for Deus Ex" window = the main MDI frame (not the Log Window)
best=""; area=0
for w in $(xdotool search --name "Unreal Editor 2.2 for Deus Ex" 2>/dev/null); do
  eval "$(xdotool getwindowgeometry --shell "$w")"; a=$((WIDTH*HEIGHT))
  [ "$a" -gt "$area" ] && { area=$a; best=$w; }
done
[ -z "$best" ] && { echo "NO-FRAME"; exit 1; }
eval "$(xdotool getwindowgeometry --shell "$best")"
xdotool windowactivate --sync "$best"; sleep 0.3
cx=$((X+370)); cy=$((Y+HEIGHT-36))
xdotool mousemove "$cx" "$cy" click 1; sleep 0.2
xdotool key --clearmodifiers End; xdotool key --clearmodifiers shift+Home; xdotool key --clearmodifiers Delete
xdotool type --delay 10 "$line"
xdotool key --clearmodifiers Return
sleep 0.4
ce=$(xdotool search --name "Critical Error" 2>/dev/null | head -1)
[ -n "$ce" ] && echo "CRASH after: $line" || echo "ok: $line"
