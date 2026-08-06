#!/usr/bin/env bash
set -euo pipefail

# UnrealEd is an x86 Windows program. This entrypoint runs `wine <exe>` uniformly on every host; the
# x86-execution substrate is chosen by which `wine` is on PATH — native wine on x86_64, or the FEX
# run_x86 shim on arm64 (wine-fex-shim.sh, installed only by the arm64 image). Same editor, driven
# the same way, same output — only the substrate under it adapts (owner ruling 2026-08-06). The arch
# seam is that shim, in the image; this entrypoint and uedcli stay arch-agnostic.

DISPLAY_NUM="${DISPLAY:-:99}"
GEOMETRY="${UED_GEOMETRY:-1600x1200x24}"     # 32-bpp Xvfb won't start under FEX; 24 is required
VNC_PORT="${VNC_PORT:-5900}"
NOVNC_PORT="${NOVNC_PORT:-6080}"
PID_FILE="${UED_PID_FILE:-/run/uned.pid}"
UED_DIR="${UED_DIR:-/opt/UED22}"
export DISPLAY="$DISPLAY_NUM"

# UnrealEd's OpenGL path goes through Mesa; force llvmpipe since there's no GPU under Xvfb. (The
# build editors also force the SoftDrv software device via the crafted ini — see
# editor._force_headless_render_device — but this stays for any OpenGL-touching startup code.)
export LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}"

mkdir -p "$(dirname "$PID_FILE")"
# The mutable host<->container exchange dir (docker cp target). Made explicitly, not a tmpfs — see
# docker-compose.yml.
mkdir -p /work

# wine's runtime dir (set by the image ENV on the FEX substrate; harmless when unset).
[[ -n "${XDG_RUNTIME_DIR:-}" ]] && { mkdir -p "$XDG_RUNTIME_DIR"; chmod 700 "$XDG_RUNTIME_DIR"; }

# A restart (or a snapshotted base image) keeps the filesystem, so a stale X lock can linger and make
# the new Xvfb refuse to start ("Server is already active"), and a stale /run/uned.pid from a prior
# boot would make wine_ctl resolve a dead pid until the real one is written. Clear both.
num="${DISPLAY_NUM#:}"; num="${num%%.*}"
rm -f "/tmp/.X${num}-lock" "/tmp/.X11-unix/X${num}" "$PID_FILE" 2>/dev/null || true

Xvfb "$DISPLAY_NUM" -screen 0 "$GEOMETRY" -nolisten tcp &
XVFB_PID=$!
for _ in $(seq 1 200); do
    xdpyinfo -display "$DISPLAY_NUM" >/dev/null 2>&1 && break
    sleep 0.05
done

# A window manager lets the editor maximize and lays out its child windows; without one the frame is
# stuck small and EWMH (windowactivate / _NET_ACTIVE_WINDOW) doesn't work, which wine_ctl needs.
WM_PID=""
if command -v fluxbox >/dev/null 2>&1; then
    setsid fluxbox >/var/log/fluxbox.log 2>&1 &
    WM_PID=$!
fi

# noVNC is an optional debug viewer, not part of the build. Start it only where present (the native
# x86 image ships it; the FEX image does not), exactly like the fluxbox guard above.
VNC_PID=""; WS_PID=""
if command -v x11vnc >/dev/null 2>&1 && command -v websockify >/dev/null 2>&1; then
    VNC_FLAGS=( -display "$DISPLAY_NUM" -forever -shared -rfbport "$VNC_PORT" -nopw -quiet )
    if [[ "${VNC_VIEW_ONLY:-1}" == "1" ]]; then
        VNC_FLAGS+=( -viewonly )
    else
        VNC_FLAGS+=( -pipeinput "python3 /opt/uned/vnc_input_bridge.py" )
    fi
    x11vnc "${VNC_FLAGS[@]}" >/var/log/x11vnc.log 2>&1 &
    VNC_PID=$!
    websockify --web=/usr/share/novnc "$NOVNC_PORT" "localhost:$VNC_PORT" \
        >/var/log/websockify.log 2>&1 &
    WS_PID=$!
fi

