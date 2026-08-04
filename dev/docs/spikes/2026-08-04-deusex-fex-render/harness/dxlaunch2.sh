#!/bin/sh
export WINEDLLPATH=/usr/lib/x86_64-linux-gnu/wine/x86_64-windows:/usr/lib/i386-linux-gnu/wine/i386-windows
export XDG_RUNTIME_DIR=/run/user/0
mkdir -p /run/user/0; chmod 1777 /run/user/0
export WINEPREFIX=/wineprefix
export DISPLAY=172.20.0.3:99
export WINEDEBUG=err+all,fixme-all
export WINEDLLOVERRIDES="mscoree,mshtml,winemenubuilder,plugplay=;"
cd /game/System || exit 9
rm -f /game/System/DeusEx.log
wine DeusEx.exe -log -nosound > /tmp/dx2_stdout.txt 2>&1 &
echo $! > /tmp/dx2_pid
