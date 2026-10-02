#!/bin/bash
# boot_fex_editor.sh — bring up a DRIVABLE UnrealEd under FEX+wine-10 on an arm64 host.
# Proven recipe (spike 2026-08-06): three containers on one docker network.
#   xdisp  (native arm64) : Xvfb :99 24bpp over TCP  — the shared X server
#   driver (amd64 image)  : fluxbox WM + xdotool (drives by window title; see drive.sh)
#   fex-ed (fextest-wine10-ready) : FEXInterpreter + wine-10 runs unrealed.exe -> xdisp
# The two facts that make it work:
#   1. FEX+wine-10 clears the qemu-i386 SyntaxHighlighting::AddQuote GPF (editor boots).
#   2. render device MUST be SoftDrv, not OpenGLDrv — else the Mesh browser's viewport
#      asserts `RenDev` at startup, and Ignoring it drops to [Recovery Mode] (can't MAP SAVE).
set -eu
IMG_FEX=fextest-wine10-ready:latest
IMG_DRV=dx-lum-uned:latest      # has xdotool + fluxbox
IMG_X=xdisp-saved:latest        # native arm64 Xvfb
UED_SRC="${UED_SRC:?path to a UED22 install dir (unrealed.exe + *.u + inis)}"

docker network create fexnet 2>/dev/null || true
docker rm -f xdisp driver fex-ed 2>/dev/null || true

docker run -d --name xdisp --network fexnet --entrypoint sh "$IMG_X" \
  -c 'Xvfb :99 -screen 0 1600x1200x24 -listen tcp -ac +extension GLX & sleep infinity'
sleep 4
XIP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' xdisp)

docker run -d --name driver --network fexnet -e DISPLAY="$XIP:99" --entrypoint sleep "$IMG_DRV" infinity
docker exec -e XIP="$XIP" driver sh -c 'setsid fluxbox -display '"$XIP"':99 >/tmp/fluxbox.log 2>&1 & sleep 3'

docker run -d --name fex-ed --network fexnet --entrypoint sleep "$IMG_FEX" infinity
docker cp "$UED_SRC" fex-ed:/root/UED22run
docker exec fex-ed bash -c '
  cd /root/UED22run
  # engine packages: use the lowercase pristine set; DO NOT copy uppercase dups (Core.u vs core.u
  # collide on wines case-fold and fail "Cant find edit package Core").
  for u in Core Engine IpDrv; do [ -f "${u}.u" ] || [ -f "$(echo $u|tr A-Z a-z).u" ] || cp /game/System/${u}.u . 2>/dev/null || true; done
  # [Core.System] Paths -> cwd; render device -> SoftDrv (the RenDev fix)
  python3 - <<PY
p="unrealtournament.ini"; s=open(p,encoding="latin-1").read().split("\n"); out=[];cs=False;done=False
for L in s:
    t=L.strip().lower()
    if t.startswith("[") and t.endswith("]"):
        if cs and not done: out.append("Paths=../UED22run/*.u");done=True
        cs=(t=="[core.system]")
    if cs and L.strip().startswith("Paths="):
        if not done: out.append("Paths=../UED22run/*.u");done=True
        continue
    out.append(L)
if cs and not done: out.append("Paths=../UED22run/*.u")
txt="\n".join(out)
import re
for k in ("WindowedRenderDevice","RenderDevice","GameRenderDevice"):
    txt=re.sub(r"(?m)^%s=.*"%k, "%s=SoftDrv.SoftwareRenderDevice"%k, txt)
open(p,"w",encoding="latin-1").write(txt)
PY'

docker exec -e XIP="$XIP" fex-ed bash -c '
  export WINEARCH=win32 WINEPREFIX=/wineprefix32c WINELOADER=/opt/wine-stable/bin/wine
  export WINEDLLPATH=/opt/wine-stable/lib/wine/i386-windows XDG_RUNTIME_DIR=/run/user/0
  mkdir -p /run/user/0; chmod 1777 /run/user/0
  export DISPLAY='"$XIP"':99 WINEESYNC=1 WINEFSYNC=1 WINEDLLOVERRIDES="winealsa.drv=d;mscoree=d;mshtml=d"
  export WINEDEBUG=-all LIBGL_ALWAYS_SOFTWARE=1
  cd /root/UED22run; rm -f Editor.log
  setsid bash -c "cd /root/UED22run && exec FEXBash -c \"cd /root/UED22run && exec /opt/wine-stable/bin/wine unrealed.exe -log=Editor.log\"" >/tmp/ued.log 2>&1 &'
echo "booting; XIP=$XIP; wait ~100s then drive with: XIP=$XIP driver /tmp/drive.sh 'MAP ...'"
