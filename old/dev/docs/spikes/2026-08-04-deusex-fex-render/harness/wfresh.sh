#!/bin/sh
export WINEDLLPATH=/usr/lib/x86_64-linux-gnu/wine/x86_64-windows:/usr/lib/i386-linux-gnu/wine/i386-windows
export XDG_RUNTIME_DIR=/run/user/0
mkdir -p /run/user/0; chmod 1777 /run/user/0
export WINEPREFIX=/tmp/wpfresh
rm -rf /tmp/wpfresh
export WINEDEBUG=err+all,fixme-all
export WINEDLLOVERRIDES="mscoree,mshtml,winemenubuilder=;"
rm -f /tmp/wfresh_done
timeout 45 wine wineboot -i > /tmp/wfresh_out.txt 2>&1
echo "rc=$?" > /tmp/wfresh_done
