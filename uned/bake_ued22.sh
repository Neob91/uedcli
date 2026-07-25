#!/usr/bin/env bash
# One-time generator for the committed Tools/uedctl/uned/UED22/ editor substrate.
#
# Copies Extra/UED22 -> Tools/uedctl/uned/UED22 and bakes the OpenGL/windowed/viewport ini
# settings UnrealEd needs under wine+llvmpipe, replacing the runtime ued2_stub.sh
# symlink-farm + ini-patching with a committed, deterministic, pre-baked editor dir.
#
# Storage: the .u/.dll/.exe binaries are byte-identical to Extra/UED22, so git
# stores each blob only once; only the baked *.ini are new blobs. The cost is
# working-tree disk (a second ~105MB copy), accepted deliberately.
#
# EditPackages for the engine/builder set stay ACTIVE; DeusEx*/LUM lines are
# COMMENTED OUT (prefixed ';') so the editor boots headless without base DX content
# and they can be re-enabled (uncommented) against a real Deus Ex install.
set -euo pipefail
SRC="${1:-Extra/UED22}"
DST="${2:-Tools/uedctl/uned/UED22}"
KEEP="core engine editor fire ipdrv extension davesbrushbuilders framebuilder rahnembrushbuilders extendedbuilders tarquinbrushbuilders unrealedex tarquinextrudebuilder"

rm -rf "$DST"
mkdir -p "$DST"
cp -a "$SRC"/. "$DST"/

# Fresh runtime files so the editor regenerates them in the committed dir at first
# run rather than dirtying the repo with logs.
: > "$DST/Editor.log" 2>/dev/null || true
rm -f "$DST/Running.ini" 2>/dev/null || true

python3 - "$DST" "$KEEP" <<'PY'
import sys, glob, os, re
dst, keep = sys.argv[1], {s.lower() for s in sys.argv[2].split()}
for ini in sorted(glob.glob(os.path.join(dst, "*.ini"))):
    txt = open(ini, "rb").read().decode("latin1")
    out = []
    for line in txt.splitlines(keepends=True):
        s = line.strip()
        if s.lower().startswith("editpackages="):
            name = s.split("=", 1)[1].strip().lower()
            if name not in keep:
                out.append(";" + line)   # comment out, don't delete
                continue
        out.append(line)
    txt = "".join(out)
    txt = re.sub(r"(?im)^(WindowedRenderDevice=).*$", r"\1OpenGLDrv.OpenGLRenderDevice", txt)
    txt = re.sub(r"(?im)^WindowedColorBits=.*$", "WindowedColorBits=32", txt)
    txt = re.sub(r"(?im)^FullscreenColorBits=.*$", "FullscreenColorBits=32", txt)
    txt = re.sub(r"(?im)^StartupFullscreen=.*$", "StartupFullscreen=False", txt)
    open(ini, "wb").write(txt.encode("latin1"))

ued = os.path.join(dst, "UnrealEd.ini")
if os.path.exists(ued):
    txt = open(ued, "rb").read().decode("latin1")
    # Normalize every saved viewport render device to SoftDrv (D3D9/XOpenGL panes
    # stay gray under wine/llvmpipe).
    txt = re.sub(r"(?im)^Device=(?!SoftDrv\.SoftwareRenderDevice).*RenderDevice\s*$",
                 "Device=SoftDrv.SoftwareRenderDevice", txt)
    # Close auto-open browser surfaces (nothing valid to show after the DX strip).
    lines, sec, out = txt.splitlines(keepends=True), None, []
    for ln in lines:
        st = ln.strip()
        if st.startswith("[") and st.endswith("]"):
            sec = st[1:-1]
        if sec and sec.lower().endswith("browser") and st.lower() == "active=1":
            ln = re.sub(r"(?i)active=1", "Active=0", ln)
        out.append(ln)
    open(ued, "wb").write("".join(out).encode("latin1"))
print("baked", dst)
PY
echo "UED22 substrate baked into $DST — review then commit"
