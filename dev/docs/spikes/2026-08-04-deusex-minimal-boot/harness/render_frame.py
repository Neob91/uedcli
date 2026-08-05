#!/usr/bin/env python3
"""render_frame.py — runs INSIDE the container after minimal_boot.sh links :7777.
Drives the UedPreviewLink to pose the camera at room center looking +X at the
Amark-marked wall, applies the generic stock-field clean, and X-grabs the SoftDrv
window to /work/game_preview_here.png. Stock-engine boot: no Give/ShowHud (no DeusEx.u)."""
import socket, subprocess, sys, time

PORT = 7777
POSE = (0, 0, 0, 0, 0)   # x y z pitchUU yawUU — center, look +X
SETTLE = 0.8
_rid = 0

def connect(t=8.0):
    s = socket.create_connection(("127.0.0.1", PORT), timeout=t); s.settimeout(t)
    try: s.recv(256)
    except OSError: pass
    return s

def cmd(s, c, timeout=30.0):
    global _rid; _rid += 1; rid = _rid
    s.settimeout(timeout); s.sendall(("#%d %s\n" % (rid, c)).encode())
    ok_m, err_m = ("#%d OK" % rid).encode(), ("#%d ERR" % rid).encode()
    buf = b""
    while ok_m not in buf and err_m not in buf:
        try: d = s.recv(4096)
        except OSError: break
        if not d: break
        buf += d
    return ok_m in buf, [l.strip() for l in buf.replace(b"\r", b"").split(b"\n") if l.strip()]

def xgrab(path):
    script = (r'''g=$(wmctrl -lG | grep -iF -- "deus ex" '''
              r'''| grep -viF -- running | grep -viF -- starting | grep -viF -- config '''
              r'''| sort -k5 -n | tail -1 | awk '{print $1}'); '''
              r'''[ -n "$g" ] && import -window "$g" ''' + path + r''' || { echo noWin >&2; exit 3; }''')
    r = subprocess.run(["bash", "-c", script], capture_output=True, timeout=60,
                       env={"DISPLAY": ":99", "PATH": "/usr/bin:/bin:/usr/local/bin"})
    if r.returncode != 0:
        raise RuntimeError("xgrab failed: " + r.stderr.decode(errors="replace")[-200:])
    print("  grabbed", path, flush=True)

def wait_possessed():
    for _ in range(40):
        try:
            s = connect(); ok, lines = cmd(s, "GetCurrentLevelName"); s.close()
            if ok:
                print("  level:", b" ".join(lines).decode(errors="replace"), flush=True); return
        except OSError: pass
        time.sleep(2)
    raise RuntimeError("no possessed link")

def main():
    wait_possessed()
    s = connect()
    ok, lines = cmd(s, "PrepareCamera %d %d %d %d %d" % POSE)
    print("  PrepareCamera:", ok, flush=True)
    if not ok: raise RuntimeError("PrepareCamera failed: %r" % lines[-2:])
    ok, _ = cmd(s, "Clean generic"); print("  Clean generic:", ok, flush=True)
    time.sleep(SETTLE)
    xgrab("/work/game_preview_here.png")
    s.close()
    print("DONE", flush=True)

if __name__ == "__main__":
    sys.exit(main())
