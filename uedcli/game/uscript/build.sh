#!/usr/bin/env bash
# build.sh — compile the engine-only UedPreview package with the base image's own
# regular UED22 UCC (v469). No game System, no content mounts, no DeusEx.u:
# UedPreview names only stock Core/Engine/IpDrv, all present in /opt/UED22 (spike
# 2026-08-04-generic-hud-hide §1). The resulting v69 package LOADS AND RUNS in retail
# v68 DeusEx.exe (board engine-only-uedpreview-via-regular-ucc-renders).
#
# Recipe (proven, from that spike's build_pkg.sh): UED22 is a UT-based SDK; its working
# make ini is unrealtournament.ini. UCC resolves a package's sources at ../<Package>/
# Classes/*.uc relative to the System dir (/opt/UED22) — a SIBLING dir. So: stage the
# sources at /opt/UedPreview/Classes, append EditPackages=UedPreview after IpDrv (deps
# first), `ucc make` from /opt/UED22, output /opt/UED22/UedPreview.u.
# Output: /work/build/System/UedPreview.u
set -e
SRC="${1:-/work/uscript}"
U=/opt/UED22
B=/work/build

rm -rf "$B" /opt/UedPreview
mkdir -p "$B/System" /opt/UedPreview/Classes
cp "$SRC"/UedPreview/Classes/*.uc /opt/UedPreview/Classes/

cd "$U"
cp unrealtournament.ini make.ini
python3 - <<'PY'
p = "make.ini"
raw = open(p, "rb").read().decode("latin-1")   # CRLF ini — keep \r\n (wine wedges on LF; quirks.md)
out = []
for l in raw.split("\r\n"):
    out.append(l)
    if l.strip() == "EditPackages=IpDrv":
        out.append("EditPackages=UedPreview")
open(p, "wb").write(("\r\n".join(out)).encode("latin-1"))
PY

rm -f UedPreview.u
export WINEDLLOVERRIDES="winealsa.drv=d"
timeout 60 wineboot -u >/dev/null 2>&1 || true
wine ./UCC.exe make -ini=make.ini 2>&1 | tr -d '\000' | tail -8
test -e "$U/UedPreview.u" || { echo "compile FAILED (no UedPreview.u)"; exit 4; }
cp "$U/UedPreview.u" "$B/System/UedPreview.u"
echo "compiled: UedPreview.u ($(stat -c %s "$B/System/UedPreview.u") bytes)"
