#!/usr/bin/env bash
# Fetch the ORIGINAL Ion Storm Deus Ex GOTY (v1112fm / build 1100) build substrate into
# uned/DXORIG/System/. This is the self-consistent toolchain the conversation corpus compiles
# against: the game's own DLLs + .u packages, plus the SDK's own UCC.exe (the console compiler,
# absent from every retail disc — it shipped only in the SDK).
#
# Why this exact mix, and NOT an OldUnreal build: OldUnreal's rebuilt Editor.dll dropped the
# `#exec CONVERSATION IMPORT` handler, so it silently no-ops. The original Ion Storm binaries below
# DO import conversations (verified: `#exec CONVERSATION IMPORT` emits Conversation/ConEvent/…
# objects into a `<Pkg>Text.u` sibling package). See reference_dxorig.py.
#
# Two sources (no single archive has both loose):
#   1. GOTY install (archive.org) — every .u + DLL incl. Editor.u/Editor.dll/ConSys/Extension.
#      Retail CDs pack these inside SystemFiles.exe; this is a plain installed folder in a .rar.
#   2. Deus Ex SDK v1112fm (WinZip self-extractor = a zip) — the only source of the DX-native
#      UCC.exe (+ UnrealEd.exe). Its Core.dll differs from GOTY's but is ABI-compatible; the SDK
#      is meant to be dropped onto the installed game, so we keep GOTY's DLLs and add only UCC.exe.
#
# Reproducible + gitignored (uned/DXORIG/ is in .gitignore) — never committed. Run from repo root.
# Idempotent: an already-present, valid file is skipped. Needs curl + python3 (+ tar for unrar).
set -euo pipefail

DEST="uned/DXORIG/System"
TMP="_scratch/dl"
mkdir -p "$DEST" "$TMP"

RAR_URL="https://archive.org/download/deusexgameoftheyearedition_ionstorm_shadowjoe/Deus%20Ex%20Game%20Of%20The%20Year%20Edition.rar"
RAR_INNER="Deus Ex Game Of The Year Edition/System"
SDK_URL="http://www.stevetack.com/archive/TacksDeusExLab/archived-sites/Deus%20Ex%20SDK%20v1112fm/DeusExSDK1112f.exe"
UNRAR_URL="https://www.rarlab.com/rar/rarlinux-x64-712.tar.gz"

U_MAGIC=$'\xc1\x83\x2a\x9e'   # Unreal package magic (0x9E2A83C1 LE) — the real check for a .u

have() { [[ -f "$DEST/$1" && $(wc -c <"$DEST/$1") -ge "$2" ]]; }

# --- 1. GOTY System (Core.dll + every game .u/DLL, incl. Editor.u/ConSys/Extension) via unrar ---
if have Core.u 1000 && have Editor.u 1000 && have ConSys.u 1000 && have DeusEx.dll 100000; then
  echo "  skip GOTY System (already present)"
else
  echo "== GOTY System (archive.org shadowjoe .rar) =="
  if [[ ! -x "$TMP/unrar" ]]; then
    echo "  get unrar"; timeout 180 curl -fsSL "$UNRAR_URL" -o "$TMP/rar.tgz"
    tar xzf "$TMP/rar.tgz" -C "$TMP" rar/unrar && mv "$TMP/rar/unrar" "$TMP/unrar" && rmdir "$TMP/rar" 2>/dev/null || true
  fi
  if [[ ! -f "$TMP/goty.rar" || $(wc -c <"$TMP/goty.rar") -lt 300000000 ]]; then
    echo "  get GOTY .rar (~306 MB)"; timeout 900 curl -fsSL "$RAR_URL" -o "$TMP/goty.rar"
  fi
  echo "  extract System/*"
  "$TMP/unrar" e -o+ "$TMP/goty.rar" "$RAR_INNER/*" "$DEST/" >/dev/null
fi

# --- 2. SDK v1112fm UCC.exe (+ UnrealEd) — WinZip SFX = a zip, read with python3 ---
if have UCC.exe 100000; then
  echo "  skip SDK UCC.exe (already present)"
else
  echo "== SDK v1112fm (stevetack mirror, WinZip SFX) =="
  if [[ ! -f "$TMP/DeusExSDK1112f.exe" || $(wc -c <"$TMP/DeusExSDK1112f.exe") -lt 6000000 ]]; then
    echo "  get DeusExSDK1112f.exe (~6.5 MB)"
    timeout 180 curl -fsSL "$SDK_URL" -o "$TMP/DeusExSDK1112f.exe"
  fi
  echo "  extract System/UCC.exe, UCC.lib, UnrealEd.exe, UnrealEd.int"
  python3 - "$TMP/DeusExSDK1112f.exe" "$DEST" <<'PY'
import sys, zipfile, os
sfx, dest = sys.argv[1], sys.argv[2]
z = zipfile.ZipFile(sfx)                       # zipfile scans past the SFX stub to the central dir
for m in ("UCC.exe", "UCC.lib", "UnrealEd.exe", "UnrealEd.int"):
    data = z.read(f"ReleaseSDK1112f/System/{m}")
    open(os.path.join(dest, m), "wb").write(data)
    print(f"    {m}: {len(data)} bytes")
PY
fi

# --- verify the substrate is complete + valid ---
fail=0
for u in Core Engine Editor Fire IpDrv UWindow UBrowser Extension DeusExUI ConSys DeusExConversations; do
  if ! have "$u.u" 128; then echo "MISSING $u.u"; fail=1
  elif [[ "$(head -c4 "$DEST/$u.u")" != "$U_MAGIC" ]]; then echo "BAD MAGIC $u.u"; fail=1; fi
done
for d in Core Engine Editor Window WinDrv Render Fire Galaxy IpDrv ConSys Extension DeusEx DeusExText MSVCRT UCC.exe; do
  f="$d"; [[ "$d" == *.exe ]] || f="$d.dll"
  [[ -f "$DEST/$f" ]] || { echo "MISSING $f"; fail=1; }
done
[[ $fail -eq 0 ]] || { echo "FAIL: substrate incomplete at $DEST"; exit 1; }
echo "Done. Substrate at $DEST ($(du -sh "$DEST" | cut -f1)); UCC.exe = $(wc -c <"$DEST/UCC.exe") bytes."
