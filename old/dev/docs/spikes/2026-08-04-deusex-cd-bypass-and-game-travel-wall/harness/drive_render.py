#!/usr/bin/env python3
# Runs on fex. Waits for :7777, travels to room.dx, poses, cleans. Screenshot grabbed from xdisp2.
import socket, sys, time
PORT=7777; POSE=(0,0,0,0,0)
def conn(t=8):
    s=socket.create_connection(("127.0.0.1",PORT),timeout=t); s.settimeout(t)
    try: s.recv(256)
    except: pass
    return s
def cmd(s,c,tmo=20):
    s.settimeout(tmo); s.sendall((c+"\n").encode()); time.sleep(0.3)
    buf=b""
    t0=time.time()
    while time.time()-t0<tmo:
        try: d=s.recv(4096)
        except: break
        if not d: break
        buf+=d
        if b" OK " in buf or b" ERR " in buf: break
    return buf
# wait for link
for i in range(60):
    try:
        s=conn(); r=cmd(s,"#1 GetCurrentLevelName",5); s.close()
        if b"LevelName" in r: print("bound, level:",r.decode(errors="replace").strip()); break
    except OSError: pass
    time.sleep(2)
else:
    print("NO_BIND"); sys.exit(1)
s=conn()
print("travel:", cmd(s,"#2 TravelToLevel room.dx",8).decode(errors="replace").strip())
# poll until in room
for i in range(20):
    r=cmd(s,"#%d GetCurrentLevelName"%(10+i),4)
    ln=r.decode(errors="replace")
    print("  level:",ln.strip().replace("\r\n"," "))
    if "room" in ln.lower(): break
    time.sleep(1.5)
time.sleep(1.0)
print("pose:", cmd(s,"#50 PrepareCamera %d %d %d %d %d"%POSE,10).decode(errors="replace").strip())
print("clean:", cmd(s,"#51 Clean generic",10).decode(errors="replace").strip())
time.sleep(1.0)
print("RENDER_READY")
s.close()
