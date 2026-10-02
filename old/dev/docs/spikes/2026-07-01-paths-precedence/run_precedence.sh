#!/usr/bin/env bash
# Spike harness: verify the `[Core.System] Paths` precedence model that the
# global-CLI package-overlay design depends on:
#   H1 first-match-wins  — the FIRST matching dir on Paths supplies a package.
#   H2 override shadows   — a dir prepended ahead of the baked substrate shadows
#                           a substrate package of the same name.
#
# METHOD (see findings.md for the full reasoning). Two same-named packages made
# trivially distinguishable by their texture SETS:
#   A = BobPage.utx       -> BP_FX_01/02/03, Palette5/7           (6 exports)
#   B = InfoPortraits.utx -> AlexJacobson, AnnaNavarre, ...       (42 exports)
# each copied to a dir as `Foo.utx`, put on `[Core.System] Paths` in a chosen
# order, and resolved BY NAME.
#
# TWO KEY FINDINGS that shaped the method (findings.md):
#  1. The RUNNING GUI editor process REWRITES `unrealtournament.ini` from its
#     boot-time in-memory config, CLOBBERING any `Paths=` line you `sed` in after
#     launch. So a live editor never sees a mid-session Paths edit — and a slow
#     step between the edit and the read lets the editor wipe it. Do the ini edit
#     and the read in ONE atomic `docker exec` so the editor can't race it.
#  2. `UCC.exe` (a separate wine process) reads the ini FRESH on every invocation
#     and performs the REAL by-name Paths glob-search — so `UCC batchexport <pkg>`
#     is the correct probe for the by-name resolution the precedence model is
#     about. (Only DIRECTORY-GLOB Paths entries `<dir>/*.utx` are searched by
#     name; `OBJ LOAD FILE=<bare-name>` / `OBJ LOAD PACKAGE=<name>` in the editor
#     do NOT do a Paths search at all.)
#
# Usage: run_precedence.sh <container-name>
#   Runs BOTH orderings (H1) in one editor and prints each verdict.
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
docker compose run -d --name "$CNAME" -v "$VOL":/wineprefix \
  -v "$SCRATCH/dirA":/precedence/dirA:ro \
  -v "$SCRATCH/dirB":/precedence/dirB:ro \
  uned >/dev/null
# Bounded wait: UCC works even before the GUI is fully up; a short sleep suffices.
sleep 6

# One ordering = one atomic exec: strip prior precedence entries, prepend SECOND
# then FIRST (so FIRST lands first), run UCC by-name, list the resolved textures.
run_order() {
  local first="$1" second="$2"
  docker exec "$CNAME" sh -c "
    sed -i '\\#Paths=/precedence/dir#d' $INI
    sed -i '/^\\[Core.System\\]/a Paths=$second/*.utx' $INI
    sed -i '/^\\[Core.System\\]/a Paths=$first/*.utx' $INI
    grep -n 'Paths=/precedence' $INI
    rm -rf /work/foo_out
    cd /opt/UED22 && wine UCC.exe batchexport Foo Texture pcx 'Z:\\work\\foo_out' >/dev/null 2>&1
    echo '--- resolved textures ---'
    ls /work/foo_out 2>/dev/null | sed 's/[.]pcx\$//'
  "
}

verdict() {
  if docker exec "$CNAME" sh -c "ls /work/foo_out 2>/dev/null | grep -qi '^BP_FX'"; then
    echo "VERDICT: RESOLVED = A (BobPage / dirA)"
  elif docker exec "$CNAME" sh -c "ls /work/foo_out 2>/dev/null | grep -qiE '^(AlexJacobson|AnnaNavarre|GuntherHermann|Icarus)'"; then
    echo "VERDICT: RESOLVED = B (InfoPortraits / dirB)"
  else
    echo "VERDICT: RESOLVED = UNKNOWN"
  fi
}

echo; echo "==== H1a: dirA first (expect A) ===="
run_order /precedence/dirA /precedence/dirB
verdict
echo; echo "==== H1b: dirB first (expect B) ===="
run_order /precedence/dirB /precedence/dirA
verdict
