#!/bin/bash
set -u
XIP="${XIP:-172.20.0.2}"
export WINEARCH=win32 WINEPREFIX=/wineprefix32c WINELOADER=/opt/wine-stable/bin/wine
export WINEDLLPATH=/opt/wine-stable/lib/wine/i386-windows XDG_RUNTIME_DIR=/run/user/0
mkdir -p /run/user/0; chmod 1777 /run/user/0
export DISPLAY=$XIP:99 WINEESYNC=1 WINEFSYNC=1
export WINEDLLOVERRIDES="winealsa.drv=d;mscoree=d;mshtml=d"
export WINEDEBUG=+file
W=/opt/wine-stable/bin/wine
cd /game/System
python3 /root/mkini.py DeusEx.ini stock 4 >/dev/null
$W wineserver -k 2>/dev/null; sleep 1
rm -f boot.log; : > boot.log
FL=/tmp/file.log; : > "$FL"
setsid bash -c "cd /game/System && exec FEXBash -c \"cd /game/System && exec $W DeusEx.exe -log=boot.log -nosound\"" >"$FL" 2>&1 &
sleep 25
$W wineserver -k9 2>/dev/null; FEXBash -c "pkill -9 -f DeusEx" 2>/dev/null
echo "=== boot.log lines=$(wc -l < boot.log) ==="
echo "=== file accesses mentioning game root / cd-ish, last 60 ==="
grep -aiE "z:|\\\\game\\\\|/game/|deusex|autorun|\.dx|\.uax|\.umx" "$FL" | grep -aivE "prefetch|windows\\\\|system32|wineprefix|drive_c\\\\windows" | tail -60
echo "=== file.log total lines=$(wc -l < "$FL") ==="
