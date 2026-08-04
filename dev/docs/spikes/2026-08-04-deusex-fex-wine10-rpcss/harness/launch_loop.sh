#!/bin/bash
export WINEARCH=win32 WINEPREFIX=/wineprefix32c WINELOADER=/opt/wine-stable/bin/wine
export WINEDLLPATH=/opt/wine-stable/lib/wine/i386-windows XDG_RUNTIME_DIR=/run/user/0
mkdir -p /run/user/0; chmod 1777 /run/user/0
export DISPLAY=172.17.0.3:99 WINEDEBUG=-all WINEESYNC=1 WINEFSYNC=1 WINEDLLOVERRIDES="winealsa.drv=d"
listening(){ netstat -ltn 2>/dev/null | grep -q ':7777 '; }
cd /game/System
echo "[loop] wineboot"; timeout 120 FEXBash -c "/opt/wine-stable/bin/wine wineboot -u" >/tmp/wb.log 2>&1; echo "[loop] wineboot rc=$?"
LINKED=0
for try in $(seq 1 8); do
  echo "[loop] === attempt $try ($(date +%T)) pids=$(cat /sys/fs/cgroup/pids.current) ==="
  L=/game/System/boot_$try.log; rm -f "$L"
  setsid bash -c "cd /game/System && exec FEXBash -c \"cd /game/System && exec /opt/wine-stable/bin/wine DeusEx.exe -log=boot_$try.log -nosound\"" >/tmp/dxl_$try.log 2>&1 &
  for s in $(seq 1 14); do
    listening && { echo "[loop] LINK BOUND attempt $try t=$((s*3))s"; LINKED=1; break; }
    sleep 3
  done
  [ $LINKED = 1 ] && break
  ll=$(wc -l < "$L" 2>/dev/null || echo 0)
  echo "[loop] attempt $try no-link, loglines=$ll"
  /opt/wine-stable/bin/wineserver -k9 2>/dev/null; pkill -9 -f DeusEx.exe 2>/dev/null; sleep 3
done
echo "[loop] DONE LINKED=$LINKED"
listening && netstat -ltn | grep 7777
