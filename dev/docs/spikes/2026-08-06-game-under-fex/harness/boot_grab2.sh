#!/bin/bash
# boot_grab2.sh — robust boot: warm ONE persistent wineserver, then relaunch DeusEx on the SAME
# server (killing only DeusEx on a banner-wedge, never the server — killing the server re-triggers
# the cold wineserver race that wedges the boot). Runs INSIDE fex-game.
# Env: XIP, ENGINE(dx|stock), TRIES(default 8), WEDGE_S(default 55), LABEL
set -u
XIP="${XIP:-172.22.0.3}"; ENGINE="${ENGINE:-dx}"; TRIES="${TRIES:-8}"; WEDGE_S="${WEDGE_S:-55}"; LABEL="${LABEL:-bg2}"
export WINEARCH=win32 WINEPREFIX=/wineprefix32c WINELOADER=/opt/wine-stable/bin/wine
export WINEDLLPATH=/opt/wine-stable/lib/wine/i386-windows XDG_RUNTIME_DIR=/run/user/0
mkdir -p /run/user/0; chmod 1777 /run/user/0
export DISPLAY=$XIP:99 WINEDEBUG=-all WINEESYNC=1 WINEFSYNC=1
export WINEDLLOVERRIDES="winealsa.drv=d;mscoree=d;mshtml=d"
W=/opt/wine-stable/bin/wine
FB(){ FEXBash -c "$*"; }
listening(){ FB "netstat -ltn 2>/dev/null" 2>/dev/null | grep -q ':7777 '; }
cd /game/System
cp -f Default.ini DeusEx.ini 2>/dev/null || true
python3 /root/mkini.py DeusEx.ini "$ENGINE" 4 >/dev/null
# --- warm ONE persistent wineserver + prefix (all via FEXBash; direct wine needs binfmt) ---
FB "$W wineserver -k" 2>/dev/null; sleep 2
setsid bash -c "exec FEXBash -c \"$W wineserver -p -f\"" >/tmp/wsrv.log 2>&1 &
sleep 3
timeout 70 FB "$W wineboot -u" >/tmp/wboot.log 2>&1; echo "[$LABEL] wineboot rc=$?"
timeout 30 FB "$W cmd /c echo WARMOK" 2>/dev/null | grep -aq WARMOK && echo "[$LABEL] wine healthy" || echo "[$LABEL] WARN wine not confirmed healthy"
_launch(){ rm -f Running.ini boot.log; : > boot.log
  setsid bash -c "cd /game/System && exec FEXBash -c \"cd /game/System && exec $W DeusEx.exe -log=boot.log -nosound\"" >/tmp/dxl.log 2>&1 & }
LINKED=0
for try in $(seq 1 "$TRIES"); do
  echo "[$LABEL] launch attempt $try/$TRIES (ENGINE=$ENGINE)"
  _launch
  t=0; wedged=1
  while [ "$t" -lt "$WEDGE_S" ]; do
    listening && { LINKED=1; break; }
    if tr -d '\000' < boot.log 2>/dev/null | grep -aq 'Double fault'; then echo "[$LABEL] CRASH during boot"; wedged=0; break; fi
    if [ "$(wc -l < boot.log 2>/dev/null||echo 0)" -gt 40 ]; then wedged=0; break; fi   # progressing
    sleep 5; t=$((t+5))
  done
  [ "$LINKED" = 1 ] && break
  if [ "$wedged" = 1 ]; then
    echo "[$LABEL] banner-wedge (<=40 lines in ${WEDGE_S}s) — kill DeusEx ONLY, keep server, retry"
    pkill -9 -f DeusEx.exe 2>/dev/null; sleep 3; continue
  fi
  # progressing: wait for link up to 180s
  echo "[$LABEL] boot progressing ($(wc -l <boot.log) lines) — waiting for link"
  for _ in $(seq 1 60); do listening && { LINKED=1; break; }; \
    tr -d '\000' <boot.log 2>/dev/null | grep -aq 'Double fault' && { echo "[$LABEL] CRASH while progressing"; break; }; sleep 3; done
  [ "$LINKED" = 1 ] && break
  pkill -9 -f DeusEx.exe 2>/dev/null; sleep 3
done
echo "[$LABEL] BOOT LINKED=$LINKED"
echo "[$LABEL] --- key log ---"
tr -d '\000' < boot.log | grep -aE "LoadMap:|Bringing Level .* up for play|listening on 7777|Browse:|Failed to enter|ULevel::PostLoad|Double fault|Anomalous" | grep -avE "FireTexture|LodMesh|Draw" | tail -14
if [ "$LINKED" = 1 ]; then
  echo "[$LABEL] --- current level / pose / clean ---"
  FB "python3 - <<PY 2>/dev/null
import socket,time
def q(c,t=12):
    s=socket.create_connection(('127.0.0.1',7777),timeout=t);s.settimeout(t)
    try:s.recv(200)
    except:pass
    s.sendall((c+'\n').encode());time.sleep(0.4);b=b'';t0=time.time()
    while time.time()-t0<t:
        try:d=s.recv(4096)
        except:break
        if not d:break
        b+=d
        if b' OK ' in b or b' ERR ' in b:break
    s.close();return b
print('  level:',q('#1 GetCurrentLevelName'))
print('  pose :',q('#2 PrepareCamera 0 0 0 0 0'))
print('  clean:',q('#3 Clean generic'))
PY"
fi
