#!/bin/bash
# boot_grab.sh — boot DeusEx via the BOOT-LoadMap path (not runtime ClientTravel) and try to
# land in a chosen map. Idea: the boot "LoadMap: entry.dx" is the ONE map-load path that does
# not corrupt under FEX (runtime ClientTravel PostLoad does). So put our map AT Entry.dx.
# Runs INSIDE fex-game. Leaves the game running; caller grabs the frame from the X host.
# Env: XIP, ENGINE(dx|stock), BOOTMAP(file under /game/Maps to install as Entry.dx; empty=real Entry),
#      LABEL, WINDOW_S(default 240)
set -u
XIP="${XIP:-172.22.0.3}"; ENGINE="${ENGINE:-stock}"; BOOTMAP="${BOOTMAP:-}"; LABEL="${LABEL:-bg}"; WINDOW_S="${WINDOW_S:-240}"
export WINEARCH=win32 WINEPREFIX=/wineprefix32c WINELOADER=/opt/wine-stable/bin/wine
export WINEDLLPATH=/opt/wine-stable/lib/wine/i386-windows XDG_RUNTIME_DIR=/run/user/0
mkdir -p /run/user/0; chmod 1777 /run/user/0
export DISPLAY=$XIP:99 WINEDEBUG=-all WINEESYNC=1 WINEFSYNC=1
export WINEDLLOVERRIDES="winealsa.drv=d;mscoree=d;mshtml=d"
W=/opt/wine-stable/bin/wine
listening(){ FEXBash -c "netstat -ltn 2>/dev/null" 2>/dev/null | grep -q ':7777 '; }
cd /game/System
# route ALL wine maintenance through FEXBash — direct `wine` needs the i386 binfmt handler,
# which is lost after a container restart (routes to a broken qemu-i386). FEXBash invokes FEX
# explicitly, so it is restart-proof.
FEXBash -c "$W wineserver -k" 2>/dev/null; sleep 1
# warm the prefix/services BEFORE launching the game — a cold wineserver bringup races and wedges
# the game at the CPU-detect banner.
timeout 60 FEXBash -c "$W wineboot -u" >/dev/null 2>&1 || true; sleep 1
# install boot map
if [ -n "$BOOTMAP" ]; then
  cp -f "/game/Maps/$BOOTMAP" /game/Maps/Entry.dx
  echo "[$LABEL] installed /game/Maps/$BOOTMAP as Entry.dx ($(stat -c %s /game/Maps/Entry.dx) B)"
else
  cp -f /game/Maps/Entry.dx.orig /game/Maps/Entry.dx
  echo "[$LABEL] using real Entry.dx"
fi
cp -f Default.ini DeusEx.ini 2>/dev/null || true
python3 /root/mkini.py DeusEx.ini "$ENGINE" 4 >/dev/null
echo "[$LABEL] boot ENGINE=$ENGINE"
_launch(){ rm -f Running.ini boot.log; : > boot.log
  setsid bash -c "cd /game/System && exec FEXBash -c \"cd /game/System && exec $W DeusEx.exe -log=boot.log -nosound\"" >/tmp/dxl.log 2>&1 & }
_launch
t=0; LINKED=0; CRASHED=0
while [ "$t" -lt "$WINDOW_S" ]; do
  listening && { LINKED=1; break; }
  if tr -d '\000' < boot.log 2>/dev/null | grep -aq 'Double fault'; then echo "[$LABEL] CRASH during boot t=${t}s"; CRASHED=1; break; fi
  # boot-banner wedge (pipe_read race): log frozen <=22 lines after 40s -> relaunch
  if [ "$t" -ge 40 ] && [ "$(wc -l < boot.log 2>/dev/null||echo 0)" -le 22 ]; then
    echo "[$LABEL] boot-banner wedge at t=${t}s -> relaunch"
    pkill -9 -f DeusEx.exe 2>/dev/null; $W wineserver -k 2>/dev/null; sleep 2; _launch; t=0; continue
  fi
  sleep 4; t=$((t+4))
done
echo "[$LABEL] boot done LINKED=$LINKED t=${t}s"
echo "[$LABEL] --- key log lines ---"
tr -d '\000' < boot.log | grep -aE "LoadMap:|Bringing Level .* up for play|listening on 7777|Browse:|Failed to enter|ULevel::PostLoad|Double fault|Anomalous" | grep -avE "FireTexture|LodMesh|Draw" | tail -14
if [ "$LINKED" = 1 ]; then
  echo "[$LABEL] --- link: current level + pose/clean ---"
  FEXBash -c "python3 - <<PY 2>/dev/null
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