WINE_PGID=""
cleanup() {
    [[ -n "$WINE_PGID" ]] && kill -- "-$WINE_PGID" 2>/dev/null || true
    kill "$XVFB_PID" ${WM_PID:+$WM_PID} ${VNC_PID:+$VNC_PID} ${WS_PID:+$WS_PID} 2>/dev/null || true
    rm -f "$PID_FILE"
}
trap cleanup EXIT INT TERM

# Fresh logs each boot (the editor writes into its own dir on the per-container COW overlay).
: > "$UED_DIR/Editor.log" 2>/dev/null || true
rm -f "$UED_DIR/Running.ini" 2>/dev/null || true; : > "$UED_DIR/Running.ini" 2>/dev/null || true

# The package search path ([Core.System] Paths) and the render device are composed HOST-SIDE: every
# editor-driving verb bind-mounts a crafted unrealtournament.ini over the baked one PRE-LAUNCH (see
# editor.ensure_editor). The entrypoint no longer touches either.

if [[ "${LAUNCH_UED:-1}" == "1" ]]; then
    UED_EXE="${UED_EXE:-$(ls "$UED_DIR"/[Uu]nreal[Ee]d.exe 2>/dev/null | head -1)}"
    if [[ -z "$UED_EXE" || ! -f "$UED_EXE" ]]; then
        echo "entrypoint: UnrealEd executable not found in $UED_DIR" >&2
        exit 1
    fi
    exe="$(basename "$UED_EXE")"
    # `wine` is the substrate shim (native or FEX). setsid puts the whole wine tree in one process
    # group we can reap as a unit.
    setsid bash -c "cd '$UED_DIR' && exec wine '$exe' -log=Editor.log" >/var/log/uned.log 2>&1 &
    WINE_PGID=$!

    # Find the MAIN editor frame by title via xdotool (a raw X query — independent of the WM's EWMH
    # client list, which wmctrl reads), excluding the "…Log Window". Its _NET_WM_PID is the pid that
    # OWNS the frame — the right pid on BOTH substrates with no arch branch (native wine's editor
    # process, or under FEX the live process running the editor, spike
    # 2026-08-06-materialize-under-fex) — and wine_ctl resolves the window by it. Require the pid to
    # be ALIVE and the SAME across three reads (~1 s) before recording it, so a transient boot window
    # can't leave a dead pid; no pid file exists until then, so wine_ctl status just reports not-ready.
    find_main_frame() {
        local w name
        for w in $(xdotool search --name "Unreal Editor" 2>/dev/null); do
            name="$(xdotool getwindowname "$w" 2>/dev/null || true)"
            [[ "$name" == *"Log Window"* ]] && continue
            [[ "$name" == *"Unreal Editor"* ]] && { echo "$w"; return 0; }
        done
        return 1
    }
    frame=""; settled=""; last=""; stable=0
    for _ in $(seq 1 400); do            # FEX cold boot is ~100 s — be generous
        frame="$(find_main_frame || true)"
        if [[ -n "$frame" ]]; then
            wpid="$(xdotool getwindowpid "$frame" 2>/dev/null || true)"
            if [[ -n "$wpid" ]] && kill -0 "$wpid" 2>/dev/null; then
                if [[ "$wpid" == "$last" ]]; then stable=$((stable + 1)); else stable=0; fi
                last="$wpid"
                if [[ "$stable" -ge 2 ]]; then settled="$wpid"; break; fi
            fi
        fi
        kill -0 "$WINE_PGID" 2>/dev/null || { echo "entrypoint: editor exited before a window settled" >&2; break; }
        sleep 0.5
    done
    if [[ -n "$settled" ]]; then
        echo "$settled" > "$PID_FILE"
        wmctrl -i -r "$frame" -b add,maximized_vert,maximized_horz 2>/dev/null || true
        echo "entrypoint: editor main frame $frame owner pid $settled"
    else
        echo "entrypoint: editor window never settled" >&2
    fi
fi

echo "entrypoint: noVNC ${WS_PID:+at http://localhost:${NOVNC_PORT}/vnc.html}${WS_PID:-disabled (no x11vnc)}"

if [[ $# -gt 0 ]]; then
    exec "$@"
fi

# Idle so `docker exec` can drive wine_ctl.py against the live editor.
while true; do
    sleep 3600 &
    wait $!
done
