# uedcli-game — the `level photo --game` image (spec 2026-07-13 + gate folds).
# Thin layer over the editor base: warm wineprefix + the compiled UedPreview packages +
# the staged boot map + the game entrypoint. The .u compile happens in build-image.sh's
# MOUNTED builder step (a Docker RUN cannot see the asset mounts). Build:
#   docker build -t uedcli-game -f uedcli/game/Dockerfile uedcli/game
# --platform: ued-x86-runtime is amd64 (the wine/x86 DeusEx stack), so pin it — else on an arm64
# host the build looks for a nonexistent arm64 manifest ("no match for platform"). amd64 runs via
# the same qemu emulation the base already uses; on an amd64 host this is a no-op.
FROM --platform=linux/amd64 ued-x86-runtime:latest
ENV LAUNCH_UED=0

# Bake a WARM wineprefix (gate fold: a per-command ephemeral boot must not pay a cold
# ~2min wineboot; this makes the runtime wineboot a 2-4s no-op). Above the churny COPYs
# so a package/entrypoint edit doesn't bust this slow layer.
RUN xvfb-run -a wineboot -u \
 && test -d /wineprefix/drive_c \
 && echo "warm wineprefix baked"

COPY staging/UedPreview.u /opt/uedpreview/pkg/
COPY staging/BootMap.dx /opt/uedpreview/BootMap.dx
COPY preview_batch.py /opt/uedpreview/preview_batch.py
COPY staging/preview_shots.py /opt/uedpreview/preview_shots.py
COPY game-entrypoint.sh /opt/uned/game-entrypoint.sh

# CMD (not ENTRYPOINT): the base ENTRYPOINT brings up Xvfb/noVNC then execs this.
CMD ["bash", "/opt/uned/game-entrypoint.sh"]
