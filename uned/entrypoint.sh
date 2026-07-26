#!/usr/bin/env bash
set -euo pipefail

DISPLAY_NUM="${DISPLAY:-:99}"
GEOMETRY="${UED_GEOMETRY:-1600x1200x24}"
VNC_PORT="${VNC_PORT:-5900}"
NOVNC_PORT="${NOVNC_PORT:-6080}"
PID_FILE="${UED_PID_FILE:-/run/uned.pid}"

# UnrealEd's OpenGL render device goes through Mesa; force its software
# rasterizer (llvmpipe) since there's no GPU under Xvfb.
export LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}"

mkdir -p "$(dirname "$PID_FILE")"

# The mutable host<->container exchange dir. `docker cp` needs the destination's PARENT to
# exist already, and a `docker compose run` editor may not inherit the service `tmpfs:` mount
# (compose-version-sensitive) — so create it explicitly. No-op if the tmpfs is mounted; falls
# back to the writable overlay (still dies with the container) if it isn't.
mkdir -p /work

# A plain `docker restart` keeps the container filesystem, so a stale X lock can
# linger and make the new Xvfb refuse to start ("Server is already active").
num="${DISPLAY_NUM#:}"; num="${num%%.*}"
rm -f "/tmp/.X${num}-lock" "/tmp/.X11-unix/X${num}" 2>/dev/null || true

Xvfb "$DISPLAY_NUM" -screen 0 "$GEOMETRY" -nolisten tcp &
XVFB_PID=$!

# Wait for the X server to accept connections before launching anything that needs it.
for _ in $(seq 1 100); do
    if xdpyinfo -display "$DISPLAY_NUM" >/dev/null 2>&1; then
        break
    fi
    sleep 0.05
done

# A window manager lets the editor maximize and lays out its child windows
# correctly; without one the frame is stuck at a small default size.
WM_PID=""
if command -v fluxbox >/dev/null 2>&1; then
    DISPLAY="$DISPLAY_NUM" fluxbox >/var/log/fluxbox.log 2>&1 &
    WM_PID=$!
fi

VNC_FLAGS=( -display "$DISPLAY_NUM" -forever -shared -rfbport "$VNC_PORT" -nopw -quiet )
if [[ "${VNC_VIEW_ONLY:-1}" == "1" ]]; then
    VNC_FLAGS+=( -viewonly )
else
    # Route interactive pointer input through the absolute->relative bridge so a
    # browser RMB-drag rotates the viewport at a sane rate instead of slamming the
    # camera (UnrealEd's per-frame cursor warp + RFB's absolute positions = unbounded
    # over-rotation). x11vnc stops injecting itself under -pipeinput; the bridge is the
    # sole injector. See vnc_input_bridge.py and
    # dev/docs/specs/2026-06-18-uedcli-viewport-drag-sensitivity-findings.md.
    VNC_FLAGS+=( -pipeinput "python3 /opt/uned/vnc_input_bridge.py" )
fi
x11vnc "${VNC_FLAGS[@]}" >/var/log/x11vnc.log 2>&1 &
VNC_PID=$!

websockify --web=/usr/share/novnc "$NOVNC_PORT" "localhost:$VNC_PORT" \
    >/var/log/websockify.log 2>&1 &
WS_PID=$!

WINE_PID=""
cleanup() {
    if [[ -n "$WINE_PID" ]]; then
        kill -- "-$WINE_PID" 2>/dev/null || true
    fi
    wineserver -k 2>/dev/null || true
    kill "$WS_PID" "$VNC_PID" "$XVFB_PID" ${WM_PID:+$WM_PID} 2>/dev/null || true
    rm -f "$PID_FILE"
}
trap cleanup EXIT INT TERM

# Truncate the editor's logs on every boot so a long-lived container starts each run
# clean (there's no longer a per-boot rm -rf reassembly to do this). The editor writes
# these into its own baked dir on the per-container COW overlay — never the repo.
: > /opt/UED22/Editor.log
rm -f /opt/UED22/Running.ini; : > /opt/UED22/Running.ini

# The package search path (`[Core.System] Paths`) is composed HOST-SIDE now: the asset-wiring
# cutover (Part C, 2026-07-14) has every editor-driving command bind-mount a crafted
# unrealtournament.ini over the baked one PRE-LAUNCH, its `[Core.System] Paths` covering the
# config CONTENT dirs (`/resources/<n>`) + `/opt/UED22` + `/stubs`. So the entrypoint no longer
# touches Paths at all — the old `$DEUSEX_ASSETS_DIR` `sed -i` block is GONE (it would in any case
# fail on a single-file bind-mounted ini, whose rename-over sed cannot do). See
# `editor.ensure_editor` / `stub.ephemeral_build_container` and `container_assets.paths_ini_lines`.

if [[ "${LAUNCH_UED:-1}" == "1" ]]; then
    # The editor binary is "unrealed.exe" in UED22 but "UnrealEd.exe" in Ued2 —
    # match case-insensitively.
    UED_EXE="${UED_EXE:-$(ls /opt/UED22/[Uu]nreal[Ee]d.exe 2>/dev/null | head -1)}"
    if [[ -z "$UED_EXE" || ! -f "$UED_EXE" ]]; then
        echo "entrypoint: UnrealEd executable not found in /opt/UED22" >&2
        exit 1
    fi
    # setsid so the wine tree shares a process group we can reap as one unit.
    setsid bash -c "cd /opt/UED22 && exec wine '$(basename "$UED_EXE")' -log" \
        >/var/log/uned.log 2>&1 &
    WINE_PID=$!

    # wine reparents the real editor away from this shell, so record the actual
    # editor PID (what owns the X windows) once it appears.
    for _ in $(seq 1 150); do
        ued_pid="$(pgrep -fi 'unrealed\.exe' | head -1 || true)"
        [[ -n "$ued_pid" ]] && break
        sleep 0.1
    done
    echo "${ued_pid:-$WINE_PID}" > "$PID_FILE"
    echo "entrypoint: launched UnrealEd (pgid=$WINE_PID, editor pid=${ued_pid:-?})"

    # Maximize the editor frame to a deterministic size so the bottom command
    # box lands at a known position for wine_ctl.
    if command -v wmctrl >/dev/null 2>&1; then
        mf=""
        for _ in $(seq 1 60); do
            # `|| true` so a not-yet-present window (grep exit 1) doesn't trip set -e.
            mf="$(wmctrl -l 2>/dev/null | grep -i 'Unreal Editor' | grep -vi 'Log Window' | head -1 | awk '{print $1}' || true)"
            [[ -n "$mf" ]] && break
            sleep 0.5
        done
        if [[ -n "$mf" ]]; then
            wmctrl -i -r "$mf" -b add,maximized_vert,maximized_horz 2>/dev/null || true
        fi
    fi
fi

echo "entrypoint: noVNC at http://localhost:${NOVNC_PORT}/vnc.html"
echo "entrypoint: view-only=${VNC_VIEW_ONLY:-1}"

if [[ $# -gt 0 ]]; then
    exec "$@"
fi

# Idle so `docker exec` can run wine_ctl.py against the live UEd.
while true; do
    sleep 3600 &
    wait $!
done
