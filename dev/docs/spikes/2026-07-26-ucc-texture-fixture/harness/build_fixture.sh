#!/usr/bin/env bash
# build_fixture.sh — SPIKE: can the GAME'S OWN toolchain (UCC) build a texture package
# from artwork we author, so an offline test fixture needs no copyrighted content and its
# encoder is independent of uedcli?
#
# Why this matters: the native-texture-decode plan's oracle compares our BC1 decode against
# a P8 copy of the same image. That is only evidence if something OTHER than us encoded them
# (dev/docs/plans/2026-07-25-native-texture-formats-plan.md, D7). Lifting the real game
# texture is redistribution; encoding both halves ourselves is circular. UCC is the third way.
#
# Usage:  build_fixture.sh [outdir]      (default: <repo>/_scratch/uccfixture)
# Needs:  wine, a Deus Ex install (for System/), Pillow (in the repo venv).
set -euo pipefail

REPO="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../../../.." && pwd)"
OUT="${1:-$REPO/_scratch/uccfixture}"
GSYS="${UEDCLI_SPIKE_GAMESYS:-$HOME/Games/LutrisDX/drive_c/DX/System}"
PY="$REPO/.venv/bin/python"

# UCC needs a SHORT build path — a long one makes it fail with a bogus
# L"C:\\windows\\system32\\UCC.exe" not found (spikes/levelbuild-friction).
B="/tmp/uccsp$$"

[ -d "$GSYS" ] || { echo "no game System dir at $GSYS (set UEDCLI_SPIKE_GAMESYS)" >&2; exit 3; }
command -v wine >/dev/null || { echo "wine not on PATH" >&2; exit 3; }

rm -rf "$B" "$OUT"; mkdir -p "$B/System" "$B/UccFix/Classes" "$OUT"
cp -r "$GSYS"/. "$B/System/" 2>/dev/null || true

