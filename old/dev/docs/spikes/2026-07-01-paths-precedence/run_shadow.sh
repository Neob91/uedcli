#!/usr/bin/env bash
# Spike harness H2: an OVERRIDE dir prepended to `[Core.System] Paths` shadows a
# package that ALSO exists in the baked substrate.
#
# `CoreTexMetal` is a real substrate package (175 metal textures, resolved from
# /deusex/Textures). We provide an override `CoreTexMetal.utx` that is actually
# BobPage content (3 distinctive BP_FX textures), placed in a dir prepended to
# Paths AHEAD of the substrate entries. If H2 holds, by-name `CoreTexMetal`
# resolves to the 3 BP_FX override textures, NOT the 175 substrate ones; the
# control (override removed) must revert to the 175.
#
# Same method/caveats as run_precedence.sh: UCC (fresh ini read) is the by-name
# probe; the ini edit + UCC run happen in ONE atomic exec so the running editor
# can't clobber the Paths edit. The override .utx is `docker cp`'d into /work
# (it is not a compose mount).
# NEVER touches the standing dx-lum-uned. Tears down container + volume on exit.
set -euo pipefail

CNAME="${1:?container name}"
VOL="wp-${CNAME}"
COMPOSE_DIR="/home/human/src/dx_lum/Tools/uedcli/uned"
SCRATCH="/home/human/src/dx_lum/_scratch/paths-precedence"
INI="/opt/UED22/unrealtournament.ini"

cleanup() { docker rm -f "$CNAME" >/dev/null 2>&1 || true; docker volume rm "$VOL" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "== spin up ephemeral editor $CNAME =="
cd "$COMPOSE_DIR"
docker compose run -d --name "$CNAME" -v "$VOL":/wineprefix uned >/dev/null
sleep 6

# Stage the override CoreTexMetal.utx (= BobPage content) into /work/override.
docker exec "$CNAME" sh -c 'mkdir -p /work/override'
docker cp "$SCRATCH/override/CoreTexMetal.utx" "$CNAME":/work/override/CoreTexMetal.utx

echo; echo "==== baseline: substrate CoreTexMetal (no override) ===="
docker exec "$CNAME" sh -c "
  rm -rf /work/ctm; cd /opt/UED22 && wine UCC.exe batchexport CoreTexMetal Texture pcx 'Z:\\work\\ctm' >/dev/null 2>&1
  echo 'texture count: '\$(ls /work/ctm 2>/dev/null | wc -l)
  echo 'has BP_FX? '\$(ls /work/ctm 2>/dev/null | grep -ci '^BP_FX')
"

echo; echo "==== H2: override prepended AHEAD of substrate ===="
docker exec "$CNAME" sh -c "
  sed -i '/^\\[Core.System\\]/a Paths=/work/override/*.utx' $INI
  grep -n 'Paths=.*\\(override\\|Textures\\)' $INI
  rm -rf /work/ctm2; cd /opt/UED22 && wine UCC.exe batchexport CoreTexMetal Texture pcx 'Z:\\work\\ctm2' >/dev/null 2>&1
  echo '--- resolved ---'
  ls /work/ctm2 2>/dev/null
  echo 'texture count: '\$(ls /work/ctm2 2>/dev/null | wc -l)
"
if docker exec "$CNAME" sh -c "ls /work/ctm2 2>/dev/null | grep -qi '^BP_FX'"; then
  echo "VERDICT: OVERRIDE WON (shadowed substrate) — H2 HOLDS"
else
  echo "VERDICT: substrate still won — H2 FAILS"
fi

echo; echo "==== control: remove override, must revert to substrate ===="
docker exec "$CNAME" sh -c "
  sed -i '\\#Paths=/work/override#d' $INI
  rm -rf /work/ctm3; cd /opt/UED22 && wine UCC.exe batchexport CoreTexMetal Texture pcx 'Z:\\work\\ctm3' >/dev/null 2>&1
  echo 'texture count: '\$(ls /work/ctm3 2>/dev/null | wc -l)
  echo 'has BP_FX? '\$(ls /work/ctm3 2>/dev/null | grep -ci '^BP_FX')
"
