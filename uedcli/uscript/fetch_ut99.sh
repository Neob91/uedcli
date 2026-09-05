#!/usr/bin/env bash
# Fetch the stock UnrealTournament GOTY (UT99) build substrate from archive.org into
# uned/UT99/System/. This is the self-consistent toolchain the UT99 corpus compiles against:
# UT99's own UCC.exe + DLLs + .u packages (NOT the /opt/UED22 substrate, a different engine build).
#
# Reproducible + gitignored (uned/UT99/ is in .gitignore) — ~50MB, never committed.
# Idempotent: an already-present, valid file is skipped. Run from the repo root.
set -euo pipefail

BASE="https://archive.org/download/ut-goty/UT_GOTY_CD1.iso/System%2F"
DEST="uned/UT99/System"
mkdir -p "$DEST"

# .u start with the Unreal package magic C1 83 2A 9E (little-endian 0x9E2A83C1).
U_MAGIC=$'\xc1\x83\x2a\x9e'

fetch() {  # <filename> <min_bytes> [magic]
  local name="$1" min="$2" magic="${3:-}"
  local out="$DEST/$name"
  if [[ -f "$out" && $(wc -c <"$out") -ge "$min" ]]; then
    echo "  skip $name ($(wc -c <"$out") bytes)"; return
  fi
  echo "  get  $name"
  timeout 300 curl -fsSL "${BASE}${name}" -o "$out"
  local sz; sz=$(wc -c <"$out")
  if [[ "$sz" -lt "$min" ]]; then
    echo "FAIL $name: only $sz bytes (<$min)"; rm -f "$out"; exit 1
  fi
  if [[ -n "$magic" ]]; then
    local head; head=$(head -c 4 "$out")
    if [[ "$head" != "$magic" ]]; then
      echo "FAIL $name: bad magic $(head -c 4 "$out" | od -An -tx1)"; rm -f "$out"; exit 1
    fi
  fi
}

echo "== script packages (.u) =="
for p in Core Engine Editor Fire IpDrv IpServer UWeb UWindow UBrowser UMenu UTMenu \
         UTBrowser UnrealShare UnrealI BotPack relics relicsbindings multimesh \
         epiccustommodels de UTServerAdmin; do
  fetch "$p.u" 128 "$U_MAGIC"   # some stock .u are tiny (relicsbindings ≈ 582B); magic is the real check
done

echo "== DLLs =="
for d in Core Engine Editor Render WinDrv Window Fire Galaxy IpDrv UWeb SoftDrv \
         D3DDrv OpenGlDrv SGLDrv MeTaLDrv GlideDrv MSVCRT; do
  fetch "$d.dll" 1024
done

echo "== UCC.exe =="
fetch "UCC.exe" 1024

# .int (localization) and inis are best-effort: not needed to compile, and some are absent
# on the CD or served empty. A missing one is not fatal.
try_fetch() {  # <filename> <min_bytes>
  local name="$1" min="$2" out="$DEST/$1"
  if [[ -f "$out" && $(wc -c <"$out") -ge "$min" ]]; then echo "  skip $name"; return; fi
  if timeout 120 curl -fsSL "${BASE}${name}" -o "$out" 2>/dev/null && \
     [[ $(wc -c <"$out") -ge "$min" ]]; then echo "  got  $name"
  else rm -f "$out"; echo "  absent $name"; fi
}

echo "== localization (.int, best-effort) =="
for i in Core Engine Editor Botpack UnrealShare UnrealI UWindow UBrowser UMenu \
         UTMenu IpDrv UWeb Startup Manifest UnrealTournament Setup; do
  try_fetch "$i.int" 16
done

echo "== inis (best-effort; may be absent on CD) =="
for ini in UnrealTournament.ini Default.ini; do
  try_fetch "$ini" 16
done

echo "Done. Substrate at $DEST ($(du -sh "$DEST" | cut -f1))."
