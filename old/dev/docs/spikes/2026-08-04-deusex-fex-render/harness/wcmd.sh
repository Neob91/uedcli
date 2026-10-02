#!/bin/sh
export WINEDLLPATH=/usr/lib/x86_64-linux-gnu/wine/x86_64-windows:/usr/lib/i386-linux-gnu/wine/i386-windows
export XDG_RUNTIME_DIR=/run/user/0
mkdir -p /run/user/0; chmod 1777 /run/user/0
export WINEPREFIX=/wineprefix
export WINEDEBUG=-all
export WINEDLLOVERRIDES="mscoree,mshtml,winemenubuilder=;"
rm -f /tmp/wcmd_done
wine cmd /c "echo BOX64_WINE_IPC_OK" > /tmp/wcmd_out.txt 2>/tmp/wcmd_err.txt
echo "rc=$?" > /tmp/wcmd_done
