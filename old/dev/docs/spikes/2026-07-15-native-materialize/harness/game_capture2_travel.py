#!/usr/bin/env python3
"""capture2.py - patch AddLight while on the CLEAN boot map, THEN travel to NativeLit.

The game double-faults a few frames after the NativeLit render crash, so we can't drive
frames post-crash. Instead: neuter AddLight (store ebx to a scratch global + early-return,
no fault) WHILE on DX.dx (renders clean, link alive), then TravelToLevel NativeLit. NativeLit
renders through the patched AddLight -> ebx captured, NO crash, game survives. Read the scratch
global = Model.Lights.Data[iLightActors+i], the bad light pointer.

Run inside dx-lum-game (needs --cap-add=SYS_PTRACE). Boot with DX_MAP that stays clean.
"""
import ctypes,os,sys,struct,time,glob,socket
libc=ctypes.CDLL("libc.so.6",use_errno=True)
PTRACE_CONT=7;PTRACE_DETACH=17;PTRACE_SEIZE=0x4206;PTRACE_INTERRUPT=0x4207
libc.ptrace.restype=ctypes.c_long; libc.ptrace.argtypes=[ctypes.c_long,ctypes.c_long,ctypes.c_void_p,ctypes.c_void_p]
def pt(r,p,a=0,d=0):
    ctypes.set_errno(0);x=libc.ptrace(r,p,ctypes.c_void_p(a),ctypes.c_void_p(d));return x,ctypes.get_errno()
BP=0x10b08b4a; CAP=0x10b5c800
def log(m): sys.stderr.write(m+"\n"); sys.stderr.flush()

def link(c, t=6):
    s=socket.create_connection(("127.0.0.1",7777),timeout=t); s.settimeout(4)
    try: s.recv(256)
    except OSError: pass
    s.sendall(("#9 "+c+"\n").encode())
    buf=b""
    try:
        while b"OK " not in buf and b"ERR " not in buf:
            d=s.recv(4096)
            if not d: break
            buf+=d
    except OSError: pass
    s.close(); return buf.decode(errors="replace")
def level():
    r=link("GetCurrentLevelName")
    for ln in r.replace("\r","").splitlines():
        if "LevelName " in ln: return ln.split("LevelName ",1)[1].strip()
    return ""

# 1. find render pid (Render.dll loaded == byte 0x8a at BP); boot map must have rendered.
def dxpids():
    o=[]
    for d in glob.glob("/proc/[0-9]*"):
        try:
            if b"DeusEx.exe" in open(d+"/cmdline","rb").read(): o.append(int(d.split("/")[-1]))
        except: pass
    return o
target=mem=None; t0=time.time()
while time.time()-t0<180 and target is None:
    for pid in dxpids():
        try:
            m=os.open(f"/proc/{pid}/mem",os.O_RDWR); os.lseek(m,BP,0); b=os.read(m,1)
            if b==b"\x8a": target=pid; mem=m; break
            os.close(m)
        except:
            try: os.close(m)
            except: pass
    if target is None: time.sleep(0.3)
if not target: print("DONE no-render-pid (boot map never rendered?)"); sys.exit()
log("target pid=%d, boot level=%r @ %.0fs"%(target,level(),time.time()-t0))

def rd(a,n): os.lseek(mem,a,0); return os.read(mem,n)
def wr(a,b): os.lseek(mem,a,0); return os.write(mem,b)
orig_bp=rd(BP,6); orig_50=rd(BP+6,2); cap0=struct.unpack("<I",rd(CAP,4))[0]
log("orig@BP=%s orig@0x50=%s CAP_before=0x%08x"%(orig_bp.hex(),orig_50.hex(),cap0))

# 2. seize+interrupt, patch, cont
seized=[int(t) for t in os.listdir("/proc/%d/task"%target) if pt(PTRACE_SEIZE,int(t),0,0)[0]==0]
for t in seized:
    pt(PTRACE_INTERRUPT,t)
    try: os.waitpid(t,0)
    except: pass
patch_bp=b"\x89\x1d"+struct.pack("<I",CAP)   # mov [CAP],ebx
wr(BP,patch_bp); wr(BP+6,b"\x30\xc0")        # xor al,al
log("patched@BP=%s @0x50=%s"%(rd(BP,6).hex(),rd(BP+6,2).hex()))
for t in seized: pt(PTRACE_CONT,t,0,0)
for t in seized: pt(PTRACE_DETACH,t,0,0)

# 3. travel to NativeLit
log("traveling to NativeLit ...")
for _ in range(8):
    r=link("TravelToLevel NativeLit")
    if "OK TravelToLevel" in r: break
    time.sleep(1)
else:
    log("travel not accepted: "+r.strip().replace("\n"," | "))

# 4. wait for NativeLit + read CAP
lv=""; caps=[]
for i in range(40):
    time.sleep(1)
    try: lv=level()
    except Exception: lv="?"
    v=struct.unpack("<I",rd(CAP,4))[0]
    if v!=cap0 and v not in caps: caps.append(v)
    if lv=="NativeLit" and caps: break
capf=struct.unpack("<I",rd(CAP,4))[0]
# singularity count
try: sing=open("/work/dx/System/DeusEx.log","rb").read().count(b"Anomalous singularity")
except Exception: sing="?"
mp=None
if capf not in (0,cap0):
    try: os.lseek(mem,(capf&0xffffffff)+0x1e0,0); os.read(mem,1); mp=True
    except: mp=False
print("RESULT level=%r singularities=%s CAP=0x%08x mapped[+0x1e0]=%s distinct=%s"%(
    lv,sing,capf,mp,[hex(x) for x in caps]),flush=True)
if 0<capf<0x10000:
    print("  => ebx SMALL INT %d => Model.Lights holds an UNRESOLVED raw ref (not an AActor*)"%capf,flush=True)
elif mp is False:
    print("  => ebx heap-ish but UNMAPPED => resolved to freed/wrong object (lifetime/reloc)",flush=True)
elif mp is True:
    print("  => ebx MAPPED => that call's light was valid; if game still crashed unpatched, bad one differs",flush=True)
print("DONE",flush=True)
