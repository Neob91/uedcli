FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:99
ENV WINEPREFIX=/wineprefix
ENV WINEARCH=win32
ENV WINEDEBUG=-all
# Skip Mono/Gecko prompts — UnrealEd 2 doesn't need them
ENV WINEDLLOVERRIDES="mscoree=;mshtml="

RUN dpkg --add-architecture i386 \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
        ca-certificates \
        procps psmisc \
        python3 \
        tini \
        xvfb xauth x11-utils x11-apps xdotool wmctrl xclip \
        fluxbox \
        x11vnc \
        novnc websockify \
        imagemagick \
        wine wine32 wine64 \
        fonts-wine \
        mesa-utils \
        libgl1:i386 libglx-mesa0:i386 libgl1-mesa-dri:i386 \
 && rm -rf /var/lib/apt/lists/*

# Pre-create the wineprefix so the first container start is fast.
RUN xvfb-run -a wineboot --init \
 && wineserver -w

EXPOSE 6080

# Bake the substrate directly to its final runtime location (was a /repo mount, then a
# boot-time symlink-farm assembly). The editor writes into this dir at runtime, but the
# per-container COW overlay keeps those writes ephemeral (no repo pollution — there is no
# /repo mount; D4). Order: binaries+inis first (re-bake only), then the scripts (edited most
# often) so a wine_ctl/entrypoint tweak reuses every layer above.
COPY UED22/ /opt/UED22/
COPY entrypoint.sh wine_ctl.py vnc_input_bridge.py /opt/uned/

WORKDIR /opt/uned
ENTRYPOINT ["/usr/bin/tini", "--", "bash", "/opt/uned/entrypoint.sh"]
