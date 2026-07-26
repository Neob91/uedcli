#!/usr/bin/env python3
"""preview_batch.py — the WHOLE `--game` preview batch, run in the container via ONE
`docker exec` (spec 2026-07-17 one-exec driver). Replaces the old per-operation docker-exec
host driving (deliver / travel / each pose / each grab / each cp). Talks to the in-game
UedPreview link on 127.0.0.1:7777.

Wire: a JSON request on STDIN
  {"deliver": "<mapfilename>"|null, "stem": "<stem>", "rebuild": bool,
   "window_title": "...", "window_exclude": [...],
   "shots": [[x, y, z, pitchUU, yawUU], ...]}
and a length-framed stream on STDOUT — per shot, a JSON status line then (iff ok) a 4-byte
big-endian length + the PNG bytes:
  {"ok": true}\n <u32 len> <png bytes>            (a captured shot)
  {"ok": false, "err": "..."}\n                  (a failure — no binary frame; host closes+reboots)
Exit non-zero on a setup/travel failure (host reboot-retries). All socket reads are bounded.
"""
import json
import os
import socket
import struct
import subprocess
import sys
import time

LINK_PORT = 7777
MAPS = "/work/dx/Maps"
PREVIEW = "/resources/preview"
# Frame settle: PrepareCamera poses the camera but the window only repaints on the game's next
# render pass, so grab too soon and you capture the PREVIOUS pose. The settle can't live in the
# link verb (the bPlayersOnly freeze also freezes its Tick/Timer), so it lives here — a short
# wait between the OK and the X-grab. Spiked; env-overridable. (~1-2 frames is enough since the
# world is frozen; 0.15s is conservative padding, far below the old 0.4s host sleep.)
SETTLE_S = float(os.environ.get("UED_SETTLE_S", "0.2"))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # baked next to us at /opt/uedpreview
import preview_shots as ps  # noqa: E402  (the shared shot model — resolves @actor poses)

_req = 0
_actor_cache: dict = {}


def _deg_to_uu(deg):
    return round(deg * 65536 / 360.0) % 65536


def _actor_loc(name):
    """@actor → (x,y,z) via the game (cached), or None if not found."""
    if name in _actor_cache:
        return _actor_cache[name]
    loc = None
    try:
        s = _connect()
        try:
            ok, lines = _cmd(s, "GetActorLocation " + name)
            if ok:
                for ln in lines:
                    if b"Location " in ln:
                        x, y, z = ln.split(b"Location ", 1)[1].split()[:3]
                        loc = (int(x), int(y), int(z))
        finally:
            s.close()
    except OSError:
        loc = None
    _actor_cache[name] = loc
    return loc


def resolve_shots(shot_dicts):
    """Turn parsed-Shot dicts (which may carry `@actor` refs) into [x,y,z,pitchUU,yawUU] rows,
    resolving actor refs against the running game. A row is None if its `@actor` isn't found or
    the pose is degenerate (the caller emits ok:false and moves on)."""
    def ap(nm):
        loc = _actor_loc(nm)
        if loc is None:
            raise KeyError(nm)
        return loc

    rows = []
    for d in shot_dicts:
        try:
            rs = ps.resolve_pose(ps.Shot(**d), ap)     # ResolvedShot: eye + pitch/yaw in DEGREES
            pitch = max(-89.9, min(89.9, rs.pitch))     # host-parity clamp (engine picks wrong pole headless)
            rows.append([int(round(rs.eye[0])), int(round(rs.eye[1])), int(round(rs.eye[2])),
                         _deg_to_uu(pitch), _deg_to_uu(rs.yaw)])
        except (KeyError, ValueError, TypeError):       # unresolved @actor / bad shot dict → None
            rows.append(None)
    return rows


def list_actors(cls, sample=0):
    """Query the game for actors of `cls` → [(name, x, y, z), …]; if `sample>0`, evenly-indexed N.
    Raises if the class is unknown (`ERR unknown-class`) so a typo isn't a silent empty result."""
    s = _connect()
    try:
        ok, lines = _cmd(s, "ListActors " + cls, timeout=90)   # a big retail map lists many actors
    finally:
        s.close()
    if not ok:
        raise RuntimeError("ListActors %r failed (unknown class?)" % cls)
    out = []
    for ln in lines:
        if b"Actor " in ln:                            # lines carry a `#<rid> ` prefix — split after "Actor "
            p = ln.split(b"Actor ", 1)[1].split()
            if len(p) >= 4:
                out.append((p[0].decode(errors="replace"), int(p[1]), int(p[2]), int(p[3])))
    if sample and len(out) > sample:
        step = len(out) / sample
        out = [out[int(i * step)] for i in range(sample)]
    return out