# --- 1. the source artwork: OURS, generated deterministically ------------------------------
# Artwork is TUNED, and the tuning is the spike's result (findings.md §4): features must sit
# WELL ABOVE DXT1's 4x4 block size. Detail AT the block size (a 4px checker) is adversarial to
# the format and pushes a CORRECT decode to 9.8-13.0/255, above the plan's own pass mark. A
# 16px-feature image + smooth ramps gives correct=2.35/255 while keeping per-block endpoint
# variety, so gross layout errors still score 60-97. Pillow writes the 8-bit paletted PCX UE1 P8 wants.
"$PY" - "$B/UccFix/Classes" <<'PY'
import sys, pathlib
from PIL import Image
d = pathlib.Path(sys.argv[1]); d.mkdir(parents=True, exist_ok=True)
W = H = 64
img = Image.new("RGB", (W, H))
px = img.load()
for y in range(H):
    for x in range(W):
        # two-axis ramp + 16px saturated quadrants: 4x DXT1's block size, so a correct
        # decode is near-lossless while endpoints still differ block to block.
        q = ((x // 16) + (y // 16)) & 1
        px[x, y] = ((x * 4) % 256, (y * 4) % 256, 255 if q else 40)
img.convert("P", palette=Image.ADAPTIVE, colors=256).save(d / "fixture.pcx")
print("wrote", d / "fixture.pcx")
PY

# --- 2. the UnrealScript that imports it ---------------------------------------------------
# #exec runs at compile time and must follow the class declaration immediately.
cat > "$B/UccFix/Classes/UccFix.uc" <<'UC'
//=============================================================================
// UccFix — spike fixture package. The #exec below makes UCC import our own
// artwork and build its mip chain, so the package's pixel bytes are written by
// the game's toolchain, not by uedcli.
//=============================================================================
class UccFix extends Object;

#exec TEXTURE IMPORT NAME=SpikeFixture FILE=Classes\fixture.pcx MIPS=ON
UC

# --- 3. point EditPackages at just ours (CRLF ini — wine wedges on LF; quirks.md) ----------
"$PY" - "$B/System/DeusEx.ini" <<'PY'
import sys
p = sys.argv[1]
raw = open(p, "rb").read().decode("latin-1")
out, inj = [], False
for l in raw.split("\r\n"):
    if l.strip().startswith("EditPackages="):
        if not inj:
            out += ["EditPackages=Core", "EditPackages=Engine", "EditPackages=UccFix"]
            inj = True
        continue
    out.append(l)
open(p, "wb").write(("\r\n".join(out)).encode("latin-1"))
PY

# --- 4. compile ----------------------------------------------------------------------------
cd "$B/System"
export WINEDLLOVERRIDES="winealsa.drv=d"
rm -f UccFix.u
timeout 300 wine ./UCC.exe make -ini=DeusEx.ini > "$OUT/ucc-make.log" 2>&1 || true
grep -viE 'err:ntoskrnl|fixme:' "$OUT/ucc-make.log" | tail -20

# UCC prints "Success - 0 error(s)" even when an #exec import failed (levelbuild-friction:
# "Never trust ucc's exit code or its Success line — the only usable oracle is the artifact").
# NB: filter wine's own stderr first — it emits "ZwLoadDriver failed", which is not ours.
if grep -viE 'err:ntoskrnl|fixme:|wine' "$OUT/ucc-make.log" | grep -qiE 'ExecWarning|Can.t find file|import .* failed'; then
  echo "FAILED: an #exec import failed despite UCC reporting success — see $OUT/ucc-make.log" >&2
  exit 4
fi
if [ ! -e "$B/System/UccFix.u" ]; then
  echo "FAILED: UCC produced no UccFix.u — see $OUT/ucc-make.log" >&2
  exit 4
fi
cp "$B/System/UccFix.u" "$OUT/"
cp "$B/UccFix/Classes/fixture.pcx" "$OUT/"
# The DXT1 half: a FULL 7-level pyramid, each level encoded by Pillow (third-party to uedcli).
# Each DXT1 level is the compression of THAT LEVEL'S UCC-BUILT P8 IMAGE, not a Pillow-downscaled
# copy of mip 0 — so level N of CompMips and level N of Mips are the same picture, which is what
# makes a per-level cross-check meaningful. Pillow's DDS writer emits a single surface, so the
# container is assembled here: a DDS header with mipMapCount=7 plus the concatenated blocks.
"$PY" - "$OUT" "$REPO" <<'PY'
import io, struct, sys, pathlib
from PIL import Image
d = pathlib.Path(sys.argv[1])
sys.path.insert(0, sys.argv[2])          # the repo root, so `uedcli` imports
from uedcli import utexture

pkg = utexture.load_package(str(d / "UccFix.u"))
i = utexture.textures(pkg)[0]
tex = utexture.decode_texture(pkg, i)
pal = utexture.decode_palette(pkg, utexture.export_index_of_ref(pkg, tex.palette_ref))

blocks = []
for m in tex.mips:
    rgb = Image.frombytes("RGB", (m.width, m.height), utexture.mip0_to_rgb(m, pal))
    buf = io.BytesIO()
    rgb.save(buf, format="DDS", pixel_format="DXT1")
    blocks.append(buf.getvalue()[128:])          # strip each single-surface header

w, h = tex.mips[0].width, tex.mips[0].height
DDSD = 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000 | 0x20000        # +LINEARSIZE +MIPMAPCOUNT
hdr = bytearray(128)
hdr[0:4] = b"DDS "
struct.pack_into("<IIIIII", hdr, 4, 124, DDSD, h, w, len(blocks[0]), 0)
struct.pack_into("<I", hdr, 28, len(blocks))                 # dwMipMapCount
struct.pack_into("<II", hdr, 76, 32, 0x4)                    # pixelformat size, DDPF_FOURCC
hdr[84:88] = b"DXT1"
struct.pack_into("<I", hdr, 108, 0x1000 | 0x400000 | 0x8)    # TEXTURE|MIPMAP|COMPLEX
(d / "fixture.dds").write_bytes(bytes(hdr) + b"".join(blocks))
print(f"wrote {d/'fixture.dds'} — {len(blocks)} DXT1 levels, "
      f"{[len(b) for b in blocks]} bytes each")
PY
echo "built: $OUT/UccFix.u  ($(stat -c%s "$OUT/UccFix.u") bytes)"
rm -rf "$B"
