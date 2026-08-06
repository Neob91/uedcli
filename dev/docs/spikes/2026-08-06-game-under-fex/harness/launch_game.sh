#!/bin/bash
# launch_game.sh — boot DeusEx.exe under FEX+wine10, bind :7777. Runs INSIDE fex-game.
# Knobs (env):
#   XIP        X host ip (Xvfb :99 over TCP)
#   ENGINE     dx | stock                 (mkini.py)
#   CACHE      CacheSizeMegs              (default 4)
#   LIBGL      1 => export LIBGL_ALWAYS_SOFTWARE=1 (editor's fix; game never set it)
#   WINDOW_S   boot wait seconds          (default 180)
# Leaves the game RUNNING (does not kill it) so a driver can travel over :7777.
set -u
XIP="${XIP:-172.22.0.3}"; ENGINE="${ENGINE:-dx}"; CACHE="${CACHE:-4}"; WINDOW_S="${WINDOW_S:-180}"; LIBGL="${LIBGL:-0}"
export WINEARCH=win32 WINEPREFIX=/wineprefix32c WINELOADER=/opt/wine-stable/bin/wine
export WINEDLLPATH=/opt/wine-stable/lib/wine/i386-windows XDG_RUNTIME_DIR=/run/user/0
mkdir -p /run/user/0; chmod 1777 /run/user/0
export DISPLAY=$XIP:99 WINEDEBUG=-all WINEESYNC=1 WINEFSYNC=1
export WINEDLLOVERRIDES="winealsa.drv=d;mscoree=d;mshtml=d"
[ "$LIBGL" = 1 ] && export LIBGL_ALWAYS_SOFTWARE=1
W=/opt/wine-stable/bin/wine
listening(){ FEXBash -c "netstat -ltn 2>/dev/null" | grep -q ':7777 '; }
cd /game/System
cp -f Default.ini DeusEx.ini 2>/dev/null || true
python3 /root/mkini.py DeusEx.ini "$ENGINE" "$CACHE"
$W wineserver -k 2>/dev/null; sleep 1
rm -f Running.ini boot.log; : > boot.log
echo "[launch] DeusEx.exe ENGINE=$ENGINE CACHE=$CACHE LIBGL=$LIBGL FEXcfg=$(cat ~/.config/fex-emu/Config.json|tr -d '\n')"
setsid bash -c "cd /game/System && exec FEXBash -c \"cd /game/System && exec $W DeusEx.exe -log=boot.log -nosound\"" >/tmp/dxl.log 2>&1 &
PEAK=0; LINKED=0; t=0
while [ "$t" -lt "$WINDOW_S" ]; do
  MC=$(cat /sys/fs/cgroup/memory.current 2>/dev/null||echo 0); [ "$MC" -gt "$PEAK" ] && PEAK=$MC
  LL=$(wc -l < boot.log 2>/dev/null||echo 0); OOM=$(awk '/oom_kill/{print $2}' /sys/fs/cgroup/memory.events)
  echo "[t=${t}s] mem=$((MC/1024/1024))MiB peak=$((PEAK/1024/1024))MiB loglines=$LL oom=$OOM"
  listening && { echo "=== LINK BOUND t=${t}s ==="; LINKED=1; break; }
  [ "${OOM:-0}" -gt 0 ] && { echo "=== OOM t=${t}s ==="; break; }
  sleep 4; t=$((t+4))
done
echo "[launch] DONE LINKED=$LINKED peak=$((PEAK/1024/1024))MiB"
echo "[launch] --- boot.log tail ---"; grep -avE "FireTexture|LodMesh|DrawLodMesh|DrawActorSprite|DrawFrame|ConstantTimeTick|UTexture::" boot.log 2>/dev/null | tr -d '\000' | tail -18
[ "$LINKED" = 1 ] && exit 0 || exit 7
