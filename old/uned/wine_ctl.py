#!/usr/bin/env python3
"""Control the UnrealEd 2 instance running inside this container.

Designed to be run via `docker exec dx-lum-uned …`. Resolves the editor
window by walking the process group rooted at /run/uned.pid (written by
entrypoint.sh) and intersecting with windows on the in-container Xvfb
display. There is no flag to retarget another window — by design.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PID_FILE = Path(os.environ.get("UED_PID_FILE", "/run/uned.pid"))
WIN_CACHE = Path(os.environ.get("UED_WIN_CACHE", "/run/uned.win"))
DISPLAY = os.environ.get("DISPLAY", ":99")
# The editor's main frame is titled "Unreal Editor for Deus Ex"; the log window
# is "Unreal Log Window". "Unreal" matches both; "Editor" picks the main frame.
TITLE_HINT = "Unreal"
MAIN_HINT = "Editor"


class CtlError(RuntimeError):
    pass


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["DISPLAY"] = DISPLAY
    return env


def _run(cmd: list[str], *, capture: bool = False, check: bool = True) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            check=check,
            text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
            env=_env(),
        )
    except FileNotFoundError as e:
        raise CtlError(f"missing binary: {cmd[0]}") from e
    except subprocess.CalledProcessError as e:
        msg = (e.stderr or "").strip() or str(e)
        raise CtlError(f"{' '.join(cmd)} failed: {msg}") from e


def _read_pid() -> int:
    if not PID_FILE.exists():
        raise CtlError(f"no PID file at {PID_FILE} — is UnrealEd running in this container?")
    try:
        return int(PID_FILE.read_text().strip())
    except ValueError as e:
        raise CtlError(f"corrupt PID file: {e}") from e


def _descendant_pids(root_pid: int) -> set[int]:
    """root_pid plus every descendant — wine forks, so the window owner is rarely the root."""
    seen = {root_pid}
    frontier = [root_pid]
    while frontier:
        nxt: list[int] = []
        for pid in frontier:
            res = subprocess.run(
                ["pgrep", "-P", str(pid)],
                text=True, capture_output=True, check=False,
            )
            for tok in res.stdout.split():
                try:
                    child = int(tok)
                except ValueError:
                    continue
                if child not in seen:
                    seen.add(child)
                    nxt.append(child)
        frontier = nxt
    return seen


def _windows_for_pids(pids: set[int]) -> list[str]:
    wins: list[str] = []
    for pid in pids:
        res = subprocess.run(
            ["xdotool", "search", "--pid", str(pid)],
            text=True, capture_output=True, check=False, env=_env(),
        )
        for w in res.stdout.split():
            if w not in wins:
                wins.append(w)
    return wins


def _window_name(wid: str) -> str:
    res = subprocess.run(
        ["xdotool", "getwindowname", wid],
        text=True, capture_output=True, check=False, env=_env(),
    )
    return res.stdout.strip()


def _window_area(wid: str) -> int:
    res = subprocess.run(
        ["xdotool", "getwindowgeometry", "--shell", wid],
        text=True, capture_output=True, check=False, env=_env(),
    )
    g = {}
    for line in res.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            g[k.lower()] = v
    try:
        return int(g.get("width", "0")) * int(g.get("height", "0"))
    except ValueError:
        return 0


def _resolve_window(retries: int = 50, delay: float = 0.2) -> str:
    """Resolve and return the UnrealEd window id.

    Cache contract: the window id is stable for an editor lifespan (the editor
    never recreates its main frame once up). WIN_CACHE stores "pid:wid"; the
    entry is reused only when the recorded pid matches the live pid AND the
    window still exists. A stale cache entry (e.g. after an editor restart) is
    silently discarded and re-resolved. This is the driver-latency fix — it
    skips the descendant-walk + title scan that dominate per-command cost.
    """
    pid = _read_pid()
    # Per-session cache: skip the expensive descendant-walk + title scan when
    # possible. Reuse only if pid matches and the window still exists.
    if WIN_CACHE.exists():
        try:
            cpid, cwid = WIN_CACHE.read_text().strip().split(":", 1)
            if int(cpid) == pid and _window_name(cwid):
                return cwid
        except (ValueError, OSError):
            pass
    last = "could not find an UnrealEd window"
    for _ in range(retries):
        try:
            os.kill(pid, 0)
        except OSError:
            raise CtlError(f"pid {pid} from {PID_FILE} is not alive — UnrealEd has exited")
        candidates: list[str] = []
        for w in _windows_for_pids(_descendant_pids(pid)):
            name = _window_name(w)
            if not name:
                continue
            if TITLE_HINT.lower() not in name.lower():
                # Not the editor's main window (could be a wine tray helper).
                continue
            candidates.append(w)
        if candidates:
            # Prefer the main editor frame ("...Editor...") over the log window,
            # then the largest of those.
            main = [w for w in candidates if MAIN_HINT.lower() in _window_name(w).lower()]
            pool = main or candidates
            pool.sort(key=_window_area, reverse=True)
            wid = pool[0]
            try:
                WIN_CACHE.write_text(f"{pid}:{wid}")
            except OSError:
                pass
            return wid
        time.sleep(delay)
    raise CtlError(last)


def _window_position(wid: str) -> tuple[int, int]:
    res = subprocess.run(
        ["xdotool", "getwindowgeometry", "--shell", wid],
        text=True, capture_output=True, check=False, env=_env(),
    )
    g = {}
    for line in res.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            g[k.lower()] = v
    try:
        return int(g.get("x", "0")), int(g.get("y", "0"))
    except ValueError:
        return 0, 0


def _focus(wid: str, delay: float) -> None:
    # A window manager (fluxbox) runs in the container, so windowactivate works
    # (raises + gives input focus). xdotool's synthetic events (--window) are
    # ignored by wine, so every input below uses real XTEST against this window
    # after activating it.
    _run(["xdotool", "windowactivate", "--sync", wid])
    if delay > 0:
        time.sleep(delay)


# A wine/UnrealEd general-protection-fault pops a modal dialog titled "Critical Error".
# Its presence means the editor has crashed even though the process is still alive.
CRASH_DIALOG_HINT = "Critical Error"


def _crash_dialog_open() -> bool:
    """Fast: is a 'Critical Error' (GPF) dialog on the display? One xdotool search."""
    res = subprocess.run(
        ["xdotool", "search", "--onlyvisible", "--name", CRASH_DIALOG_HINT],
        text=True, capture_output=True, check=False, env=_env(),
    )
    return bool(res.stdout.strip())


def _assert_alive() -> str:
    """FAST precondition for every driving command. Raises CtlError (→ non-zero exit)
    if UnrealEd is not running, has crashed with an error dialog, or lost its window
    (zombie). Returns the resolved window id so the caller needn't resolve again.

    Fast because: pid check is a syscall; the crash-dialog scan is one xdotool call;
    and the window resolve is single-pass (retries=1) and cache-hits in the normal
    case — so it fails fast on a crash instead of the 50×0.2s window-search wait."""
    pid = _read_pid()
    try:
        os.kill(pid, 0)
    except OSError:
        raise CtlError(f"UnrealEd (pid {pid}) is not running — crashed or exited")
    if _crash_dialog_open():
        raise CtlError(f"UnrealEd has crashed — a {CRASH_DIALOG_HINT!r} dialog is open")
    return _resolve_window(retries=1)


def cmd_status(args: argparse.Namespace) -> int:
    pid = _read_pid()
    try:
        os.kill(pid, 0)
        alive = True
    except OSError:
        alive = False
    print(f"pid={pid} alive={alive} display={DISPLAY}")
    if alive:
        try:
            wid = _resolve_window(retries=1)
            print(f"window={wid} name={_window_name(wid)!r}")
        except CtlError as e:
            print(f"window=<unresolved: {e}>")
    return 0


def cmd_wait(args: argparse.Namespace) -> int:
    retries = max(1, int(args.timeout / 0.2))
    wid = _resolve_window(retries=retries, delay=0.2)
    print(wid)
    return 0


def cmd_focus(args: argparse.Namespace) -> int:
    _focus(_assert_alive(), args.delay)
    return 0


def cmd_type(args: argparse.Namespace) -> int:
    wid = _assert_alive()
    _focus(wid, args.delay)
    # Real XTEST keystrokes to the focused window (no --window: wine drops synthetic events).
    _run(["xdotool", "type", "--delay", str(args.char_delay), args.text])
    return 0


def cmd_key(args: argparse.Namespace) -> int:
    wid = _assert_alive()
    _focus(wid, args.delay)
    for chord in args.keys:
        _run(["xdotool", "key", "--clearmodifiers", chord])
    return 0


def cmd_click(args: argparse.Namespace) -> int:
    wid = _assert_alive()
    _focus(wid, args.delay)
    # Window-relative -> absolute, then a real XTEST click (synthetic --window clicks are ignored).
    # Chain move+click in ONE xdotool invocation: `mousemove --sync` alone blocks ~15s under
    # Xvfb+fluxbox waiting for a pointer-arrival event that never arrives, so we drop --sync;
    # chaining in a single process still guarantees the move is processed before the click.
    ox, oy = _window_position(wid)
    _run(["xdotool", "mousemove", str(ox + args.x), str(oy + args.y), "click", str(args.button)])
    return 0


def cmd_drag(args: argparse.Namespace) -> int:
    """Paced relative-motion drag in a viewport — the verified way to drive UnrealEd's mouse
    rotate/move (dev/docs/specs/2026-06-18-uedcli-viewport-drag-sensitivity-findings.md). RMB
    drag = camera rotate; Ctrl+RMB (`--modifier ctrl`) = rotate the selected actor(s).

    UnrealEd warps the captured cursor back to a recenter anchor every frame and derives the delta
    from the move, so ONLY relative motion reads correctly (absolute over-rotates, unbounded). And
    the motion must be SUSTAINED + PACED: it's emitted as one xdotool chain (button state can't
    survive across processes) of small `mousemove_relative` steps with a short sleep between each —
    zero-pause/coalesced steps get dropped, and a too-short press opens the RMB context menu
    instead of rotating. Caller gives a window-relative start (x,y) and a total pixel delta
    (dx,dy); calibrated viewport rate ≈0.06°/px yaw, ≈0.10°/px pitch (set MAP ROTGRID for a clean
    snapped angle)."""
    wid = _assert_alive()
    _focus(wid, args.delay)
    ox, oy = _window_position(wid)
    steps = max(1, args.steps)
    chain = ["xdotool", "mousemove", str(ox + args.x), str(oy + args.y)]
    if args.modifier:
        chain += ["keydown", args.modifier]
    chain += ["mousedown", str(args.button)]
    for i in range(steps):                      # integer per-step deltas summing EXACTLY to dx,dy
        sdx = args.dx * (i + 1) // steps - args.dx * i // steps
        sdy = args.dy * (i + 1) // steps - args.dy * i // steps
        chain += ["mousemove_relative", "--", str(sdx), str(sdy), "sleep", str(args.step_pause)]
    chain += ["mouseup", str(args.button)]
    if args.modifier:
        chain += ["keyup", args.modifier]
    _run(chain)
    return 0


def cmd_shot(args: argparse.Namespace) -> int:
    wid = _assert_alive()
    _focus(wid, 0.2)
    if not shutil.which("import"):
        raise CtlError("imagemagick's `import` not installed in this container")
    _run(["import", "-window", wid, args.path])
    print(args.path)
    return 0


def cmd_exec(args: argparse.Namespace) -> int:
    """Type a line into UnrealEd's bottom 'Command:' box and press Return.

    Clicks the command box first to focus it. Location (window-relative) comes
    from --at, else env UED_CMD_X/UED_CMD_Y, else a default that targets the
    UnrealEd 2.2 command box at the bottom-left of the (maximized) frame.
    """
    wid = _assert_alive()
    _focus(wid, args.delay)

    w, h = _window_size(wid)
    if args.at:
        cx, cy = args.at
    else:
        cx = _env_int("UED_CMD_X")
        cy = _env_int("UED_CMD_Y")
        if cx is None:
            cx = 370          # inside the box, just past the "Command:" label
        if cy is None:
            cy = h - 36       # the command bar sits at the very bottom of the frame

    ox, oy = _window_position(wid)
    # Single chained move+click — `mousemove --sync` alone hangs ~15s under Xvfb+fluxbox
    # (waits for a pointer-arrival event that never comes); chaining keeps move-before-click
    # ordering without the sync. This is the per-command latency fix (was ~16s/command).
    _run(["xdotool", "mousemove", str(ox + cx), str(oy + cy), "click", "1"])
    time.sleep(0.2)
    # The command box keeps the previous command, so clear it first or commands
    # concatenate. Select the field's contents (End, then Shift+Home) and Delete.
    # Avoid Ctrl+A — UnrealEd binds it to "select all actors", not select-text.
    _run(["xdotool", "key", "--clearmodifiers", "End"])
    _run(["xdotool", "key", "--clearmodifiers", "shift+Home"])
    _run(["xdotool", "key", "--clearmodifiers", "Delete"])
    _run(["xdotool", "type", "--delay", str(args.char_delay), args.line])
    _run(["xdotool", "key", "--clearmodifiers", "Return"])
    # Post-check: a console verb (REBUILD/IMPORTADD/PASTE/…) can GPF the editor. Settle
    # briefly, then fail (non-zero) if a crash dialog opened, so the caller knows THIS
    # command crashed it rather than discovering it on the next command.
    time.sleep(0.3)
    if _crash_dialog_open():
        raise CtlError(f"command crashed UnrealEd ({CRASH_DIALOG_HINT!r} dialog opened): {args.line!r}")
    return 0


def cmd_edit_copy(args: argparse.Namespace) -> int:
    """Run EDIT COPY, then read the selection T3D off the X clipboard.

    Copy is selection-scoped (a Begin Map…End Map of just the selection) and does
    NOT offset coordinates — the 32-unit offset is paste-only. Needs xclip.
    """
    # Reuse cmd_exec to type EDIT COPY into the command box.
    exec_args = argparse.Namespace(line="EDIT COPY", char_delay=8, at=None, delay=args.delay)
    cmd_exec(exec_args)
    time.sleep(0.3)
    if not shutil.which("xclip"):
        raise CtlError("xclip not installed in this container")
    res = _run(["xclip", "-selection", "clipboard", "-o"], capture=True)
    sys.stdout.write(res.stdout)
    return 0


def _env_int(name: str):
    val = os.environ.get(name)
    try:
        return int(val) if val is not None else None
    except ValueError:
        return None


def _window_size(wid: str) -> tuple[int, int]:
    res = subprocess.run(
        ["xdotool", "getwindowgeometry", "--shell", wid],
        text=True, capture_output=True, check=False, env=_env(),
    )
    g = {}
    for line in res.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            g[k.lower()] = v
    try:
        return int(g.get("width", "0")), int(g.get("height", "0"))
    except ValueError:
        return 0, 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--delay", type=float, default=0.1,
                   help="seconds after focusing before sending input")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="report PID + window state").set_defaults(func=cmd_status)

    w = sub.add_parser("wait", help="block until the UEd window is up")
    w.add_argument("--timeout", type=float, default=30.0)
    w.set_defaults(func=cmd_wait)

    sub.add_parser("focus", help="raise + focus the UEd window").set_defaults(func=cmd_focus)

    t = sub.add_parser("type", help="type a literal string")
    t.add_argument("text")
    t.add_argument("--char-delay", type=int, default=12, help="ms between keystrokes")
    t.set_defaults(func=cmd_type)

    k = sub.add_parser("key", help="send key chord(s): Return, ctrl+s, alt+F4")
    k.add_argument("keys", nargs="+")
    k.set_defaults(func=cmd_key)

    c = sub.add_parser("click", help="click at window-relative coords")
    c.add_argument("x", type=int)
    c.add_argument("y", type=int)
    c.add_argument("--button", type=int, default=1)
    c.set_defaults(func=cmd_click)

    dg = sub.add_parser("drag", help="paced relative drag in a viewport (RMB=cam rotate; "
                                     "--modifier ctrl = actor rotate)")
    dg.add_argument("x", type=int, help="window-relative start X")
    dg.add_argument("y", type=int, help="window-relative start Y")
    dg.add_argument("dx", type=int, help="total X delta in px (signed)")
    dg.add_argument("dy", type=int, help="total Y delta in px (signed)")
    dg.add_argument("--button", type=int, default=3, help="mouse button (3=RMB, default)")
    dg.add_argument("--modifier", default=None, help="held modifier, e.g. ctrl (Ctrl+RMB rotates "
                                                     "the selected actor)")
    dg.add_argument("--steps", type=int, default=16, help="paced relative steps (keep per-step ≤10px)")
    dg.add_argument("--step-pause", dest="step_pause", type=float, default=0.07,
                    help="seconds between steps (zero-pause steps get dropped)")
    dg.set_defaults(func=cmd_drag)

    s = sub.add_parser("shot", help="screenshot the UEd window to PATH")
    s.add_argument("path")
    s.set_defaults(func=cmd_shot)

    e = sub.add_parser("exec", help="type a line then press Return (optionally click the command box first)")
    e.add_argument("line")
    e.add_argument("--char-delay", type=int, default=8)
    e.add_argument("--at", type=int, nargs=2, metavar=("X", "Y"),
                   help="window-relative coords of the command box to click before typing")
    e.set_defaults(func=cmd_exec)

    ec = sub.add_parser("edit-copy", help="EDIT COPY the current selection, print the clipboard T3D")
    ec.set_defaults(func=cmd_edit_copy)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for tool in ("xdotool", "pgrep"):
        if not shutil.which(tool):
            print(f"error: {tool} not found in this container", file=sys.stderr)
            return 2
    try:
        return args.func(args)
    except CtlError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
