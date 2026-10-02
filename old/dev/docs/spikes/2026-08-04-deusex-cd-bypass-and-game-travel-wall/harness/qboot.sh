#!/bin/bash
# qboot.sh — boot DeusEx.exe under dx-lum-uned (qemu amd64 wine-8), dx engine, its own Xvfb :99.
set -u
export WINEPREFIX=/wineprefix WINEARCH=win32 WINEDEBUG=-all DISPLAY=:99
export WINEDLLOVERRIDES="winealsa.drv=d;mscoree=;mshtml="
WINDOW_S="${WINDOW_S:-300}"
listening(){ netstat -ltn 2>/dev/null | grep -q ':7777 '; }
cd /game/System
python3 /root/mkini.py DeusEx.ini dx 64
wineserver -k 2>/dev/null; sleep 1
rm -f Running.ini boot.log; : > boot.log
echo "[q] launch DeusEx.exe (qemu/wine8)"
setsid bash -c "cd /game/System && exec wine DeusEx.exe -log=boot.log -nosound" >/tmp/dxl.log 2>&1 &
t=0; PEAK=0
while [ "$t" -lt "$WINDOW_S" ]; do
  MC=$(cat /sys/fs/cgroup/memory.current 2>/dev/null||echo 0); [ "$MC" -gt "$PEAK" ] && PEAK=$MC
  LL=$(wc -l < boot.log 2>/dev/null||echo 0)
  echo "[t=${t}s] mem=$((MC/1024/1024))MiB peak=$((PEAK/1024/1024))MiB loglines=$LL"
  listening && { echo "=== LINK BOUND t=${t}s ==="; break; }
  sleep 8; t=$((t+8))
done
listening && echo "[q] LINKED" || echo "[q] NO LINK"
echo "[q] --- boot.log tail ---"; grep -avE "FireTexture|LodMesh|Draw|UTexture::" boot.log 2>/dev/null | tr -d '\000' | tail -15