def _connect(timeout=8.0):
    s = socket.create_connection(("127.0.0.1", LINK_PORT), timeout=timeout)
    s.settimeout(timeout)
    try:
        s.recv(256)                                # id-less HELLO banner
    except OSError:
        pass
    return s


def _mark():
    """Refresh the idle-watchdog marker so a long batch (slow travel / many shots) is not killed
    mid-flight (reviewers H1). Called throughout — every travel poll and every shot."""
    try:
        os.utime("/work/.last_use", None)
    except OSError:
        pass


def _cmd(s, cmd, timeout=30.0):
    """Send one framed command; read until THIS request's `#<rid> OK`/`ERR` (bounded). Returns
    (ok, lines) where `ok` is id-SCOPED — a stale `OK` from a prior request on the reused shots
    socket is NOT mistaken for this command's success (reviewer M1)."""
    global _req
    _req += 1
    rid = _req
    s.settimeout(timeout)
    try:
        s.sendall(("#%d %s\n" % (rid, cmd)).encode())    # a link mid-(re)spawn can drop the send
    except OSError:
        return False, []
    ok_m, err_m = ("#%d OK" % rid).encode(), ("#%d ERR" % rid).encode()
    buf = b""
    while ok_m not in buf and err_m not in buf:
        try:
            d = s.recv(4096)
        except OSError:
            break
        if not d:
            break
        buf += d
    lines = [ln.strip() for ln in buf.replace(b"\r", b"").split(b"\n") if ln.strip()]
    return ok_m in buf, lines


def _levelname(lines):
    for ln in lines:
        if b"LevelName " in ln:
            return ln.split(b"LevelName ", 1)[1].decode(errors="replace").strip()
    return ""


def _stem(name):
    return name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].removesuffix(".dx").removesuffix(".unr")


def current_level():
    """Live GetURLMap over a fresh connection (the link is transient — travel destroys it)."""
    try:
        s = _connect()
    except OSError:
        return None                                    # link not up / mid-respawn → caller retries
    try:
        ok, lines = _cmd(s, "GetCurrentLevelName")
        return _levelname(lines) if ok else None
    except OSError:
        return None
    finally:
        s.close()


def deliver(mapfile):
    """Post-boot symlink /resources/preview/<mapfile> into the local Maps dir (lowercased)."""
    dst = os.path.join(MAPS, mapfile.lower())
    try:
        os.remove(dst)
    except OSError:
        pass
    os.symlink(os.path.join(PREVIEW, mapfile), dst)


def travel(stem, timeout=480):
    """3-phase handshake: wait for a possessed link → TravelToLevel (OK before the open) →
    reconnect-poll GetURLMap == stem (the `open` destroyed the link; the console respawns it).
    The host only runs this after boot-READY (link port up = a pawn was possessed), so phase-1
    is short: if the link is not answering promptly the game is wedged/dead → fail FAST so the
    host reboot-retries instead of stalling."""
    deadline = time.time() + 25
    while time.time() < deadline:
        _mark()
        if current_level():
            break
        time.sleep(2)
    else:
        raise RuntimeError("no possessed link within 25s (game wedged/dead — reboot)")

    deadline = time.time() + 60
    while time.time() < deadline:
        _mark()
        ok = False
        try:
            s = _connect()
            ok, _ = _cmd(s, "TravelToLevel " + stem)   # id-scoped OK, not a substring scan
            s.close()
        except OSError:
            ok = False
        if ok:
            break
        time.sleep(2)
    else:
        raise RuntimeError("TravelToLevel %r not accepted" % stem)

    deadline = time.time() + timeout
    while time.time() < deadline:
        _mark()                                        # long cold-map poll must not idle-die (H1)
        cur = current_level()
        if cur and _stem(cur).casefold() == stem.casefold():
            return
        time.sleep(2)
    raise RuntimeError("never possessed a pawn on %r within %ds" % (stem, timeout))


