#!/usr/bin/env bash
export BOX=/root/box64/build/box64 WINELOADER=/usr/lib/wine/wine WINESERVER=/usr/lib/wine/wineserver
export WINEDEBUG=-all WINEARCH=win32 WINEPREFIX=/root/wp32 BOX64_LOG=0
pgrep -f Xvfb >/dev/null || { Xvfb :99 -screen 0 1024x768x24 >/tmp/xvfb.log 2>&1 & sleep 2; }
: > /tmp/reliab.result
for trial in 1 2 3; do
  pkill -9 -f DeusEx.exe 2>/dev/null; DISPLAY=:99 $BOX $WINESERVER -k 2>/dev/null; sleep 2
  cd /root/gameroot/System; : > DeusEx.log
  DISPLAY=:99 $BOX $WINELOADER DeusEx.exe -log -nosound >/tmp/dx$trial.out 2>/tmp/dx$trial.err &
  gp=$!
  maxlog=0; bound=0; alive=1
  for i in $(seq 1 20); do
    sleep 4
    L=$(wc -l < DeusEx.log 2>/dev/null||echo 0); [ "$L" -gt "$maxlog" ] && maxlog=$L
    if netstat -ltn 2>/dev/null|grep -q ":7777 "; then bound=1; break; fi
    if ! pgrep -f "DeusEx.exe -log" >/dev/null 2>&1; then alive=0; break; fi
  done
  echo "trial=$trial maxlog=$maxlog bound=$bound proc_alive_at_end=$alive t~$((i*4))s" | tee -a /tmp/reliab.result
done
echo "RELIAB-DONE" | tee -a /tmp/reliab.result
