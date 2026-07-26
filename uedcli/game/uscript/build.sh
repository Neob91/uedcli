#!/usr/bin/env bash
# build.sh — compile the UedPreview packages (v68) INSIDE a mounted builder container.
# Expects: /work/uscript (these sources), /work/edit (the user-supplied v469 UCC toolchain,
# 9 files — see game/inputs/README.md), /gsys (the game's System dir, read-only), /gc0..N
# (the remaining composed content dirs, read-only — DeusEx.u's import closure needs
# Ambient.uax/Effects.utx/... resolvable at compile).
# Output: /work/build/System/{UedPreview.u, UedPreviewDX.u}
set -e
SRC="${1:-/work/uscript}"
B=/work/build; E=/work/edit
rm -rf "$B"; mkdir -p "$B/System" "$B/UedPreview/Classes" "$B/UedPreviewDX/Classes"
cp -r /gsys/. "$B/System/"
cp "$E/Editor.dll" "$E/Editor.u" "$B/System/"; cp "$E/Editor.int" "$B/System/" 2>/dev/null || true
cp "$E/Window.dll" "$E/RenderExt.dll" "$E/RenderExt.int" "$E/msvcr120.dll" "$E/CoreI.dll" "$B/System/"
cp "$E/hUCC.exe" "$B/System/UCC.exe"
cp "$SRC"/UedPreview/Classes/*.uc "$B/UedPreview/Classes/"
cp "$SRC"/dxdriver/Classes/*.uc   "$B/UedPreviewDX/Classes/"

# EditPackages -> ours only, on top of Core/Engine/IpDrv; and append Paths entries for
# every mounted content dir so DeusEx.u's content import closure resolves at compile.
python3 - <<'PY'
import glob
p = "/work/build/System/DeusEx.ini"
# CRLF ini — keep \r\n (wine wedges on LF; quirks.md). Read/write bytes.
raw = open(p, "rb").read().decode("latin-1")
out, inj = [], False
for l in raw.split("\r\n"):
    if l.strip().startswith("EditPackages="):
        if not inj:
            out += ["EditPackages=Core", "EditPackages=Engine", "EditPackages=IpDrv",
                    "EditPackages=UedPreview", "EditPackages=UedPreviewDX"]
            inj = True
        continue
    out.append(l)
# append content-mount Paths after the last stock Paths line so DeusEx.u's content closure resolves
extra = []
for d in sorted(glob.glob("/gc*")):
    for ext in ("u", "utx", "uax", "umx", "dx"):
        if glob.glob(f"{d}/*.{ext}") or glob.glob(f"{d}/*.{ext.upper()}"):
            extra.append(f"Paths={d}/*.{ext}")
last = max(i for i, l in enumerate(out) if l.strip().lower().startswith("paths="))
out[last + 1:last + 1] = extra
open(p, "wb").write(("\r\n".join(out)).encode("latin-1"))
PY

cd "$B/System"
export WINEDLLOVERRIDES="winealsa.drv=d"
timeout 60 wineboot -u >/dev/null 2>&1 || true
wine ./UCC.exe make -ini=DeusEx.ini 2>&1 | tail -5
test -e "$B/System/UedPreview.u" -a -e "$B/System/UedPreviewDX.u" \
  || { echo "compile FAILED (no output .u)"; exit 4; }
echo "compiled: UedPreview.u UedPreviewDX.u"
