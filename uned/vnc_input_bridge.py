#!/usr/bin/env python3
"""Absolute->relative VNC pointer bridge for UnrealEd viewport drags.

x11vnc injects RFB PointerEvents with `XTestFakeMotionEvent` (ABSOLUTE). UnrealEd,
during a viewport mouse-capture drag, warps the cursor back to a fixed anchor every
frame and derives the camera delta as `commanded_abs - anchor`. With absolute moves
each event is measured against the far anchor, so a tiny intended drag becomes a huge
rotation (the "rotating ultra fast / unusable" symptom). A real mouse never hits this
because the OS feeds the X server RELATIVE deltas.

This script is x11vnc's `-pipeinput` command: with it, x11vnc stops injecting input
itself and streams every event here instead (verified live: under `-pipeinput cat` the
cursor does not move), and we re-inject via XTEST through one persistent `xdotool -`
process:

- While ANY button is held (a drag), inject RELATIVE motion (`mousemove_relative`) so
  the editor's capture-warp reads exactly the intended per-frame delta -- the clean
  ~0.07 deg/px yaw / ~0.12 deg/px pitch rate (findings:
  dev/docs/specs/2026-06-18-uedctl-viewport-drag-sensitivity-findings.md).
- While NO button is held (hover) and on a button-state change, position the cursor
  ABSOLUTELY at the VNC-reported (x,y), so clicks land where the user points and the
  cursor re-syncs after a warp -- a pure-relative bridge would drift the X cursor away
  from the VNC pointer after any capture-warp and make clicks miss.

The press/release ordering is load-bearing: an ABSOLUTE reposition while a button is
held reads to the editor as a drag delta (a phantom rotation -- it doubled the measured
pitch before this was fixed). So position the cursor BEFORE a press only when nothing is
held yet, and resync AFTER a release only once nothing remains held. When a button-state
change arrives WITH motion and a button is still held (a chord mid-drag), the move is
emitted as a relative delta so that frame's rotation is not dropped.

Caveats (documented, accepted): (1) a button-held drag over a NON-viewport widget that
expects absolute tracking (a scrollbar/slider in a browser pane) gets relative motion
too and misbehaves -- noVNC is a viewport-navigation/inspect aid and the editor is
driven via the console, so this is fine. (2) The absolute path emits the raw RFB (x,y),
which is correct ONLY because x11vnc serves the full Xvfb screen with no `-scale`/`-clip`
(VNC framebuffer geometry == X screen geometry); adding `-scale` would break absolute
positioning (relative drags would still work -- a confusing split, so don't add it). (3)
Two viewers dragging the SAME editor at once interleave into one shared bridge state and
will fight -- single-operator preview is the design.

Pipeinput line format (captured live, x11vnc 0.9.16 `-pipeinput tee:/bin/cat`):
    Pointer <client#> <x> <y> <mask> <hint>
    Keysym  <client#> <down> <keysym#> <keysym-name> <hint>
mask bit N (1<<(N-1)) = button N pressed; client# < 0 means viewonly-discarded.
"""

import os
import subprocess
import sys

# RFB button-mask bit -> X button number. RFB packs the wheel as buttons 4/5 (a scroll
# tick is a momentary press+release, handled by the same mousedown/mouseup path).
_MASK_BITS = ((0x01, 1), (0x02, 2), (0x04, 3), (0x08, 4), (0x10, 5))


def _log(msg: str) -> None:
    # stderr is captured to /var/log/x11vnc.log by entrypoint.sh -- the only diagnostic
    # trail when input misbehaves on this crash-prone stack.
    print(f"vnc_input_bridge: {msg}", file=sys.stderr, flush=True)


class _Injector:
    """A self-healing `xdotool -` pipe. A dead xdotool (crash, X glitch) would otherwise
    silently freeze the pointer forever; respawn on write failure and re-emit once."""

    def __init__(self, env: dict) -> None:
        self._env = env
        self._spawn()

    def _spawn(self) -> None:
        self._xdo = subprocess.Popen(
            ["xdotool", "-"], stdin=subprocess.PIPE, env=self._env, text=True
        )

    def emit(self, cmd: str) -> None:
        if self._xdo.poll() is not None:  # died between events
            _log("xdotool exited; respawning")
            self._spawn()
        for attempt in (1, 2):
            try:
                self._xdo.stdin.write(cmd + "\n")
                self._xdo.stdin.flush()
                return
            except (BrokenPipeError, ValueError, OSError) as e:
                _log(f"xdotool write failed ({e!r}); respawning (attempt {attempt})")
                try:
                    self._xdo.kill()
                except Exception:
                    pass
                self._spawn()
        _log(f"dropped after respawn: {cmd!r}")


def _handle(line: str, emit, st: "_State") -> None:
    parts = line.split()
    if not parts:
        return
    kind = parts[0]

    if kind == "Pointer":
        # Pointer <client#> <x> <y> <mask> <hint...>
        if len(parts) < 5:
            return
        if int(parts[1]) < 0:  # viewonly-discarded (belt-and-suspenders; not the wired path).
            return
        x, y, mask = int(parts[2]), int(parts[3]), int(parts[4])
        changed = mask ^ st.last_mask

        if changed:
            presses = changed & mask
            releases = changed & ~mask
            repositioned = False
            if presses and st.last_mask == 0:
                emit(f"mousemove {x} {y}")
                repositioned = True
            for bit, btn in _MASK_BITS:
                if presses & bit:
                    emit(f"mousedown {btn}")
            for bit, btn in _MASK_BITS:
                if releases & bit:
                    emit(f"mouseup {btn}")
            if releases and mask == 0:
                emit(f"mousemove {x} {y}")
                repositioned = True
            # A chord change that arrives WITH motion while a button stays held: don't
            # drop the move, and don't reposition absolutely (would phantom-rotate).
            if mask and not repositioned:
                dx, dy = x - st.last_x, y - st.last_y
                if dx or dy:
                    emit(f"mousemove_relative -- {dx} {dy}")
        elif mask:
            # Drag in progress: feed the editor a clean relative delta.
            dx, dy = x - st.last_x, y - st.last_y
            if dx or dy:
                emit(f"mousemove_relative -- {dx} {dy}")
        else:
            # Hover: track the pointer absolutely.
            emit(f"mousemove {x} {y}")

        st.last_x, st.last_y, st.last_mask = x, y, mask

    elif kind == "Keysym":
        # Keysym <client#> <down> <keysym#> <keysym-name> <hint...>
        if len(parts) < 5:
            return
        if int(parts[1]) < 0:
            return
        down, name = parts[2], parts[4]
        # x11vnc fills the name from XKeysymToString(), which is "None"/absent for an
        # unnamed keysym; xdotool would reject it, so skip rather than emit a bad command.
        if not name or name == "None":
            _log(f"skipping unnamed keysym {parts[3]!r}")
            return
        emit(f"{'keydown' if down == '1' else 'keyup'} {name}")


class _State:
    __slots__ = ("last_x", "last_y", "last_mask")

    def __init__(self) -> None:
        self.last_x = 0
        self.last_y = 0
        self.last_mask = 0


def main() -> int:
    env = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":99")}
    injector = _Injector(env)
    st = _State()
    for line in sys.stdin:
        # A malformed line (field-format drift) must never kill the input channel -- the
        # user would be stuck with a dead mouse mid-session. Log it and keep going.
        try:
            _handle(line, injector.emit, st)
        except Exception as e:
            _log(f"dropped line {line.rstrip()!r}: {e!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
