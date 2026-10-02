#!/bin/sh
export WINEDLLPATH=/usr/lib/x86_64-linux-gnu/wine/x86_64-windows:/usr/lib/i386-linux-gnu/wine/i386-windows
export XDG_RUNTIME_DIR=/run/user/0
mkdir -p /run/user/0; chmod 1777 /run/user/0
export WINEPREFIX=/wineprefix
export DISPLAY=172.20.0.3:99
export WINEDEBUG=-all
export WINEDLLOVERRIDES="mscoree,mshtml,winemenubuilder=;"
# start persistent wineserver, do NOT run wineboot
wineserver -p -w >/tmp/wsrv.log 2>&1 &
sleep 3
echo "wineserver started, procs now:"  >/tmp/wsrv_stage.txt
rm -f /tmp/wsrv_done
timeout 40 wine cmd /c "echo MINIMAL_IPC_OK" > /tmp/wsrv_out.txt 2>/tmp/wsrv_err.txt
echo "rc=$?" > /tmp/wsrv_done
