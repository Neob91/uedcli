#!/usr/bin/env python3
"""game_int3_catch_ebx.py - read EBX at the Render.dll AddLight fault (0x10b08b4a) in the headless game.

Run INSIDE the dx-lum-game container (needs --cap-add=SYS_PTRACE on its docker run; see
engine-internals/gotchas.md sec 4). It self-selects the DeusEx.exe pid whose byte at 0x10b08b4a
reads 0x8a (Render.dll loaded == rendering has started), plants an INT3 there via /proc/<pid>/mem,
catches the SIGTRAP, and for each hit reports EBX (= Model.Lights[iLightActors], the light ptr)
and whether [EBX+0x1e0] is mapped. An UNMAPPED probe => bad light pointer (the crash).

WHY the whole song and dance: gdb absent; winedbg attach yields nothing; the guest AV is NOT a
tracer-visible Linux SIGSEGV (PTRACE_SEIZE catches zero signals) - but an INT3 IS (SIGTRAP).

BLOCKER as of 2026-07-16: game boots reliably WEDGE (wine pipe_read deadlock, or wrote ~7250 log
bytes then never travels to NativeLit), so a boot that reaches NativeLit render is rare. Retry with
fast deadlock-detect (empty log + wchan=pipe_read @30s => kill+retry) until one renders (sg>0), then
run this. See gotchas.md sec 4-5.
"""
import ctypes,os,sys,struct,signal,time,glob
libc=ctypes.CDLL("libc.so.6",use_errno=True)
PTRACE_CONT=7;PTRACE_GETREGS=12;PTRACE_SETREGS=13;PTRACE_DETACH=17;PTRACE_SINGLESTEP=9;PTRACE_SEIZE=0x4206;PTRACE_INTERRUPT=0x4207
libc.ptrace.restype=ctypes.c_long; libc.ptrace.argtypes=[ctypes.c_long,ctypes.c_long,ctypes.c_void_p,ctypes.c_void_p]
def pt(r,p,a=0,d=0):
    ctypes.set_errno(0);x=libc.ptrace(r,p,ctypes.c_void_p(a),ctypes.c_void_p(d));return x,ctypes.get_errno()
class R(ctypes.Structure):
    _fields_=[(n,ctypes.c_ulonglong) for n in("r15","r14","r13","r12","rbp","rbx","r11","r10","r9","r8","rax","rcx","rdx","rsi","rdi","orig_rax","rip","cs","eflags","rsp","ss","fs_base","gs_base","ds","es","fs","gs")]
BP=0x10b08b4a
def dxpids():
    o=[]
    for d in glob.glob("/proc/[0-9]*"):
        try:
            if b"DeusEx.exe" in open(d+"/cmdline","rb").read(): o.append(int(d.split("/")[-1]))
        except: pass
    return o
target=mem=orig=None; t0=time.time()
while time.time()-t0<240 and target is None:
    for pid in dxpids():
        try:
            m=os.open(f"/proc/{pid}/mem",os.O_RDWR); os.lseek(m,BP,0); b=os.read(m,1)
            if b==b"\x8a": target=pid; mem=m; orig=b; break
            os.close(m)
        except:
            try: os.close(m)
            except: pass
    if target is None: time.sleep(0.2)
if not target: print("DONE no-render-pid-240s"); sys.exit()
sys.stderr.write("target=%d render loaded @ %.0fs\n"%(target,time.time()-t0)); sys.stderr.flush()
seized=[int(t) for t in os.listdir("/proc/%d/task"%target) if pt(PTRACE_SEIZE,int(t),0,0)[0]==0]
pt(PTRACE_INTERRUPT,seized[0])
try: os.waitpid(seized[0],0)
except: pass
os.lseek(mem,BP,0); os.write(mem,b"\xcc")
for t in seized: pt(PTRACE_CONT,t,0,0)
def mapped(a):
    try: os.lseek(mem,a,0); os.read(mem,1); return True
    except: return False
seen={}; nhit=0; crash=None; last=time.time(); deadline=time.time()+150
while time.time()<deadline and crash is None:
    if time.time()-last>2:
        for t in os.listdir("/proc/%d/task"%target):
            ti=int(t)
            if ti not in seized and pt(PTRACE_SEIZE,ti,0,0)[0]==0: seized.append(ti); pt(PTRACE_CONT,ti,0,0)
        last=time.time()
    try: pid,status=os.waitpid(-1,os.WNOHANG)
    except ChildProcessError: break
    if pid==0: time.sleep(0.001); continue
    if os.WIFSTOPPED(status):
        sig=os.WSTOPSIG(status); event=(status>>16)&0xff
        rg=R(); pt(PTRACE_GETREGS,pid,0,ctypes.addressof(rg)); rip=rg.rip&0xffffffff
        if sig==signal.SIGTRAP and rip==(BP+1) and event==0:
            nhit+=1; ebx=rg.rbx&0xffffffff; mp=mapped(ebx+0x1e0); k=(ebx,mp)
            if k not in seen: seen[k]=nhit; sys.stderr.write("hit#%d ebx=0x%08x mapped=%s\n"%(nhit,ebx,mp)); sys.stderr.flush()
            if not mp: crash=ebx; print("CRASH ebx=0x%08x [ebx+0x1e0]=UNMAPPED"%ebx,flush=True)
            os.lseek(mem,BP,0); os.write(mem,orig); rg.rip=BP; pt(PTRACE_SETREGS,pid,0,ctypes.addressof(rg))
            pt(PTRACE_SINGLESTEP,pid,0,0)
            try: os.waitpid(pid,0)
            except: pass
            os.lseek(mem,BP,0); os.write(mem,b"\xcc"); pt(PTRACE_CONT,pid,0,0)
        else:
            inj=sig if (event==0 and sig not in(signal.SIGSTOP,signal.SIGTRAP)) else 0
            pt(PTRACE_CONT,pid,0,inj)
try: os.lseek(mem,BP,0); os.write(mem,orig); os.close(mem)
except: pass
for t in seized: pt(PTRACE_DETACH,t,0,0)
print("DONE hits=%d distinct=%s crash=%s"%(nhit,[(hex(e),m) for (e,m) in seen],hex(crash) if crash else None))
