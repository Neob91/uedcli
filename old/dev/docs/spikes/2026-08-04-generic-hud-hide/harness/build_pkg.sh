#!/usr/bin/env bash
# build_pkg.sh — compile the engine-only UedPreview.u (spike variant) with the REGULAR
# UED22 v469 UCC inside a dx-lum-uned container (board finding 2026-08-03: an engine-only
# UedPreview.u built by UED22 UCC LOADS+RUNS in retail v68 DeusEx.exe). No hUCC, no DeusEx.u.
#
# Recipe: UED22 is a UT-based SDK; its working make ini is unrealtournament.ini. UCC resolves
# a package's sources at ../<Package>/Classes/*.uc relative to the System dir (/opt/UED22),
# i.e. a SIBLING dir. So: sources -> /opt/UedPreview/Classes, EditPackages=UedPreview appended
# after IpDrv (deps first), `ucc make` from /opt/UED22, output /opt/UED22/UedPreview.u.
# Output: harness/UedPreview.u (v69, engine-only). That all our stock-field/method references
# compile against Engine.u is itself the schema proof (myHUD/Weapon/bBehindView/FlashScale/...).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
C=uedpreview-spike-build
docker rm -f "$C" >/dev/null 2>&1 || true
docker run -d --name "$C" -e LAUNCH_UED=0 --entrypoint bash dx-lum-uned -lc 'sleep 3600' >/dev/null
for _ in $(seq 1 30); do docker exec "$C" wine --version >/dev/null 2>&1 && break; sleep 1; done

docker exec "$C" bash -lc 'rm -rf /opt/UedPreview; mkdir -p /opt/UedPreview/Classes'
docker cp "$HERE/uscript/UedPreview/Classes/." "$C:/opt/UedPreview/Classes/" >/dev/null

docker exec "$C" bash -lc '
set -e
cd /opt/UED22
cp unrealtournament.ini make.ini
python3 - <<PY
p="make.ini"; raw=open(p,"rb").read().decode("latin-1"); out=[]
for l in raw.split("\r\n"):
    out.append(l)
    if l.strip()=="EditPackages=IpDrv": out.append("EditPackages=UedPreview")
open(p,"wb").write(("\r\n".join(out)).encode("latin-1"))
PY
rm -f UedPreview.u
export WINEDLLOVERRIDES="winealsa.drv=d"
timeout 60 wineboot -u >/dev/null 2>&1 || true
wine ./UCC.exe make -ini=make.ini 2>&1 | tr -d "\000" | grep -iE "UedPreview|error|Success|Failure|Compiling |warning"
test -e UedPreview.u || { echo "COMPILE FAILED (no UedPreview.u)"; exit 4; }
echo "OK UedPreview.u ($(stat -c %s UedPreview.u) bytes)"
'
docker cp "$C:/opt/UED22/UedPreview.u" "$HERE/UedPreview.u" >/dev/null
docker rm -f "$C" >/dev/null
echo "== wrote $HERE/UedPreview.u =="
ls -la "$HERE/UedPreview.u"
