"""Unit tests for the abs->rel VNC pointer bridge (uned/vnc_input_bridge.py).

The bridge lives in the container substrate dir, not the uedcli package, so it is loaded
here by file path. These guard the input-translation logic offline -- the live RFB
round-trip is evidence in
dev/docs/specs/2026-06-18-uedcli-viewport-drag-sensitivity-findings.md.
"""

import importlib.util
from pathlib import Path
from unittest import mock

_BRIDGE_PATH = Path(__file__).resolve().parents[2] / "uned" / "vnc_input_bridge.py"
_spec = importlib.util.spec_from_file_location("vnc_input_bridge", _BRIDGE_PATH)
bridge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bridge)


def _run(lines):
    """Feed pipeinput lines through `_handle` exactly as `main` does (swallowing a
    malformed line), returning the list of emitted xdotool commands."""
    emitted = []
    st = bridge._State()
    for line in lines:
        try:
            bridge._handle(line, emitted.append, st)
        except Exception:
            pass
    return emitted


def test_it_tracks_hover_with_absolute_motion():
    emitted = _run(["Pointer 1 400 300 0 None"])
    assert emitted == ["mousemove 400 300"]


def test_it_positions_then_presses_a_button_from_idle():
    emitted = _run(["Pointer 1 598 875 4 ButtonPress-3"])
    # Absolute position FIRST (grab starts at the VNC pointer), THEN the button down.
    assert emitted == ["mousemove 598 875", "mousedown 3"]


def test_it_injects_relative_motion_while_a_button_is_held():
    emitted = _run([
        "Pointer 1 598 875 4 ButtonPress-3",
        "Pointer 1 598 860 4 None",
        "Pointer 1 598 845 4 None",
    ])
    assert emitted == [
        "mousemove 598 875",
        "mousedown 3",
        "mousemove_relative -- 0 -15",
        "mousemove_relative -- 0 -15",
    ]


def test_it_releases_before_resyncing_position():
    # The regression: an absolute reposition while the button is still held reads as a
    # phantom drag delta (it doubled the measured pitch). mouseup MUST precede the resync.
    emitted = _run([
        "Pointer 1 598 875 4 ButtonPress-3",
        "Pointer 1 598 725 4 None",
        "Pointer 1 598 725 0 ButtonRelease-3",
    ])
    assert emitted == [
        "mousemove 598 875",
        "mousedown 3",
        "mousemove_relative -- 0 -150",
        "mouseup 3",
        "mousemove 598 725",
    ]


def test_it_never_emits_absolute_motion_between_press_and_release():
    # A full pure-vertical drag must contain ONLY relative motion between the button
    # down and up -- any absolute `mousemove` there is the over-rotation bug.
    lines = ["Pointer 1 598 875 4 ButtonPress-3"]
    y = 875
    for _ in range(5):
        y -= 12
        lines.append(f"Pointer 1 598 {y} 4 None")
    lines.append(f"Pointer 1 598 {y} 0 ButtonRelease-3")
    emitted = _run(lines)
    down_i = emitted.index("mousedown 3")
    up_i = emitted.index("mouseup 3")
    between = emitted[down_i + 1:up_i]
    assert between == ["mousemove_relative -- 0 -12"] * 5
    assert all("mousemove " not in cmd for cmd in between)


def test_it_does_not_reposition_on_a_chord_press_during_a_held_drag():
    # Press RMB and drag, then also press LMB, release LMB, keep dragging RMB. None of
    # the LMB transitions may emit an absolute mousemove (RMB stays held throughout).
    emitted = _run([
        "Pointer 1 598 875 4 ButtonPress-3",
        "Pointer 1 598 860 4 None",
        "Pointer 1 598 860 5 ButtonPress-1",   # mask 4|1 = 5: add LMB, no move
        "Pointer 1 598 860 4 ButtonRelease-1",  # back to mask 4: drop LMB, no move
        "Pointer 1 598 845 4 None",
    ])
    assert emitted == [
        "mousemove 598 875",
        "mousedown 3",
        "mousemove_relative -- 0 -15",
        "mousedown 1",
        "mouseup 1",
        "mousemove_relative -- 0 -15",
    ]


def test_it_emits_relative_motion_when_a_chord_change_carries_a_move():
    # A button-state change that ALSO moved while another button stays held must not drop
    # the move -- emit it as a relative delta, never an absolute reposition.
    emitted = _run([
        "Pointer 1 598 875 4 ButtonPress-3",
        "Pointer 1 590 860 5 ButtonPress-1",   # add LMB AND move (-8,-15), RMB held
    ])
    assert emitted == [
        "mousemove 598 875",
        "mousedown 3",
        "mousedown 1",
        "mousemove_relative -- -8 -15",
    ]


def test_it_passes_a_wheel_tick_through_as_button_press_release():
    # A scroll tick is a momentary button-4 mask set then cleared.
    emitted = _run([
        "Pointer 1 400 300 8 ButtonPress-4",
        "Pointer 1 400 300 0 ButtonRelease-4",
    ])
    assert emitted == [
        "mousemove 400 300",  # press from idle positions first
        "mousedown 4",
        "mouseup 4",
        "mousemove 400 300",  # release to idle resyncs
    ]


def test_it_passes_through_keysyms():
    emitted = _run([
        "Keysym 1 1 65 A KeyPress",
        "Keysym 1 0 65 A KeyRelease",
    ])
    assert emitted == ["keydown A", "keyup A"]


def test_it_skips_an_unnamed_keysym():
    # x11vnc emits "None" as the name for a keysym XKeysymToString() can't name; passing
    # that to xdotool would error, so it must be dropped, not emitted.
    emitted = _run(["Keysym 1 1 0 None KeyPress"])
    assert emitted == []


def test_it_drops_viewonly_discarded_events():
    # A negative client# means x11vnc already discarded the event (viewonly); injecting
    # it would defeat viewonly.
    emitted = _run([
        "Pointer -1 400 300 0 None",
        "Keysym -1 1 65 A KeyPress",
    ])
    assert emitted == []


def test_it_ignores_malformed_and_unknown_lines():
    # Short lines, a non-numeric coordinate field (caught by main's swallow), and an
    # unknown verb must all no-op without crashing or leaking an emit.
    emitted = _run(["", "Pointer 1 400", "Pointer 1 x y z None", "Bogus stuff", "Keysym 1 1"])
    assert emitted == []


def test_injector_respawns_xdotool_on_a_broken_pipe():
    # A dead xdotool would silently freeze the pointer; the injector must respawn and
    # re-emit rather than swallow the write.
    procs = []

    def make_proc():
        p = mock.MagicMock()
        p.poll.return_value = None
        procs.append(p)
        return p

    with mock.patch.object(bridge.subprocess, "Popen", side_effect=lambda *a, **k: make_proc()):
        inj = bridge._Injector({})
        # First proc's stdin breaks on write; second proc accepts it.
        procs[0].stdin.write.side_effect = BrokenPipeError()
        inj.emit("mousedown 3")

    assert len(procs) == 2  # original + one respawn
    procs[1].stdin.write.assert_called_once_with("mousedown 3\n")
    procs[1].stdin.flush.assert_called_once()
