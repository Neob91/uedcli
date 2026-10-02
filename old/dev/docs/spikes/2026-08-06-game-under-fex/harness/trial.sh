#!/bin/bash
# trial.sh — one FEX+wine10 DeusEx trial: boot menu, bind :7777, ClientTravel to a target map,
# classify SURVIVED vs CRASHED, dump the primary crash stack. Runs INSIDE fex-game.
# Env knobs:
#   XIP      X host (default 172.22.0.3)
#   ENGINE   dx|stock (default dx)
#   CACHE    CacheSizeMegs (default 4)
#   LIBGL    1 => LIBGL_ALWAYS_SOFTWARE=1
#   TARGET   map to travel to (default room.dx)
#   LABEL    tag for logs (default trial)
#   WINDOW_S menu-boot wait (default 220)
set -u
XIP="${XIP:-172.22.0.3}"; ENGINE="${ENGINE:-dx}"; CACHE="${CACHE:-4}"; LIBGL="${LIBGL:-0}"
TARGET="${TARGET:-room.dx}"; LABEL="${LABEL:-trial}"; WINDOW_S="${WINDOW_S:-220}"
export WINEARCH=win32 WINEPREFIX=/wineprefix32c WINELOADER=/opt/wine-stable/bin/wine
export WINEDLLPATH=/opt/wine-stable/lib/wine/i386-windows XDG_RUNTIME_DIR=/run/user/0
mkdir -p /run/user/0; chmod 1777 /run/user/0
export DISPLAY=$XIP:99 WINEDEBUG=-all WINEESYNC=1 WINEFSYNC=1
export WINEDLLOVERRIDES="winealsa.drv=d;mscoree=d;mshtml=d"
[ "$LIBGL" = 1 ] && export LIBGL_ALWAYS_SOFTWARE=1
[ "${WLAA:-0}" = 1 ] && export WINE_LARGE_ADDRESS_AWARE=1
W=/opt/wine-stable/bin/wine
listening(){ FEXBash -c "netstat -ltn 2>/dev/null" | grep -q ':7777 '; }
cd /game/System
$W wineserver -k 2>/dev/null; sleep 1
cp -f Default.ini DeusEx.ini 2>/dev/null || true
python3 /root/mkini.py DeusEx.ini "$ENGINE" "$CACHE" >/dev/null
rm -f Running.ini boot.log; : > boot.log
echo "[$LABEL] boot ENGINE=$ENGINE CACHE=$CACHE LIBGL=$LIBGL TARGET=$TARGET FEXcfg=$(cat ~/.config/fex-emu/Config.json|tr -d '\n')"
setsid bash -c "cd /game/System && exec FEXBash -c \"cd /game/System && exec $W DeusEx.exe -log=boot.log -nosound\"" >/tmp/dxl.log 2>&1 &
t=0; LINKED=0
while [ "$t" -lt "$WINDOW_S" ]; do
  listening && { LINKED=1; break; }
  OOM=$(awk '/oom_kill/{print $2}' /sys/fs/cgroup/memory.events)
  [ "${OOM:-0}" -gt 0 ] && { echo "[$LABEL] OOM at t=${t}s"; break; }
  sleep 4; t=$((t+4))
done
if [ "$LINKED" != 1 ]; then echo "[$LABEL] NO_LINK (menu never bound in ${WINDOW_S}s)"; exit 3; fi
AN=$(awk '/^anon /{printf "%d", $2/1024/1024}' /sys/fs/cgroup/memory.stat)
echo "[$LABEL] LINK up t=${t}s anon=${AN}MiB — traveling to $TARGET"
FEXBash -c "python3 - <<PY
import socket,time
def q(c,t=12):
    s=socket.create_connection(('127.0.0.1',7777),timeout=t); s.settimeout(t)
    try: s.recv(200)
    except: pass
    s.sendall((c+'\n').encode()); time.sleep(0.4); buf=b''; t0=time.time()
    while time.time()-t0<t:
        try: d=s.recv(4096)
        except: break
        if not d: break
        buf+=d
        if b' OK ' in buf or b' ERR ' in buf: break
    s.close(); return buf
print('  travel:', q('#2 TravelToLevel $TARGET'))
alive=False; lvl=b''
for i in range(10):
    time.sleep(2)
    try: lvl=q('#%d GetCurrentLevelName'%(10+i),5)
    except Exception as e: print('  link-dead:',e); break
    if b'LevelName' in lvl: alive=True
    if b'${TARGET%.*}' in lvl.lower() or b'${TARGET}' in lvl: print('  ARRIVED', lvl); break
print('  RESULT', 'SURVIVED' if alive else 'CRASHED', 'last=',lvl)
PY"
# primary crash stack (before the double-fault flood)
tr -d '\000' < boot.log > /tmp/clean_$LABEL.log
FIRST=$(grep -n 'Double fault' /tmp/clean_$LABEL.log | head -1 | cut -d: -f1)
if [ -n "$FIRST" ]; then
  START=$((FIRST-30)); [ $START -lt 1 ] && START=1
  echo "[$LABEL] --- primary crash stack ---"
  sed -n "${START},${FIRST}p" /tmp/clean_$LABEL.log | grep -aE 'Critical|Assert|GObj|StaticAllocate|access|General prot|Exit: Exec' | grep -avE 'FireTexture|LodMesh|Draw|UTexture::(Tick|Update)' | head -25
else
  echo "[$LABEL] no double-fault — checking for assertion/link state"
  grep -aE 'Assert|GObjAvailable|StaticAllocateObject|Critical' /tmp/clean_$LABEL.log | tail -10
fi
