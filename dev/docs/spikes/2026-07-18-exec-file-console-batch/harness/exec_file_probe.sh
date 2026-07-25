#!/usr/bin/env bash
# Re-run the EXEC-file spike probes against a live uned editor container.
# Usage: exec_file_probe.sh [container]   (default: boots+tears down uned-spike-execfile)
# Evidence for ../results.md — each probe prints PASS/FAIL; exits non-zero on any FAIL.
set -u
C="${1:-}"
OWN=0
HERE="$(cd "$(dirname "$0")" && pwd)"
UNED_DIR="$(cd "$HERE/../../../../../uned" && pwd)"   # Tools/uedctl/uned

if [ -z "$C" ]; then
  C=uned-spike-execfile
  OWN=1
  (cd "$UNED_DIR" && docker compose run -d --name "$C" -v "uned-wp-$C:/wineprefix" uned) >/dev/null
  for i in $(seq 1 60); do
    out=$(docker exec "$C" python3 /opt/uned/wine_ctl.py status 2>&1 || true)
    echo "$out" | grep -qE 'alive=True' && echo "$out" | grep -qE 'window=[0-9]' && break
    sleep 3
  done
fi

fail=0
say() { echo "== $*"; }
chk() { # chk <name> <shell test in container>
  if docker exec "$C" sh -c "$2" >/dev/null 2>&1; then echo "PASS: $1"; else echo "FAIL: $1"; fail=1; fi
}
ued() { docker exec "$C" python3 /opt/uned/wine_ctl.py exec "$1"; }

say "1. EXEC absolute path runs a 3-command script"
docker exec "$C" sh -c 'printf "MAP EXPORT FILE=Z:\\\\work\\\\p1a.t3d\nMAP EXPORT FILE=Z:\\\\work\\\\p1b.t3d\nMAP EXPORT FILE=Z:\\\\work\\\\p1c.t3d\n" > /work/p1.txt'
ued 'EXEC Z:\work\p1.txt'; sleep 3
chk "all 3 exports written" 'test -s /work/p1a.t3d -a -s /work/p1b.t3d -a -s /work/p1c.t3d'

say "2. relative filename resolves against /opt/UED22 (System), not /work"
docker exec "$C" sh -c 'printf "MAP EXPORT FILE=Z:\\\\work\\\\p2sys.t3d\n" > /opt/UED22/p2rel.txt; printf "MAP EXPORT FILE=Z:\\\\work\\\\p2work.t3d\n" > /work/p2rel.txt'
ued 'EXEC p2rel.txt'; sleep 3
chk "System-dir copy ran, /work copy did not" 'test -s /work/p2sys.t3d -a ! -e /work/p2work.t3d'

say "3. errors (bogus verb, failing OBJ LOAD) do not abort the script"
docker exec "$C" sh -c 'printf "MAP EXPORT FILE=Z:\\\\work\\\\p3a.t3d\nTOTALLYBOGUSVERB FOO=1\nOBJ LOAD FILE=Z:\\\\work\\\\missing.utx\nMAP EXPORT FILE=Z:\\\\work\\\\p3b.t3d\n" > /work/p3.txt'
ued 'EXEC Z:\work\p3.txt'; sleep 3
chk "export after the errors still ran" 'test -s /work/p3b.t3d'

say "4. GC xmessage dialog does not stall script execution (MAP NEW mid-script)"
docker exec "$C" sh -c 'printf "MAP NEW\nMAP EXPORT FILE=Z:\\\\work\\\\p4a.t3d\nBRUSH RESET\nMAP EXPORT FILE=Z:\\\\work\\\\p4b.t3d\n" > /work/p4.txt'
ued 'EXEC Z:\work\p4.txt'; sleep 5
chk "post-MAP NEW commands ran" 'test -s /work/p4a.t3d -a -s /work/p4b.t3d'
# dismiss the dialog it popped, so later probes type cleanly
docker exec "$C" sh -c 'wid=$(DISPLAY=:99 xdotool search --onlyvisible --name xmessage | head -1); [ -n "$wid" ] && DISPLAY=:99 xdotool windowactivate --sync "$wid" && DISPLAY=:99 xdotool key Return' >/dev/null 2>&1
sleep 1

say "5. CRLF script works"
docker exec "$C" sh -c 'printf "MAP EXPORT FILE=Z:\\\\work\\\\p5.t3d\r\n" > /work/p5.txt'
ued 'EXEC Z:\work\p5.txt'; sleep 3
chk "CRLF-file command ran" 'test -s /work/p5.t3d'

say "6. nested EXEC works and the outer script continues"
docker exec "$C" sh -c 'printf "EXEC Z:\\\\work\\\\p6i.txt\nMAP EXPORT FILE=Z:\\\\work\\\\p6outer.t3d\n" > /work/p6.txt; printf "MAP EXPORT FILE=Z:\\\\work\\\\p6inner.t3d\n" > /work/p6i.txt'
ued 'EXEC Z:\work\p6.txt'; sleep 3
chk "inner + outer both ran" 'test -s /work/p6inner.t3d -a -s /work/p6outer.t3d'

if [ "$OWN" = 1 ]; then
  docker rm -f "$C" >/dev/null 2>&1
  docker volume rm "uned-wp-$C" >/dev/null 2>&1
fi
exit $fail
