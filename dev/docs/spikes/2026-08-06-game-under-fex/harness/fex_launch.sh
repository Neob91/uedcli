#!/bin/bash
# fex_launch.sh — launch DeusEx.exe under FEX+wine10 (prefix already booted, mono disabled).
# Samples memory, polls :7777. CD-dialog / window state captured separately from the X host.
set -u
XIP="${XIP:-172.20.0.2}"; ENGINE="${ENGINE:-stock}"; CACHE="${CACHE:-4}"; WINDOW_S="${WINDOW_S:-120}"
export WINEARCH=win32 WINEPREFIX=/wineprefix32c WINELOADER=/opt/wine-stable/bin/wine
export WINEDLLPATH=/opt/wine-stable/lib/wine/i386-windows XDG_RUNTIME_DIR=/run/user/0
mkdir -p /run/user/0; chmod 1777 /run/user/0
export DISPLAY=$XIP:99 WINEDEBUG=-all WINEESYNC=1 WINEFSYNC=1
export WINEDLLOVERRIDES="winealsa.drv=d;mscoree=d;mshtml=d"
W=/opt/wine-stable/bin/wine
listening(){ FEXBash -c "netstat -ltn 2>/dev/null" | grep -q ':7777 '; }
cd /game/System
python3 /root/mkini.py DeusEx.ini "$ENGINE" "$CACHE"
$W wineserver -k 2>/dev/null; sleep 1
rm -f Running.ini    # crash marker; stale one => "Deus Ex Recovery Mode" modal blocks init
L=boot.log; rm -f "$L"; : > "$L"
echo "[fex] launch DeusEx.exe ENGINE=$ENGINE CACHE=$CACHE"
setsid bash -c "cd /game/System && exec FEXBash -c \"cd /game/System && exec $W DeusEx.exe -log=$L -nosound\"" >/tmp/dxl.log 2>&1 &
PEAK=0; LINKED=0; t=0
while [ "$t" -lt "$WINDOW_S" ]; do
  MC=$(cat /sys/fs/cgroup/memory.current 2>/dev/null || echo 0)
  [ "$MC" -gt "$PEAK" ] && PEAK=$MC
  LL=$(wc -l < "$L" 2>/dev/null || echo 0)
  OOM=$(awk '/oom_kill/{print $2}' /sys/fs/cgroup/memory.events)
  echo "[t=${t}s] mem=$((MC/1024/1024))MiB peak=$((PEAK/1024/1024))MiB loglines=$LL oom_kill=$OOM"
  if listening; then echo "=== LINK BOUND t=${t}s ==="; LINKED=1; break; fi
  if [ "${OOM:-0}" -gt 0 ]; then echo "=== OOM_KILL t=${t}s ==="; break; fi
  sleep 4; t=$((t+4))
done
echo "[fex] DONE LINKED=$LINKED peak=$((PEAK/1024/1024))MiB cap=$(( $(cat /sys/fs/cgroup/memory.max)/1024/1024 ))MiB"
echo "[fex] --- boot.log tail ---"; tail -30 "$L" 2>/dev/null | tr -d '\000'
[ "$LINKED" = 1 ] && exit 0 || exit 7
