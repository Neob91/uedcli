#!/bin/sh
export WINEDLLPATH=/usr/lib/x86_64-linux-gnu/wine/x86_64-windows:/usr/lib/i386-linux-gnu/wine/i386-windows
export XDG_RUNTIME_DIR=/run/user/0
mkdir -p /run/user/0; chmod 1777 /run/user/0
export WINEPREFIX=/wineprefix
export WINEDEBUG=err+all,warn+server,fixme-all
rm -f /tmp/wboot_done
timeout 40 wine wineboot -u > /tmp/wboot_out.txt 2>&1
echo "rc=$?" > /tmp/wboot_done
