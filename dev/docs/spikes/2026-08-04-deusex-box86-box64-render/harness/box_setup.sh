#!/usr/bin/env bash
# box_setup.sh — build the box64/box32 stack that runs x86 wine on this arm64
# (Apple-Silicon) host WITHOUT qemu. Run on a native arm64 debian:bookworm
# container (uname -m = aarch64, NO --platform linux/amd64). Idempotent-ish.
#
# box86 is NOT used: it is an armhf (32-bit ARM) binary and this host's CPU has
# no aarch32 EL0 (Apple Silicon), so box86 cannot run here at all. box64 is a
# native arm64 binary; its experimental BOX32 subsystem runs 32-bit x86.
set -eu
export DEBIAN_FRONTEND=noninteractive

apt-get update -qq
apt-get install -y -qq git cmake build-essential python3 ca-certificates \
  gcc-x86-64-linux-gnu gcc-i686-linux-gnu

# --- box64 with BOX32 (32-bit x86) ---
cd /root
[ -d box64 ] || git clone --depth 1 https://github.com/ptitSeb/box64
cd box64 && mkdir -p build && cd build
cmake .. -DARM_DYNAREC=ON -DBOX32=ON -DCMAKE_BUILD_TYPE=RelWithDebInfo
make -j2                      # NB: pids.max=512 here — a big -j exhausts threads (errno 11)
BOX=/root/box64/build/box64

# --- x86 wine + i386 runtime (box64 executes these; qemu never touches them) ---
dpkg --add-architecture i386
apt-get update -qq
apt-get install -y -qq libc6:i386 libstdc++6:i386
apt-get install -y -qq --no-install-recommends wine wine32:i386
apt-get install -y -qq --no-install-recommends \
  xvfb x11-apps x11-utils xauth wmctrl imagemagick net-tools procps psmisc

# --- trivial-stack proof (do this BEFORE the game) ---
cat > /root/hello.c <<'EOF'
#include <stdio.h>
int main(){ printf("HELLO sizeof(long)=%zu\n", sizeof(long)); return 0; }
EOF
x86_64-linux-gnu-gcc /root/hello.c -o /root/hello64dyn   # dynamic — box64 wants dynamic, NOT -static
i686-linux-gnu-gcc   /root/hello.c -o /root/hello32dyn
$BOX /root/hello64dyn                                    # box64  -> sizeof=8
$BOX /root/hello32dyn                                    # box32  -> sizeof=4
$BOX /usr/lib/wine/wine --version                        # -> wine-8.0
WINEARCH=win32 WINEPREFIX=/root/wp32 WINEDEBUG=-all \
  WINELOADER=/usr/lib/wine/wine WINESERVER=/usr/lib/wine/wineserver \
  $BOX /usr/lib/wine/wine wineboot -u                    # inits the prefix
WINEARCH=win32 WINEPREFIX=/root/wp32 WINEDEBUG=-all \
  WINELOADER=/usr/lib/wine/wine WINESERVER=/usr/lib/wine/wineserver \
  $BOX /usr/lib/wine/wine cmd /c "echo BOX64_WINE_IPC_OK"  # wineserver IPC roundtrip
echo "box64 stack ready. Game boot: box_boot.sh (needs /root/gameroot staged)."
