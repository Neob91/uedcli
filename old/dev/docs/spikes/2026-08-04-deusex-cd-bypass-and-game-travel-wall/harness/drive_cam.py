#!/usr/bin/env python3
# drive_cam.py — runs on fex: connect to DeusEx UedPreviewLink :7777, pose camera, clean.
# Screenshot is grabbed separately from the X host (xdisp2).
import socket, sys, time
PORT = 7777
POSE = (0, 0, 0, 0, 0)
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
def wait_possessed():
    for _ in range(40):
        try:
            s = connect(); ok, lines = cmd(s, "GetCurrentLevelName"); s.close()
            if ok:
                print("  level:", b" ".join(lines).decode(errors="replace"), flush=True); return True
        except OSError: pass
        time.sleep(2)
    return False
def main():
    if not wait_possessed():
        print("NO_LINK", flush=True); return 1
    s = connect()
    ok, lines = cmd(s, "PrepareCamera %d %d %d %d %d" % POSE)
    print("  PrepareCamera:", ok, lines[-2:] if not ok else "", flush=True)
    ok2, _ = cmd(s, "Clean generic"); print("  Clean generic:", ok2, flush=True)
    time.sleep(1.0)
    s.close()
    print("DRIVE_DONE", flush=True)
    return 0
if __name__ == "__main__":
    sys.exit(main())
