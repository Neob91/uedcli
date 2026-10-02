#!/bin/bash
# patient fast-relaunch: cold FEX boots take ~78s to reach the banner, then either progress or
# wedge (0% CPU lost-wakeup). Per try: wait up to 100s for progress/link, else relaunch. 18 tries.
set -u
FEXIP=172.22.0.2; XIP=172.22.0.3
LOG=/tmp/claude-501/-workspace-uedcli/bc8deb71-f9ac-4742-89f5-ebe03b92ae0b/scratchpad/host_boot3.out
: > "$LOG"; say(){ echo "$(date +%H:%M:%S) $*" >>"$LOG"; }
portopen(){ docker exec driver-game python3 -c "import socket,sys
try: socket.create_connection(('$FEXIP',7777),timeout=3).close(); sys.exit(0)
except Exception: sys.exit(1)" 2>/dev/null; }
loglines(){ docker exec fex-game bash -c 'wc -l </game/System/boot.log 2>/dev/null' 2>/dev/null|grep -avE Unknown|tr -d ' '; }
ENV='export WINEARCH=win32 WINEPREFIX=/wineprefix32c WINELOADER=/opt/wine-stable/bin/wine WINEDLLPATH=/opt/wine-stable/lib/wine/i386-windows XDG_RUNTIME_DIR=/run/user/0 DISPLAY='"$XIP"':99 WINEDEBUG=-all WINEESYNC=1 WINEFSYNC=1 WINEDLLOVERRIDES="winealsa.drv=d;mscoree=d;mshtml=d"; W=/opt/wine-stable/bin/wine'
docker exec fex-game bash -c "$ENV; timeout 70 FEXBash -c \"\$W wineboot -u\" >/tmp/wb.log 2>&1"
say "warm rc=$(docker exec fex-game bash -c 'tail -1 /tmp/wb.log' 2>/dev/null|grep -avE Unknown)"
for try in $(seq 1 18); do
  docker exec fex-game bash -c 'pkill -9 -x DeusEx.exe 2>/dev/null; true' 2>/dev/null; sleep 3
  docker exec -d fex-game bash -c "$ENV; cd /game/System; rm -f Running.ini boot.log; : > boot.log; setsid bash -c \"cd /game/System && exec FEXBash -c \\\"cd /game/System && exec \$W DeusEx.exe -log=boot.log -nosound\\\"\" >/tmp/dxl.log 2>&1"
  say "try $try launched"
  ok=0; prog=0
  for s in $(seq 1 20); do   # up to 100s
    sleep 5
    portopen && { say "try $try LINK t=$((s*5))s"; ok=1; break; }
    LL=$(loglines); [ -z "$LL" ] && LL=0
    [ "$LL" -gt 40 ] && { say "try $try PROGRESS $LL"; prog=1; break; }
  done
  if [ "$ok" = 0 ] && [ "$prog" = 1 ]; then
    for w in $(seq 1 80); do sleep 3; portopen && { say "try $try LINK-late"; ok=1; break; }
      DF=$(docker exec fex-game bash -c 'tr -d "\000" </game/System/boot.log|grep -ac "Double fault"' 2>/dev/null|grep -avE Unknown|tr -d ' '); [ "${DF:-0}" -gt 0 ] && { say "try $try CRASH"; break; }; done
  fi
  [ "$ok" = 1 ] && { say "SUCCESS try $try"; break; }
  say "try $try wedge(loglines=$(loglines))"
done
say ALLDONE