def _bump_travel_count():
    try:
        p = "/work/.travel_count"
        c = int(open(p).read().strip()) if os.path.exists(p) else 0
        open(p, "w").write(str(c + 1))
    except Exception:
        pass


def xgrab(title, exclude):
    """X-grab the game window off :99 (title-matched, splash excluded) → PNG bytes. Patterns are
    matched as FIXED strings (`grep -F`) passed via env, NOT interpolated into the shell, so a `'`
    or regex metachar in title/exclude can't inject or misbehave (reviewer M5). Empty excludes are
    dropped (an empty pattern matches everything and would exclude ALL windows)."""
    env = dict(os.environ, DISPLAY=":99", UED_TITLE=title)
    grep_excl = ""
    for i, e in enumerate([e for e in exclude if e]):
        env["UED_EXC%d" % i] = e
        grep_excl += ' | grep -viF -- "$UED_EXC%d"' % i
    script = ('g=$(wmctrl -lG | grep -iF -- "$UED_TITLE"%s | sort -k5 -n | tail -1 '
              "| awk '{print $1}'); "
              '[ -n "$g" ] && import -window "$g" png:- || { echo "no game window" >&2; exit 3; }'
              % grep_excl)
    r = subprocess.run(["bash", "-c", script], capture_output=True, timeout=60, env=env)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError("X-grab found no game window (title~%r): %s"
                           % (title, r.stderr.decode(errors="replace")[-200:]))
    return r.stdout


def _emit(out, ok, png=None, err=None):
    out.write((json.dumps({"ok": ok} if ok else {"ok": False, "err": err}) + "\n").encode())
    if ok and png is not None:
        out.write(struct.pack(">I", len(png)))
        out.write(png)
    out.flush()


def main():
    req = json.load(sys.stdin)
    _mark()                                            # mark activity → reset the idle watchdog
    out = sys.stdout.buffer
    stem = req["stem"]

    if req.get("deliver"):
        deliver(req["deliver"])

    cur = current_level()
    if req.get("rebuild") or not (cur and _stem(cur).casefold() == stem.casefold()):
        travel(stem)
        _bump_travel_count()

    # QUERY mode: list (or evenly-sample) a class's actors → plain "Name x y z" lines, no PNGs.
    if req.get("list_class"):
        try:
            actors = list_actors(req["list_class"], int(req.get("sample", 0) or 0))
        except RuntimeError as e:                       # unknown class etc. — clean stderr, no traceback
            sys.stderr.write(str(e) + "\n")
            return 2                                     # distinct rc: a PERMANENT failure, don't reboot
        for nm, x, y, z in actors:
            out.write(("%s %d %d %d\n" % (nm, x, y, z)).encode())
        out.flush()
        return 0

    # Shot rows are already-resolved [x,y,z,pitchUU,yawUU] ("shots") OR parsed-Shot dicts with
    # `@actor` refs the game resolves here ("unresolved" — retail maps, where the host has no trunk).
    rows = req["shots"] if "shots" in req else resolve_shots(req["unresolved"])

    title = req.get("window_title", "deus ex")
    exclude = req.get("window_exclude", [])
    s = _connect()                                 # ONE connection for all shots (same level)
    try:
        for row in rows:
            _mark()                                # keep the idle watchdog at bay across many shots
            if row is None:                        # an @actor didn't resolve — a loud, non-retryable fail
                _emit(out, False, err="actor not found (unresolved @actor pose)")
                return 1
            x, y, z, pitch, yaw = row
            ok, lines = _cmd(s, "PrepareCamera %d %d %d %d %d" % (x, y, z, pitch, yaw))
            if not ok:                             # id-scoped: this shot's OK, not a stale one
                _emit(out, False, err="PrepareCamera failed: "
                      + b" | ".join(lines[-2:]).decode(errors="replace"))
                return 1
            time.sleep(SETTLE_S)                   # let the posed frame draw+present before grabbing
            try:
                png = xgrab(title, exclude)
            except Exception as e:
                _emit(out, False, err=str(e))
                return 1
            _emit(out, True, png=png)
    finally:
        s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
