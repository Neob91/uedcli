#!/usr/bin/env python3
"""capture_patch.py - get the bad light pointer WITHOUT ptrace-SIGTRAP or +seh.

Binary-patch AddLight in the live game so it STORES ebx (= Model.Lights.Data[iLightActors+i],
the light ptr the renderer passes) into a scratch .data global, then returns before the two
faulting byte-reads. No guest exception is raised (so wine's __except never fires and the
render stops crashing), and we read the captured pointer straight out of memory.

Patch (in Render.dll @ base 0x10b00000):
  0x10b08b4a: 8A 83 E0 01 00 00  (mov al,[ebx+0x1e0])  ->  89 1D <addr LE>  (mov [addr],ebx)
  0x10b08b50: 84 C0              (test al,al)          ->  30 C0            (xor al,al; je taken -> ret)
scratch addr = 0x10b5c800 (.data BSS tail, verified 0 before patch).

Run inside dx-lum-game (needs --cap-add=SYS_PTRACE).
"""
import ctypes,os,sys,struct,time,glob
libc=ctypes.CDLL("libc.so.6",use_errno=True)
PTRACE_CONT=7;PTRACE_DETACH=17;PTRACE_SEIZE=0x4206;PTRACE_INTERRUPT=0x4207
libc.ptrace.restype=ctypes.c_long; libc.ptrace.argtypes=[ctypes.c_long,ctypes.c_long,ctypes.c_void_p,ctypes.c_void_p]
def pt(r,p,a=0,d=0):
    ctypes.set_errno(0);x=libc.ptrace(r,p,ctypes.c_void_p(a),ctypes.c_void_p(d));return x,ctypes.get_errno()
BP=0x10b08b4a
CAP=0x10b5c800
def dxpids():
    o=[]
    for d in glob.glob("/proc/[0-9]*"):
        try:
            if b"DeusEx.exe" in open(d+"/cmdline","rb").read(): o.append(int(d.split("/")[-1]))
        except: pass
    return o
target=mem=None; t0=time.time()
while time.time()-t0<300 and target is None:
    for pid in dxpids():
        try:
            m=os.open(f"/proc/{pid}/mem",os.O_RDWR); os.lseek(m,BP,0); b=os.read(m,1)
            if b==b"\x8a": target=pid; mem=m; break
            os.close(m)
        except:
            try: os.close(m)
            except: pass
    if target is None: time.sleep(0.2)
if not target: print("DONE no-render-pid-300s"); sys.exit()
sys.stderr.write("target=%d @ %.0fs\n"%(target,time.time()-t0)); sys.stderr.flush()
def rd(a,n):
    os.lseek(mem,a,0); return os.read(mem,n)
def wr(a,b):
    os.lseek(mem,a,0); return os.write(mem,b)
# original bytes for restore
orig_bp=rd(BP,6); orig_50=rd(BP+6,2)
cap_before=struct.unpack("<I",rd(CAP,4))[0]
sys.stderr.write("orig@BP=%s orig@0x50=%s CAP_before=0x%08x\n"%(orig_bp.hex(),orig_50.hex(),cap_before)); sys.stderr.flush()
# seize+interrupt every thread so we patch safely
seized=[int(t) for t in os.listdir("/proc/%d/task"%target) if pt(PTRACE_SEIZE,int(t),0,0)[0]==0]
for t in seized:
    pt(PTRACE_INTERRUPT,t)
    try: os.waitpid(t,0)
    except: pass
# apply patch
patch_bp=b"\x89\x1d"+struct.pack("<I",CAP)      # mov [CAP],ebx
patch_50=b"\x30\xc0"                             # xor al,al
wr(BP,patch_bp); wr(BP+6,patch_50)
ver_bp=rd(BP,6); ver_50=rd(BP+6,2)
sys.stderr.write("patched@BP=%s (want %s)  @0x50=%s\n"%(ver_bp.hex(),patch_bp.hex(),ver_50.hex())); sys.stderr.flush()
for t in seized: pt(PTRACE_CONT,t,0,0)
# let the render run through AddLight many times
vals=[]
for _ in range(20):
    time.sleep(0.25)
    v=struct.unpack("<I",rd(CAP,4))[0]
    if v!=cap_before and v not in vals: vals.append(v)
# read final
cap_after=struct.unpack("<I",rd(CAP,4))[0]
mp=None
if cap_after not in (0,cap_before):
    try: os.lseek(mem,(cap_after&0xffffffff)+0x1e0,0); os.read(mem,1); mp=True
    except: mp=False
print("CAPTURED ebx=0x%08x  [ebx+0x1e0]_mapped=%s  distinct_seen=%s"%(cap_after,mp,[hex(x) for x in vals]),flush=True)
if cap_after!=0 and cap_after<0x10000:
    print("  => ebx is a SMALL INT (%d) => Model.Lights holds an UNRESOLVED raw ref, not an AActor*"%cap_after,flush=True)
elif mp is False:
    print("  => ebx is a heap-ish pointer but UNMAPPED => resolved to a freed/wrong object",flush=True)
elif mp is True:
    print("  => ebx points to MAPPED memory (this call was a valid light; the bad one may differ)",flush=True)
# restore original code
for t in seized:
    pt(PTRACE_INTERRUPT,t)
    try: os.waitpid(t,0)
    except: pass
wr(BP,orig_bp); wr(BP+6,orig_50)
for t in seized: pt(PTRACE_DETACH,t,0,0)
print("DONE restored",flush=True)
